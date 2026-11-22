import os
import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
db = SQLAlchemy()
csrf = CSRFProtect()
BR_TZ = ZoneInfo("America/Sao_Paulo")


def agora_br():
    return datetime.now(BR_TZ).replace(tzinfo=None)


def criar_app():
    app = Flask(__name__)
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        secret_key = secrets.token_hex(32)
        print("[AVISO] SECRET_KEY nao configurada; usando uma chave temporaria aleatoria.")
    elif len(secret_key) < 32:
        raise RuntimeError("SECRET_KEY deve ter pelo menos 32 caracteres.")
    app.config["SECRET_KEY"] = secret_key
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "").replace(
        "postgres://", "postgresql://", 1
    ) or "sqlite:///pizzaria.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    production = (
        os.getenv("ENVIRONMENT", "").strip().lower() == "production"
        or os.getenv("RENDER", "").strip().lower() == "true"
    )
    cookie_secure = os.getenv("COOKIE_SECURE")
    if cookie_secure is None:
        cookie_secure = "true" if production else "false"
    secure_cookies = cookie_secure.lower() == "true"
    if production and not secure_cookies:
        raise RuntimeError("COOKIE_SECURE=true deve ser configurado em producao.")
    app.config["SESSION_COOKIE_SECURE"] = secure_cookies
    app.config["WTF_CSRF_TIME_LIMIT"] = None

    db.init_app(app)
    csrf.init_app(app)

    @app.context_processor
    def dados_globais():
        return {"usuario_atual": usuario_logado(), "now": agora_br()}

    with app.app_context():
        db.create_all()
        criar_admin_inicial()
        criar_produtos_exemplo()

    @app.get("/")
    def index():
        categorias = ["Pizzas", "Bebidas", "Sobremesas"]
        produtos = Produto.query.filter_by(ativo=True).order_by(Produto.categoria, Produto.nome).all()
        promos = Promocao.query.filter(
            Promocao.ativa.is_(True), Promocao.inicio <= agora_br(), Promocao.fim > agora_br()
        ).all()
        return render_template("index.html", produtos=produtos, categorias=categorias, promos=promos)

    @app.route("/cadastro", methods=["GET", "POST"])
    def cadastro():
        if request.method == "POST":
            nome = request.form.get("nome", "").strip()
            email = request.form.get("email", "").strip().lower()
            senha = request.form.get("senha", "")
            if not nome or not email or len(senha) < 8:
                flash("Preencha os campos. A senha precisa ter pelo menos 8 caracteres.", "erro")
            elif Usuario.query.filter_by(email=email).first():
                flash("Este e-mail já está cadastrado.", "erro")
            else:
                user = Usuario(nome=nome, email=email, senha_hash=generate_password_hash(senha), papel="cliente")
                db.session.add(user)
                db.session.commit()
                session.clear()
                session["usuario_id"] = user.id
                flash("Conta criada com sucesso!", "sucesso")
                return redirect(url_for("index"))
        return render_template("auth.html", modo="cadastro")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            senha = request.form.get("senha", "")
            user = Usuario.query.filter_by(email=email).first()
            if user and check_password_hash(user.senha_hash, senha):
                session.clear()
                session["usuario_id"] = user.id
                flash("Login realizado.", "sucesso")
                return redirect(url_for("admin") if user.papel == "admin" else url_for("index"))
            flash("E-mail ou senha inválidos.", "erro")
        return render_template("auth.html", modo="login")

    @app.post("/sair")
    def sair():
        session.clear()
        flash("Você saiu da sua conta.", "sucesso")
        return redirect(url_for("index"))

    @app.post("/api/finalizar-pedido")
    def finalizar_pedido():
        user = usuario_logado()
        if not user or user.papel != "cliente":
            return jsonify(ok=False, erro="Entre em uma conta de cliente para finalizar."), 401
        dados = request.get_json(silent=True) or {}
        itens = dados.get("itens", [])
        endereco = str(dados.get("endereco", "")).strip()
        pagamento = str(dados.get("pagamento", "")).strip()
        observacao = str(dados.get("observacao", "")).strip()[:500]
        if not isinstance(itens, list) or not itens or len(itens) > 30:
            return jsonify(ok=False, erro="Seu carrinho está vazio ou contém itens demais."), 400
        if not endereco or len(endereco) < 8 or pagamento not in ["Pix", "Dinheiro", "Cartão na entrega"]:
            return jsonify(ok=False, erro="Informe um endereço e uma forma de pagamento válida."), 400

        pedido = Pedido(cliente_id=user.id, endereco=endereco, pagamento=pagamento,
                        observacao=observacao, status="Recebido", total=0)
        total = 0
        try:
            for item in itens:
                produto_id = int(item.get("produto_id"))
                quantidade = int(item.get("quantidade"))
                if quantidade < 1 or quantidade > 20:
                    raise ValueError()
                produto = db.session.get(Produto, produto_id)
                if not produto or not produto.ativo:
                    return jsonify(ok=False, erro="Um produto não está mais disponível."), 400
                subtotal = produto.preco * quantidade
                total += subtotal
                pedido.itens.append(ItemPedido(produto_id=produto.id, nome_produto=produto.nome,
                                               quantidade=quantidade, preco_unitario=produto.preco))
            if total <= 0:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            return jsonify(ok=False, erro="Carrinho inválido. Atualize a página e tente novamente."), 400

        pedido.total = total
        db.session.add(pedido)
        db.session.commit()
        return jsonify(ok=True, mensagem="Pedido enviado!", pedido_id=pedido.id)

    @app.get("/meus-pedidos")
    def meus_pedidos():
        user = usuario_logado()
        if not user or user.papel != "cliente":
            return redirect(url_for("login"))
        pedidos = Pedido.query.filter_by(cliente_id=user.id).order_by(Pedido.criado_em.desc()).all()
        return render_template("meus_pedidos.html", pedidos=pedidos)

    @app.get("/admin")
    @admin_required
    def admin():
        pedidos = Pedido.query.order_by(Pedido.criado_em.desc()).limit(80).all()
        produtos = Produto.query.order_by(Produto.categoria, Produto.nome).all()
        promos = Promocao.query.order_by(Promocao.criado_em.desc()).all()
        produto_edicao = db.session.get(Produto, request.args.get("editar", type=int)) if request.args.get("editar") else None
        total_hoje = db.session.query(func.coalesce(func.sum(Pedido.total), 0)).filter(
            func.date(Pedido.criado_em) == agora_br().date(),
            Pedido.status != "Cancelado"
        ).scalar() or 0
        return render_template("admin.html", pedidos=pedidos, produtos=produtos,
                               promos=promos, total_hoje=total_hoje, produto_edicao=produto_edicao)

    @app.get("/admin/pedidos.json")
    @admin_required
    def pedidos_json():
        pedidos = Pedido.query.order_by(Pedido.criado_em.desc()).limit(80).all()
        return jsonify([pedido_dict(p) for p in pedidos])

    @app.post("/admin/pedido/<int:pedido_id>/status")
    @admin_required
    def alterar_status(pedido_id):
        pedido = db.get_or_404(Pedido, pedido_id)
        status = request.form.get("status")
        permitidos = ["Recebido", "Em preparo", "Saiu para entrega", "Concluído", "Cancelado"]
        if status not in permitidos:
            abort(400)
        pedido.status = status
        db.session.commit()
        flash(f"Pedido #{pedido.id} atualizado.", "sucesso")
        return redirect(url_for("admin") + "#pedidos")

    @app.post("/admin/produto")
    @admin_required
    def salvar_produto():
        try:
            produto_id = request.form.get("produto_id")
            nome = request.form.get("nome", "").strip()
            categoria = request.form.get("categoria", "").strip()
            descricao = request.form.get("descricao", "").strip()[:300]
            preco = int(round(float(request.form.get("preco", "0").replace(",", ".")) * 100))
            imagem = request.form.get("imagem", "").strip()[:500]
            if not nome or categoria not in ["Pizzas", "Bebidas", "Sobremesas"] or preco <= 0:
                raise ValueError()
            produto = db.session.get(Produto, int(produto_id)) if produto_id else Produto()
            if not produto:
                abort(404)
            produto.nome, produto.categoria, produto.descricao = nome, categoria, descricao
            produto.preco, produto.imagem_url = preco, imagem
            produto.ativo = request.form.get("ativo") == "on"
            db.session.add(produto)
            db.session.commit()
            flash("Produto salvo.", "sucesso")
        except (ValueError, TypeError):
            flash("Confira nome, categoria e preço.", "erro")
        return redirect(url_for("admin") + "#produtos")

    @app.post("/admin/produto/<int:produto_id>/excluir")
    @admin_required
    def excluir_produto(produto_id):
        produto = db.get_or_404(Produto, produto_id)
        if ItemPedido.query.filter_by(produto_id=produto.id).first():
            produto.ativo = False
            flash("Produto desativado porque já aparece em pedidos antigos.", "sucesso")
        else:
            db.session.delete(produto)
            flash("Produto excluído.", "sucesso")
        db.session.commit()
        return redirect(url_for("admin") + "#produtos")

    @app.post("/admin/promocao")
    @admin_required
    def criar_promocao():
        try:
            titulo = request.form.get("titulo", "").strip()
            descricao = request.form.get("descricao", "").strip()[:300]
            duracao = int(request.form.get("duracao_horas", "0"))
            if not titulo or duracao < 1 or duracao > 720:
                raise ValueError()
            promo = Promocao(titulo=titulo, descricao=descricao, inicio=agora_br(),
                             fim=agora_br() + timedelta(hours=duracao), ativa=True)
            db.session.add(promo)
            db.session.commit()
            flash("Promoção criada. Ela expira automaticamente no horário de Brasília.", "sucesso")
        except ValueError:
            flash("Informe título e duração entre 1 e 720 horas.", "erro")
        return redirect(url_for("admin") + "#promocoes")

    @app.post("/admin/promocao/<int:promo_id>/excluir")
    @admin_required
    def excluir_promocao(promo_id):
        promo = db.get_or_404(Promocao, promo_id)
        db.session.delete(promo)
        db.session.commit()
        flash("Promoção removida.", "sucesso")
        return redirect(url_for("admin") + "#promocoes")

    return app


