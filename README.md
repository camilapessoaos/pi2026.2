
# AgroClima Cloud — Desenvolvimento Local

Aplicação web com frontend JavaScript, API de domínio Spring Boot, serviço analítico FastAPI e MySQL Server local (administrável pelo MySQL Workbench). O ambiente de desenvolvimento usa somente serviços locais: não precisa de domínio, hospedagem, Railway, Render, AWS, Azure, Vercel ou Docker. **ThingSpeak** é a única integração externa opcional em tempo de execução e é consultado somente pelo backend Java.

O navegador chama caminhos *same-origin* (`/api/java` e `/api/python`); o proxy do Vite encaminha as chamadas para as APIs locais. As fontes **DM Sans** e **Manrope** são empacotadas no frontend, e os arquivos Swagger UI do Python são servidos pela própria API; a documentação não depende de CDN.

---

## 1. Pré-requisitos

Instale no computador:
* **JDK 21** e **Maven 3.9+** para a API Java;
* **MySQL Server 8.4+** instalado e em execução local; o MySQL Workbench é opcional para administrar o servidor;
* **Python 3.11+** para a API analítica;
* **Node.js 22.12+** (ou 20.19+) e **npm** para o frontend. O Vite 7 não funciona em versões anteriores.

> **Nota:** Não é necessário instalar ou iniciar Docker.

### Portas Padrão

As portas padrão devem estar livres:

| Serviço | Porta padrão | URL local |
| :--- | :--- | :--- |
| **Frontend Vite** | `5173` | `http://localhost:5173` |
| **API Java / Spring Boot** | `8080` | `http://localhost:8080` |
| **API Python / FastAPI** | `8000` | `http://localhost:8000` |
| **MySQL Server** | `3306` | `localhost:3306` |

---

## 2. Criar e Configurar o MySQL Server Local

Instale e inicie o MySQL Server 8.4 no computador. O MySQL Workbench é um cliente gráfico para administrar o servidor; instalá-lo sozinho **não** instala nem inicia o banco.

Conecte pelo Workbench a `127.0.0.1:3306` com uma conta administrativa e execute uma vez no SQL Editor:

