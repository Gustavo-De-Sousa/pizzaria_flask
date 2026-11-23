# Forno da Vila — sistema de pedidos com Flask

Projeto inicial funcional de pizzaria: vitrine pública, cadastro/login de clientes, carrinho, checkout validado no servidor, painel administrativo, gestão de produtos, promoções com expiração e atualização automática dos pedidos.

## 1. Requisitos
- Python 3.10+
- Git (opcional)
- Para produção: PostgreSQL

## 2. Executar localmente (Windows PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```
Edite `.env` e configure uma `SECRET_KEY` aleatoria com pelo menos 32 caracteres,
`ADMIN_EMAIL` e uma `ADMIN_PASSWORD` com pelo menos 12 caracteres.
Nao use senha ou chave de exemplo no ambiente real.

Para habilitar "Esqueceu sua senha?", configure também `PUBLIC_BASE_URL` e os campos
`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD` e `SMTP_FROM`. Por padrão,
o envio usa STARTTLS na porta 587; use `SMTP_USE_SSL=true` para provedores que exigem
TLS implícito, normalmente na porta 465. Em produção, `PUBLIC_BASE_URL` deve começar
com `https://`. Use uma senha de app do provedor de e-mail quando disponível.

```powershell
python app.py
```
Abra http://127.0.0.1:5000

Execute os testes automatizados com `python -m unittest discover -s tests`.

No primeiro início, o sistema cria produtos de demonstração e o administrador definido no `.env`. Faça login com `ADMIN_EMAIL` e `ADMIN_PASSWORD`.

Se já existe uma conta de administrador e você esqueceu a senha, execute `python reset_admin_password.py` no terminal do projeto. O comando mostra os e-mails das contas admin e solicita a nova senha sem exibi-la. Depois, entre em `/login` com o e-mail e a senha escolhidos.

## 3. Publicar no Render
1. Envie o projeto para um repositório GitHub privado ou público.
2. Crie um PostgreSQL no Render.
3. Crie um Web Service ligado ao repositório.
4. Build command: `pip install -r requirements.txt` (inclui Gunicorn e o driver PostgreSQL)
5. Start command: `gunicorn app:app`
6. Configure `SECRET_KEY`, `DATABASE_URL`, `ADMIN_EMAIL` e `ADMIN_PASSWORD` nas variáveis de ambiente.
7. Para habilitar a recuperação de senha, configure `PUBLIC_BASE_URL` com a URL HTTPS do serviço e as variáveis SMTP.
8. Ative `COOKIE_SECURE=true` em produção HTTPS.
9. Aponte seu domínio para o serviço conforme as instruções do Render.

O `render.yaml` é um exemplo de Blueprint. Confira os planos e preços atuais do Render antes de publicar.

## 4. Recursos implementados
- Senhas armazenadas com hash Werkzeug.
- Recuperação de senha por e-mail com token de uso único e validade de 30 minutos.
- Sessões com cookie HttpOnly e SameSite=Lax.
- Proteção CSRF em formulários e requisição de checkout.
- Separação de cliente e administrador no backend.
- Preço e total recalculados com dados do banco; o valor vindo do navegador é ignorado.
- Quantidade limitada por item e validação de disponibilidade.
- Promoções com data final armazenada em horário local `America/Sao_Paulo`; deixam de aparecer após expirar.
- Painel busca pedidos automaticamente a cada 8 segundos.
- Botão de impressão usa a impressão do navegador; impressão térmica automática exige um serviço local/conector com a impressora.

## 5. Importante antes de vender para uma pizzaria
Este é um MVP funcional para desenvolvimento, não uma plataforma auditada. Antes de receber pagamentos reais:
- Adicione confirmação de e-mail.
- Integre um gateway de pagamento (Pix/cartão) com confirmação por webhook; não marque pagamento como aprovado pelo retorno do navegador.
- Defina taxa de entrega, bairros atendidos, tamanhos, meio a meio, bordas e adicionais como tabelas/regras próprias. O exemplo atual vende produtos com preço fixo.
- Configure backups do PostgreSQL, logs, monitoramento, política de privacidade e termos.
- Adicione rate limit e política de bloqueio/limite de tentativas no login.
- Use migrações (Flask-Migrate/Alembic) para evoluir o banco sem perder dados.
- Para impressão automática em impressora térmica USB/rede, instale um agente local na pizzaria. Um site hospedado na nuvem não consegue acessar diretamente a USB do computador do estabelecimento.

## 6. Estrutura
Os testes ficam em `tests/`; `reset_admin_password.py` redefine localmente a senha de uma conta admin existente. As telas de recuperação estão em `templates/recuperar_senha.html` e `templates/redefinir_senha.html`.

```text
pizzaria_flask/
├── app.py
├── requirements.txt
├── .env.example
├── render.yaml
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── auth.html
│   ├── meus_pedidos.html
│   └── admin.html
└── static/
    ├── css/style.css
    └── js/{main,shop,admin}.js
```
