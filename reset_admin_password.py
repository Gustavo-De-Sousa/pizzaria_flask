from getpass import getpass

from app import app, db, Usuario
from werkzeug.security import generate_password_hash


with app.app_context():
    admins = Usuario.query.filter_by(papel="admin").order_by(Usuario.id).all()
    if not admins:
        raise SystemExit("Nenhuma conta de administrador foi encontrada.")

    print("Contas de administrador encontradas:")
    for admin in admins:
        print(f"- {admin.email}")

    email = input("E-mail da conta que deseja redefinir: ").strip().lower()
    admin = next((user for user in admins if user.email == email), None)
    if not admin:
        raise SystemExit("E-mail nao corresponde a uma conta de administrador.")

    senha = getpass("Nova senha (minimo de 12 caracteres): ")
    confirmacao = getpass("Confirme a nova senha: ")
    if len(senha) < 12 or len(senha) > 256:
        raise SystemExit("A senha precisa ter entre 12 e 256 caracteres.")
    if senha != confirmacao:
        raise SystemExit("As senhas nao conferem.")

    admin.senha_hash = generate_password_hash(senha)
    db.session.commit()

print("Senha do administrador redefinida com sucesso.")