```sql
CREATE DATABASE agroclima CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'agroclima'@'localhost' IDENTIFIED BY 'SUBSTITUA_POR_UMA_SENHA_LOCAL';
GRANT ALL PRIVILEGES ON agroclima.* TO 'agroclima'@'localhost';
Use a mesma senha em DATABASE_PASSWORD no .env da API Java.

Caso já tenha criado outro schema ou usuário, atualize DATABASE_URL, DATABASE_USER e DATABASE_PASSWORD para corresponderem a eles.

Para conexão direta local, o endereço padrão é jdbc:mysql://localhost:3306/agroclima.

Ao iniciar a API Java, o Flyway aplica as migrations MySQL localizadas em backend/java/src/main/resources/db/migration/; o Hibernate apenas valida o schema (não o cria automaticamente).

Depois do boot, atualize a lista de schemas no Workbench para conferir as tabelas app_user, plantation, climate_reading e demais objetos da aplicação. Os dados existentes em PostgreSQL não são migrados automaticamente: use um schema MySQL novo e planeje qualquer exportação/importação separadamente.

O docker-compose.yml oferece, opcionalmente, um MySQL em container e publica sua porta local para conexão pelo Workbench; o Docker não é necessário no fluxo direto acima.

3. Arquivos .env
Os exemplos não contêm credenciais de produção. Copie-os para arquivos locais — esses arquivos são ignorados pelo Git:

Linux / macOS (Bash):

Bash
cp "Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)/Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura/.env.example" "Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)/Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura/.env"
cp backend/java/.env.example backend/java/.env
cp backend/python/.env.example backend/python/.env
Windows (PowerShell):

PowerShell
Copy-Item "Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)\Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura\.env.example" "Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)\Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura\.env"
Copy-Item backend/java/.env.example backend/java/.env
Copy-Item backend/python/.env.example backend/python/.env
Java — backend/java/.env
Preencha pelo menos:

DATABASE_URL, DATABASE_USER e DATABASE_PASSWORD: acesso ao MySQL Server local;

JWT_SECRET: segredo aleatório de pelo menos 32 bytes;

INITIAL_ADMIN_EMAIL e INITIAL_ADMIN_PASSWORD: conta administrativa inicial;

INTERNAL_API_KEY: chave aleatória com pelo menos 32 caracteres, compartilhada com o Python;

PORT e SERVER_ADDRESS: por padrão 8080 e 127.0.0.1;

CORS_ALLOWED_ORIGINS: lista explícita de origens locais, sem *.

THINGSPEAK_*: configuração do canal consumido diretamente pelo Java (veja a seção 8).

Gere valores independentes para JWT_SECRET e INTERNAL_API_KEY e copie-os para os dois .env correspondentes. Para evitar problemas de escaping nos scripts de inicialização, também é prático usar uma senha hexadecimal para o banco e para o Administrador:

Bash
python3 -c "import secrets; print(secrets.token_hex(32))"
Execute o comando separadamente para cada segredo; use o valor de DATABASE_PASSWORD também ao criar o usuário MySQL no Workbench. A senha administrativa deve ter ao menos 8 caracteres, conter letras e números e respeitar o limite documentado pelo backend.

Python — backend/python/.env
JAVA_API_URL deve permanecer como http://localhost:8080.

Copie para INTERNAL_API_KEY o mesmo valor usado pela API Java.

CORS_ALLOWED_ORIGINS permite as origens locais configuradas sem usar wildcard.

O Python não acessa o ThingSpeak e não possui variáveis THINGSPEAK_*: as leituras chegam pela API Java, autenticadas com INTERNAL_API_KEY.

Frontend — .env na pasta do front
O Vite lê o `.env` que fica na mesma pasta do `package.json` do frontend, não na raiz do repositório. O exemplo configura a porta Vite e os destinos do proxy local:

Snippet de código
VITE_PORT=5173
DEV_JAVA_API_URL=http://localhost:8080
DEV_PYTHON_API_URL=http://localhost:8000
VITE_API_JAVA_BASE=/api/java
VITE_API_PYTHON_BASE=/api/python
Esses caminhos relativos preservam same-origin no navegador; o Vite faz o proxy para as APIs locais. Se optar por chamar as APIs diretamente do navegador, altere apenas VITE_API_JAVA_BASE para http://localhost:8080 e VITE_API_PYTHON_BASE para http://localhost:8000; os serviços já têm CORS local configurável.

4. Iniciar a API Java
Com o MySQL Server ligado, schema/usuário criados e backend/java/.env preenchido, abra um terminal na raiz do projeto:

Linux / macOS (Bash):

Bash
bash backend/java/run-local.sh
Windows (PowerShell):

PowerShell
.\backend\java\run-local.ps1
Os scripts carregam as variáveis de backend/java/.env e executam mvn spring-boot:run. Alternativamente, no Bash:

Bash
cd backend/java
set -a
source .env
set +a
mvn spring-boot:run
A primeira execução do Maven baixa as dependências de build. O primeiro boot aplica as migrations e cria a conta administrativa inicial se ela ainda não existir.

Health: http://localhost:8080/actuator/health

Swagger UI: http://localhost:8080/swagger-ui.html

OpenAPI JSON: http://localhost:8080/v3/api-docs

5. Iniciar a API Python
Em outro terminal:

Linux / macOS (Bash):

Bash
cd backend/python
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
Windows (PowerShell):

PowerShell
Set-Location backend/python
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
O FastAPI lê backend/python/.env ao iniciar a partir dessa pasta. Se a API Java estiver fora do ar, o Python continua iniciando; as rotas que dependem de leituras respondem com indisponibilidade e /health mostra javaApiConfigured e internalKeyConfigured.

Health: http://localhost:8000/health

Swagger UI: http://localhost:8000/docs

OpenAPI JSON: http://localhost:8000/openapi.json

6. Iniciar o Frontend
O `package.json` do frontend não está na raiz do repositório. Ele fica na pasta `Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)/Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura`, e todos os comandos npm devem ser executados dentro dela. Na raiz, `npm ci` e `npm run dev` falham com `ENOENT` (package.json não encontrado).

Em um terceiro terminal, a partir da raiz do repositório:

Linux / macOS (Bash):

Bash
cd "Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)/Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura"
npm ci
npm run dev

Windows (PowerShell):

PowerShell
Set-Location "Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)\Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura"
npm ci
npm run dev

Acesse http://localhost:5173. Use as aspas no caminho: o nome da pasta contém espaços e parênteses. O `.env` do frontend (seção 3) define a porta e os destinos do proxy; sem ele, o Vite usa os valores padrão.

Sem as APIs em execução, a tela abre normalmente, mas as chamadas /api/java/... e /api/python/... retornam erro 500 do proxy até que Java e Python sejam iniciados. As chamadas são encaminhadas pelo proxy configurado em vite.config.js para localhost:8080 e localhost:8000.

Para gerar os arquivos estáticos, execute na mesma pasta:

Bash
npm run build

O resultado vai para `dist/`, que é ignorado pelo Git. A configuração de Nginx e Docker Compose permanece opcional e não é usada pelos comandos locais acima.

7. Verificar APIs, Comunicação e Autenticação
Health e Documentação
Bash
curl -i http://localhost:8080/actuator/health
curl -i http://localhost:8000/health
curl -i http://localhost:5173/
Abra também as documentações Swagger indicadas acima. O frontend deve responder em localhost:5173 mesmo que uma API esteja parada; as operações que dependem dela mostrarão erro de conexão.

Testar Autenticação
Use o e-mail e a senha definidos em backend/java/.env para a conta administrativa inicial:

Bash
curl -sS -X POST http://localhost:8080/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@agroclima.com","password":"SENHA_CONFIGURADA_NO_ENV"}'
A resposta inclui accessToken. Use-o em operações protegidas:

Bash
curl -i http://localhost:8080/api/auth/me \
  -H 'Authorization: Bearer COLE_O_ACCESS_TOKEN_AQUI'
Sem token, /api/auth/me e os recursos protegidos devem responder 401. As permissões e o escopo de produtor são verificados pelo backend; a interface não substitui essas verificações. Também é possível criar uma conta Produtor pela tela de cadastro do frontend ou por POST /api/auth/register.

Testar o Proxy Frontend → APIs
Com os três serviços em execução, abra http://localhost:5173, entre com a conta criada e navegue pelas páginas de dados. No painel Network do navegador, as requisições devem começar por /api/java/ ou /api/python/, no mesmo host do frontend. Também se pode confirmar o health Python pelo proxy:

Bash
curl -i http://localhost:5173/api/python/health
Testar CORS
O CORS é restrito a origens locais explícitas (localhost e 127.0.0.1 nas portas usadas com Vite, Live Server e alternativas documentadas); não há allow all. O frontend Vite usa proxy same-origin e normalmente não precisa de CORS. Para conferir o preflight quando usar as bases diretas:

Bash
curl -i -X OPTIONS http://localhost:8080/api/auth/login \
  -H 'Origin: http://localhost:5173' \
  -H 'Access-Control-Request-Method: POST' \
  -H 'Access-Control-Request-Headers: content-type'
A resposta deve incluir Access-Control-Allow-Origin: http://localhost:5173. O mesmo teste pode ser feito para a API Python em http://localhost:8000/api/v1/dashboard/summary.

8. ThingSpeak (Opcional)
O backend Java consulta o canal diretamente em `https://api.thingspeak.com/channels/3499301/feeds.json`, normaliza as leituras e grava no MySQL. O Python e o frontend não acessam o ThingSpeak: o Python lê as leituras da API Java com INTERNAL_API_KEY.

