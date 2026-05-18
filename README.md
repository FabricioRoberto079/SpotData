# SpotData

API de ingestão e consulta de documentos (texto, PDF, Word, imagem com OCR) com RAG. Stack: FastAPI + PostgreSQL + ChromaDB + LangChain (OpenAI/Google/Anthropic).

---

## Como rodar

> **Importante:** todas as variáveis do `.env.example` são **obrigatórias**. O app falha no boot se faltar qualquer uma — não há mais "modo dev sem auth".

### Via Docker (recomendado)

Sobe Postgres + ChromaDB + API juntos.

1. **Copiar o template de env:**
   ```bash
   cp .env.example .env
   ```

2. **Editar o `.env`** e preencher:
   - `JWT_SECRET` — gere com `openssl rand -hex 32`
   - A API key do provider escolhido em `LLM_CHAT_MODEL` (ex: `OPENAI_API_KEY` se usar `openai:...`)

3. **Subir:**
   ```bash
   docker compose up --build
   ```
   Migrations Alembic rodam automaticamente no startup do container.

4. **Acessar:**
   - API: `http://localhost:8080`
   - Swagger: `http://localhost:8080/docs`

5. **Parar:**
   ```bash
   docker compose down       # mantém os volumes (dados persistem)
   docker compose down -v    # apaga postgres_data e chroma_data também
   ```

### Local (API no host, Postgres + Chroma em container)

Útil pra desenvolver com reload mais rápido e debugger anexado.

1. **Subir só os serviços de dados:**
   ```bash
   docker compose up -d postgres chromadb
   ```

2. **Criar venv e instalar deps:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Instalar dependências de sistema** (usadas pelos extractors):
   - `tesseract-ocr` — OCR de imagens
   - `antiword` — leitura de `.doc` antigos
   - Em Fedora: `sudo dnf install tesseract antiword`
   - Em Debian/Ubuntu: `sudo apt install tesseract-ocr antiword`

4. **Configurar o env:**
   ```bash
   cp .env.example .env
   # edite o .env igual ao passo 2 do modo Docker
   ```
   Confirme que `POSTGRES_HOST=localhost` e `CHROMA_HOST=localhost` (no Docker eles ficam `postgres` e `chromadb`).

5. **Aplicar migrations:**
   ```bash
   alembic upgrade head
   ```

6. **Subir a API:**
   ```bash
   python main.py
   ```
   API em `http://localhost:8080`, com auto-reload do uvicorn.

---

## Fluxo

**Ingestão:** `upload → TextExtractor → TextChunker → embeddings → ChromaDB` (chunks da versão atual marcados `is_latest=true`). Postgres guarda metadata e bytes do arquivo.

**Pergunta:** `POST /chats/messages` → busca semântica no Chroma (top-N chunks) → LLM gera resposta com citações via Pydantic structured output → persiste `Query + Response + EvidenceCitation`. Se o `chat_id` for omitido, o chat é criado na hora com título derivado da pergunta. Histórico das últimas 10 mensagens entra como contexto.

---

## Endpoints

Auth obrigatória (JWT) em tudo, exceto `POST /auth/register`, `POST /auth/login`, `GET /health` e `/docs`.

| Grupo | Rotas |
|---|---|
| Auth | `POST /auth/register` • `POST /auth/login` • `GET /auth/me` |
| Documentos | `GET /documents` (filtrar por `?category=documents\|images\|text`) • `POST /documents/upload` (re-upload do mesmo `file_name` → nova versão automática) • `POST /documents/text` • `GET /documents/search` • `GET DELETE /documents/{id}` • `GET /documents/{id}/download` • `GET /documents/{id}/versions/{n}/download` |
| Pastas de chat | `GET POST /chat-folders` • `PUT DELETE /chat-folders/{id}` |
| Chats | `GET /chats` • `GET PATCH DELETE /chats/{chat_id}` |
| Mensagens | `POST /chats/messages` |

> Não existe `POST /chats` — chat é criado pela primeira mensagem. `PATCH /chats/{id}` permite renomear ou mover de pasta depois.

### Resposta de `POST /chats/messages`
```json
{
  "query_id": "...", "chat_id": "...", "question": "...",
  "status": "success | insufficient_information | not_found | error",
  "answer": "...",
  "citations": [{ "document_id": "...", "version_number": 2, "file_name": "x.pdf", "excerpt": "...", "confidence_score": 0.92 }],
  "time_ms": 1240
}
```

---

## MCP (Model Context Protocol)

O servidor expõe a busca RAG via MCP no endpoint streamable HTTP `/mcp`,
montado no mesmo processo da API. Código isolado em `src/mcp/`:

```
src/mcp/
  __init__.py     # expõe mcp_server e importa tools para registrá-las
  server.py       # instância FastMCP
  auth.py         # SPOTDATA_JWT → user_id
  tools.py        # @tool ask_question
```

**Tool exposta:**

| Tool | Args | Retorno |
|---|---|---|
| `ask_question` | `question`, `chat_id?`, `n_results?` | mesmo payload de `POST /chats/messages` |

**Auth:** o MCP server lê `SPOTDATA_JWT` do ambiente — é o mesmo `access_token`
retornado por `POST /auth/login`. Quando o token expira, gere outro e atualize
a env. Sem `SPOTDATA_JWT`, qualquer chamada à tool falha.

**Configurar:**

```bash
# 1. obter o token
curl -s -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"...","password":"..."}' | jq -r .access_token
# 2. exportar no env do processo da API
export SPOTDATA_JWT=<token>
# 3. (re)subir a API — `/mcp` fica disponível no mesmo host
```

Aponte qualquer cliente MCP (Claude Desktop, etc.) pro endpoint
`http://<host>:8080/mcp`.

---

## Variáveis de ambiente

| Variável | Exemplo | Descrição |
|---|---|---|
| `POSTGRES_USER` / `_PASSWORD` / `_DB` / `_HOST` / `_PORT` | `spotdata` / `spotdata123` / `spotdata` / `localhost` / `5432` | Postgres |
| `CHROMA_HOST` / `_PORT` | `localhost` / `8000` | ChromaDB |
| `LLM_CHAT_MODEL` / `LLM_EMBEDDING_MODEL` | `openai:gpt-4o-mini` / `openai:text-embedding-3-small` | Modelos (formato `<provider>:<model>`) |
| `LLM_STRUCTURED_MODEL` | `openai:gpt-4o-mini` | Opcional — cai no chat model se vazio |
| `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` | — | Preencha a do provider escolhido |
| `JWT_SECRET` | `<openssl rand -hex 32>` | Random string p/ assinar JWT |
| `JWT_ALGORITHM` / `JWT_EXPIRATION_MINUTES` | `HS256` / `60` | Config JWT |
| `CORS_ORIGINS` | `*` ou `https://app.x.com,https://y.com` | Lista por vírgula |
| `LOG_LEVEL` | `INFO` | Logger raiz |

---

## Migrations

```bash
alembic revision --autogenerate -m "descrição"
alembic upgrade head
alembic downgrade -1
```

---

## Pendências

- Object storage (S3/MinIO) — hoje arquivos são `LargeBinary` no Postgres
- Testes automatizados
- Rate limiting no endpoint de LLM
- CI (lint, type-check, tests)
- Autorização granular (ACL por documento/pasta/chat)