from functools import wraps
def usuario_logado():
    uid = session.get("usuario_id")
    return db.session.get(Usuario, uid) if uid else None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = usuario_logado()
        if not user or user.papel != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def pedido_dict(p):
    return {
        "id": p.id, "cliente": p.cliente.nome, "endereco": p.endereco,
        "pagamento": p.pagamento, "observacao": p.observacao,
        "status": p.status, "total": p.total / 100,
        "criado_em": p.criado_em.strftime("%d/%m/%Y %H:%M"),
        "itens": [{"nome": i.nome_produto, "quantidade": i.quantidade,
                   "preco": i.preco_unitario / 100} for i in p.itens]
    }


class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(180), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    papel = db.Column(db.String(20), nullable=False, default="cliente")
    criado_em = db.Column(db.DateTime, default=agora_br)
    pedidos = db.relationship("Pedido", back_populates="cliente")


class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    categoria = db.Column(db.String(30), nullable=False)
    descricao = db.Column(db.String(300), default="")
    preco = db.Column(db.Integer, nullable=False)  # centavos
    imagem_url = db.Column(db.String(500), default="")
    ativo = db.Column(db.Boolean, default=True, nullable=False)


class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), nullable=False)
    criado_em = db.Column(db.DateTime, default=agora_br)
    endereco = db.Column(db.String(500), nullable=False)
    pagamento = db.Column(db.String(40), nullable=False)
    observacao = db.Column(db.String(500), default="")
    status = db.Column(db.String(40), default="Recebido", nullable=False)
    total = db.Column(db.Integer, nullable=False, default=0)
    cliente = db.relationship("Usuario", back_populates="pedidos")
    itens = db.relationship("ItemPedido", backref="pedido", cascade="all, delete-orphan")


class ItemPedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey("pedido.id"), nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey("produto.id"), nullable=True)
    nome_produto = db.Column(db.String(120), nullable=False)
    quantidade = db.Column(db.Integer, nullable=False)
    preco_unitario = db.Column(db.Integer, nullable=False)


class Promocao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(120), nullable=False)
    descricao = db.Column(db.String(300), default="")
    inicio = db.Column(db.DateTime, nullable=False)
    fim = db.Column(db.DateTime, nullable=False)
    ativa = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=agora_br)


def criar_admin_inicial():
    admin = Usuario.query.filter_by(papel="admin").first()
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    senha = os.getenv("ADMIN_PASSWORD", "")

    if admin:
        if check_password_hash(admin.senha_hash, "TroqueEstaSenha123!") :
            if not email or not senha:
                raise RuntimeError(
                    "O admin inicial ainda usa a senha padrao. Configure ADMIN_EMAIL "
                    "e uma nova ADMIN_PASSWORD segura."
                )
            admin.email = email
            admin.senha_hash = generate_password_hash(senha)
            db.session.commit()
            print("[AVISO] Senha padrao do administrador substituida.")
        return

    if not email or not senha:
        raise RuntimeError(
            "Configure ADMIN_EMAIL e ADMIN_PASSWORD para criar o administrador inicial."
        )
    if len(senha) < 12:
        raise RuntimeError("ADMIN_PASSWORD deve ter pelo menos 12 caracteres.")

    admin = Usuario(
        nome=os.getenv("ADMIN_NAME", "Administrador").strip() or "Administrador",
        email=email,
        senha_hash=generate_password_hash(senha),
        papel="admin",
    )
    db.session.add(admin)
    db.session.commit()
    print(f"Admin inicial criado: {email}")


def criar_produtos_exemplo():
    if Produto.query.count() == 0:
        exemplos = [
            Produto(nome="Calabresa", categoria="Pizzas", descricao="Molho, mussarela, calabresa e cebola.", preco=4590),
            Produto(nome="Mussarela", categoria="Pizzas", descricao="Molho artesanal, mussarela e orégano.", preco=4290),
            Produto(nome="Frango com Catupiry", categoria="Pizzas", descricao="Frango desfiado e requeijão cremoso.", preco=4990),
            Produto(nome="Refrigerante 2L", categoria="Bebidas", descricao="Consulte os sabores disponíveis.", preco=1290),
            Produto(nome="Brownie", categoria="Sobremesas", descricao="Brownie de chocolate.", preco=990),
        ]
        db.session.add_all(exemplos)
        db.session.commit()


app = criar_app()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