No arquivo backend/java/.env, defina:

Snippet de código
THINGSPEAK_ENABLED=true
THINGSPEAK_CHANNEL_ID=3499301
THINGSPEAK_READ_API_KEY=SUA_READ_API_KEY_LOCAL
THINGSPEAK_URL=https://api.thingspeak.com
THINGSPEAK_FIELD_MAP='{"temperature":"field1","humidity":"field2"}'
THINGSPEAK_POLL_INTERVAL_SECONDS=300

O canal possui apenas dois campos ativos: **field1 = temperatura (°C)** e **field2 = umidade (%)**. O mapa é fixo: qualquer outro valor em THINGSPEAK_FIELD_MAP impede a inicialização do Java. Os demais campos do canal são ignorados. Mantenha o JSON entre aspas simples para que o run-local.sh não o quebre.

A THINGSPEAK_READ_API_KEY é um segredo: ela fica somente no backend/java/.env local (ignorado pelo Git) e não deve aparecer em arquivos de exemplo nem em logs.

Sincronização:
* automática: a cada THINGSPEAK_POLL_INTERVAL_SECONDS, somente com THINGSPEAK_ENABLED=true;
* manual (ADMIN): POST http://localhost:8080/api/integrations/thingspeak/sync, com ?from=AAAA-MM-DDTHH:MM:SSZ&to=... opcional (janela de até 366 dias);
* estado (ADMIN): GET http://localhost:8080/api/integrations/thingspeak/status.

