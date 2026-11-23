import hashlib
import os
import re
import smtplib
import unittest
from datetime import datetime
from urllib.parse import urlsplit
from unittest.mock import patch

os.environ.update(
    {
        "DATABASE_URL": "sqlite:///:memory:",
        "ADMIN_EMAIL": "admin@example.test",
        "ADMIN_PASSWORD": "InitialAdminPassword123!",
        "SECRET_KEY": "password-recovery-tests-secret-key",
        "COOKIE_SECURE": "false",
        "PUBLIC_BASE_URL": "http://localhost",
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "587",
        "SMTP_USERNAME": "sender@example.test",
        "SMTP_PASSWORD": "test-smtp-password",
        "SMTP_FROM": "sender@example.test",
        "SMTP_USE_SSL": "false",
    }
)

from app import (
    ItemPedido,
    Pedido,
    Produto,
    TokenRecuperacaoSenha,
    Usuario,
    app,
    criar_admin_inicial,
    criar_app,
    db,
)
from werkzeug.security import check_password_hash, generate_password_hash


class PasswordRecoveryTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.app_context = app.app_context()
        self.app_context.push()
        db.session.remove()
        db.drop_all()
        db.create_all()
        self.admin = Usuario(
            nome="Admin de teste",
            email="admin@example.test",
            senha_hash=generate_password_hash("InitialAdminPassword123!"),
            papel="admin",
        )
        self.cliente = Usuario(
            nome="Cliente de teste",
            email="cliente@example.test",
            senha_hash=generate_password_hash("InitialClientPassword123!"),
            papel="cliente",
        )
        self.produto = Produto(
            nome="Pizza de teste",
            categoria="Pizzas",
            descricao="Produto para testes.",
            preco=1250,
            ativo=True,
        )
        db.session.add_all([self.admin, self.cliente, self.produto])
        db.session.commit()
        self.client = app.test_client()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_login_page_links_to_password_recovery(self):
        response = self.client.get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/recuperar-senha", response.data)

    def test_email_link_resets_password_and_cannot_be_reused(self):
        with patch("app.smtplib.SMTP") as smtp_class:
            response = self.client.post(
                "/recuperar-senha", data={"email": "admin@example.test"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Se o e-mail estiver cadastrado", response.data)
        smtp = smtp_class.return_value.__enter__.return_value
        message = smtp.send_message.call_args.args[0]
        link = re.search(r"http://localhost/redefinir-senha/[A-Za-z0-9_-]+", message.get_content())
        self.assertIsNotNone(link)
        reset_path = urlsplit(link.group(0)).path
        self.assertEqual(self.client.get(reset_path).status_code, 200)

        response = self.client.post(
            reset_path,
            data={"senha": "UpdatedAdminPassword123!", "confirmacao": "UpdatedAdminPassword123!"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/login")
        db.session.expire_all()
        admin = Usuario.query.filter_by(email="admin@example.test").one()
        self.assertTrue(check_password_hash(admin.senha_hash, "UpdatedAdminPassword123!"))
        self.assertEqual(TokenRecuperacaoSenha.query.count(), 0)
        self.assertEqual(self.client.get(reset_path).status_code, 302)

    def test_unknown_email_gets_same_confirmation_without_sending(self):
        with patch("app.smtplib.SMTP") as smtp_class:
            response = self.client.post(
                "/recuperar-senha", data={"email": "missing@example.test"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Se o e-mail estiver cadastrado", response.data)
        smtp_class.assert_not_called()
        self.assertEqual(TokenRecuperacaoSenha.query.count(), 0)

    def test_mail_failure_does_not_leave_a_usable_token(self):
        with patch("app.smtplib.SMTP", side_effect=smtplib.SMTPException("mail unavailable")):
            with self.assertLogs("app", level="ERROR"):
                response = self.client.post(
                    "/recuperar-senha", data={"email": "admin@example.test"}
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Se o e-mail estiver cadastrado", response.data)
        self.assertEqual(TokenRecuperacaoSenha.query.count(), 0)

    def test_expired_link_cannot_reset_password(self):
        token = "e" * 43
        db.session.add(
            TokenRecuperacaoSenha(
                usuario_id=self.admin.id,
                token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
                expira_em=datetime(2000, 1, 1),
            )
        )
        db.session.commit()

        response = self.client.post(
            f"/redefinir-senha/{token}",
            data={"senha": "UpdatedAdminPassword123!", "confirmacao": "UpdatedAdminPassword123!"},
        )

        self.assertEqual(response.status_code, 302)
        db.session.expire_all()
        admin = Usuario.query.filter_by(email="admin@example.test").one()
        self.assertTrue(check_password_hash(admin.senha_hash, "InitialAdminPassword123!"))

    def test_admin_pages_require_admin_and_render(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/admin").status_code, 403)

        with self.client.session_transaction() as browser_session:
            browser_session["usuario_id"] = self.admin.id

        self.assertEqual(self.client.get("/admin").status_code, 200)

    def test_registration_rejects_fields_exceeding_database_limits(self):
        response = self.client.post(
            "/cadastro",
            data={
                "nome": "A" * 101,
                "email": "new@example.test",
                "senha": "ValidPassword123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(Usuario.query.filter_by(email="new@example.test").first())

    def test_checkout_rejects_non_object_json(self):
        with self.client.session_transaction() as browser_session:
            browser_session["usuario_id"] = self.cliente.id

        response = self.client.post("/api/finalizar-pedido", json=[])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Pedido.query.count(), 0)

    def test_checkout_aggregates_duplicate_items_and_uses_database_price(self):
        with self.client.session_transaction() as browser_session:
            browser_session["usuario_id"] = self.cliente.id
        checkout = {
            "endereco": "Rua das Flores, 123",
            "pagamento": "Pix",
            "itens": [
                {"produto_id": self.produto.id, "quantidade": 2, "preco": 1},
                {"produto_id": self.produto.id, "quantidade": 3, "preco": 1},
            ],
        }

        response = self.client.post("/api/finalizar-pedido", json=checkout)

        self.assertEqual(response.status_code, 200)
        pedido = Pedido.query.one()
        item = ItemPedido.query.one()
        self.assertEqual(pedido.total, 6250)
        self.assertEqual(item.quantidade, 5)

    def test_checkout_cannot_bypass_quantity_limit_with_duplicate_items(self):
        with self.client.session_transaction() as browser_session:
            browser_session["usuario_id"] = self.cliente.id
        response = self.client.post(
            "/api/finalizar-pedido",
            json={
                "endereco": "Rua das Flores, 123",
                "pagamento": "Pix",
                "itens": [
                    {"produto_id": self.produto.id, "quantidade": 15},
                    {"produto_id": self.produto.id, "quantidade": 6},
                ],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Pedido.query.count(), 0)

    def test_admin_price_uses_decimal_rounding(self):
        with self.client.session_transaction() as browser_session:
            browser_session["usuario_id"] = self.admin.id

        response = self.client.post(
            "/admin/produto",
            data={
                "nome": "Pizza arredondada",
                "categoria": "Pizzas",
                "preco": "2.675",
                "ativo": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        produto = Produto.query.filter_by(nome="Pizza arredondada").one()
        self.assertEqual(produto.preco, 268)

    def test_production_requires_a_persistent_secret_key(self):
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "RENDER": "",
                "SECRET_KEY": "",
                "COOKIE_SECURE": "true",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                criar_app()

    def test_default_admin_password_cannot_be_replaced_with_a_weak_password(self):
        self.admin.senha_hash = generate_password_hash("TroqueEstaSenha123!")
        db.session.commit()

        with patch.dict(
            os.environ,
            {
                "ADMIN_EMAIL": self.admin.email,
                "ADMIN_PASSWORD": "short",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "12 caracteres"):
                criar_admin_inicial()


if __name__ == "__main__":
    unittest.main()
