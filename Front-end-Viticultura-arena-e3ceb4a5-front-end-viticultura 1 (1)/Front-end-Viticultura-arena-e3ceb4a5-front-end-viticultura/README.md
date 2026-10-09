# AgroClima Cloud — Frontend (desenvolvimento local)

Esta pasta contém o `package.json` do frontend (Vite + JavaScript). Todos os comandos abaixo devem ser executados **dentro desta pasta**. Para subir as APIs Java e Python e o MySQL, siga o [README da raiz do repositório](../../README.md).

## 1. Pré-requisitos

- **Node.js 22.12+** (ou 20.19+) e **npm**. O Vite 7 não funciona em versões anteriores; confira com `node -v`.
- As APIs Java (8080) e Python (8000) são necessárias para que os dados apareçam. A tela abre sem elas, mas as chamadas `/api/...` falham.

## 2. Configurar o `.env`

O Vite lê o `.env` que fica na mesma pasta do `package.json`. Crie-o a partir do exemplo:

Linux / macOS (Bash):

```bash
cp .env.example .env
```

Windows (PowerShell):

```powershell
Copy-Item .env.example .env
```

O exemplo define a porta e os destinos do proxy:

```dotenv
VITE_PORT=5173
VITE_API_JAVA_BASE=/api/java
VITE_API_PYTHON_BASE=/api/python
DEV_JAVA_API_URL=http://localhost:8080
DEV_PYTHON_API_URL=http://localhost:8000
```

Os caminhos relativos mantêm o navegador em same-origin; o Vite encaminha `/api/java` para `DEV_JAVA_API_URL` e `/api/python` para `DEV_PYTHON_API_URL`. As demais variáveis do arquivo são usadas apenas pelo Docker Compose opcional.

## 3. Instalar e iniciar

Linux / macOS (Bash):

```bash
npm ci
npm run dev
```

Windows (PowerShell):

```powershell
npm ci
npm run dev
```

Acesse http://localhost:5173. O servidor escuta em `0.0.0.0`, então também responde pelo IP da máquina na rede local.

## 4. Build e preview

```bash
npm run build      # gera dist/ (ignorado pelo Git)
npm run preview    # serve dist/ em http://localhost:4173
```

## 5. Problemas comuns

- **`npm ERR! ENOENT ... package.json` ou `Could not read package.json`:** o comando foi executado na raiz do repositório. Entre nesta pasta (`cd "Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)/Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura"`).
- **`cp: cannot stat '.env.example'`:** o comando foi executado fora desta pasta. O `.env.example` do frontend fica aqui.
- **`Vite requires Node.js version 20.19+ or 22.12+`:** atualize o Node.js.
- **`Port 5173 is already in use`:** o Vite usa porta estrita. Libere a porta ou altere `VITE_PORT` no `.env`.
- **Páginas abrem, mas as chamadas `/api/...` retornam 500 ou `ECONNREFUSED`:** a API Java (8080) ou a Python (8000) não está em execução.
- **Caminhos com espaços e parênteses:** coloque o caminho entre aspas nos comandos de terminal.

Os arquivos `docker-compose.yml` e `frontend.Dockerfile` são opcionais e não são usados pelos comandos acima.