O Python repassa essas duas rotas ao Java para o painel: GET /api/v1/integrations/thingspeak/status e POST /api/v1/integrations/thingspeak/sync (ADMIN). Como o Python não acessa o ThingSpeak, ele não tem variável de canal nem de chave.

Sem canal ou chave, o backend Java continua iniciando; a sincronização retorna configured=false e as telas mostram a indisponibilidade.

9. Testes
Bash
# Frontend (a partir da raiz do repositório)
cd "Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura 1 (1)/Front-end-Viticultura-arena-e3ceb4a5-front-end-viticultura"
npm ci
npm run build
cd ../..

# API Python
cd backend/python
python -m pip install -r requirements.txt
python -m pytest -q tests

# API Java (requer JDK 21 e Maven 3.9+)
cd ../java
mvn test
A suíte de persistência Java usa Testcontainers com MySQL e é marcada para ser ignorada quando o Docker não está disponível; os testes unitários podem ser executados sem Docker. Para validar as migrations e a persistência no fluxo sem Docker, mantenha o MySQL Server local ativo e faça o boot da API Java; o Hibernate valida o schema ao iniciar.

10. Variáveis e Dependências Externas
Portas padrão: Frontend 5173, Java 8080, Python 8000, MySQL Server 3306.

Segredos necessários: JWT_SECRET, INITIAL_ADMIN_PASSWORD e INTERNAL_API_KEY, além da senha do usuário local do MySQL. Mantenha os .env reais fora do Git.

Comunicação: Python e Java comunicam-se por localhost; o navegador usa same-origin pelo proxy Vite, com bases diretas configuráveis por VITE_API_JAVA_BASE e VITE_API_PYTHON_BASE.

ThingSpeak: (https://api.thingspeak.com) é opcional, externo e consultado somente pelo backend Java. Não há dependência de backend hospedado ou domínio.

Gerenciadores de Pacotes: npm, PyPI e Maven podem ser acessados para baixar dependências durante a instalação inicial; não são chamadas de runtime da aplicação.

Fontes: As fontes tipográficas são instaladas por npm e servidas localmente pelo frontend.

11. Problemas Comuns
Connection refused na porta 3306: inicie o MySQL Server local e confirme DATABASE_URL, usuário e senha.

Falha de conexão Python → Java: confirme que a API Java responde em http://localhost:8080, que JAVA_API_URL está configurado assim no .env Python e que a chave interna é idêntica nos dois serviços.

JWT ou administrador não configurado: preencha JWT_SECRET e INITIAL_ADMIN_PASSWORD no .env Java antes do primeiro boot; a senha deve cumprir a política do sistema.

Address already in use: libere a porta ou ajuste PORT, VITE_PORT e os destinos DEV_*_API_URL/bases da API correspondentes.

Erro de CORS usando chamada direta: acrescente a origem exata (incluindo porta) a CORS_ALLOWED_ORIGINS nos dois serviços e reinicie-os. Não use * em substituição à lista.

ThingSpeak indisponível: confirme THINGSPEAK_CHANNEL_ID, THINGSPEAK_READ_API_KEY e o acesso à Internet no backend/java/.env e consulte o log do Java (status em /api/integrations/thingspeak/status); isso não impede o boot das APIs.

Tela carrega, mas login falha: confirme que o MySQL Server, Java e Python foram iniciados; consulte os logs do backend e teste /actuator/health e /health.

Frontend: "ENOENT ... package.json" ou "Could not read package.json": o comando npm foi executado na raiz do repositório. Entre na pasta do frontend (seção 6) antes de rodar npm ci ou npm run dev.

Frontend: "cp: cannot stat '.env.example'" na raiz: o .env.example do frontend fica dentro da pasta do frontend, não na raiz. Use o caminho completo mostrado na seção 3.

Frontend: "Vite requires Node.js version 20.19+ or 22.12+": atualize o Node.js e confira com node -v.

Frontend: "Port 5173 is already in use": o Vite usa porta estrita. Libere a porta ou altere VITE_PORT no .env do frontend.

Frontend: as páginas abrem, mas as chamadas /api/... falham com 500 ou ECONNREFUSED: a API Java (8080) ou a Python (8000) não está em execução.

Caminhos com espaços e parênteses: sempre entre aspas nos comandos de terminal.
