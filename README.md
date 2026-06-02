# SpotData

API de ingestão e consulta de documentos (texto, PDF, Word, imagem com OCR) com RAG. Stack: FastAPI + PostgreSQL (com extensão pgvector) + LangChain (OpenAI/Google/Anthropic).

---

## Como rodar

> **Importante:** todas as variáveis do `.env.example` são **obrigatórias**. O app falha no boot se faltar qualquer uma — não há mais "modo dev sem auth".

### Via Docker (recomendado)

Sobe Postgres (com pgvector) + API juntos.

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
   docker compose down -v    # apaga postgres_data também
   ```

### Local (API no host, Postgres em container)

Útil pra desenvolver com reload mais rápido e debugger anexado.

1. **Subir só o Postgres:**
   ```bash
   docker compose up -d postgres
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
   Confirme que `POSTGRES_HOST=localhost` (no Docker fica `postgres`).

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

**Ingestão:** `upload → TextExtractor → TextChunker → embeddings → tabela vector_chunks (pgvector)` (chunks da versão atual marcados `is_latest=true`, com `tsv` populado para BM25). Postgres guarda metadata e bytes do arquivo (`document_versions.file_data`).

**Pergunta:** `POST /chats/messages` →
1. **QA cache**: lookup exato por hash da pergunta normalizada; se miss, embed da pergunta + lookup semântico (pgvector) em `qa_cache_entries`. Cache hit serve a resposta direto sem chamar o LLM.
2. **Busca híbrida** (`RAG_TOP_K=10` chunks): cosine distance via pgvector + BM25 via `ts_rank_cd` (Portuguese FTS), fundidos por **Reciprocal Rank Fusion** (`HYBRID_CANDIDATE_K=60` de cada lado, `RRF_K=60`).
3. **LLM** (structured output `RagAnswer` via OpenAI strict `json_schema`): devolve `{citations:[{context_index, confidence}], answer}`. O schema tem `citations` **antes** de `answer` — o decoding constrained emite primeiro o array de citações e depois o texto da resposta.
4. **Stream NDJSON** (`text/event-stream`, um JSON por linha): emite `meta` → `citations` (logo que o LLM fecha o array, antes da resposta) → `token` (deltas reais token-a-token via langchain `JsonOutputParser`) → `done`.
5. **Persistência**: `Query + Response + EvidenceCitation`. Citações com `confidence < MIN_CITATION_CONFIDENCE` (0.6) são descartadas. Se nenhuma citação sobrevive, o stream para antes de emitir qualquer token → `insufficient_information` (não há resposta sem fonte).
6. **QA cache write-through**: respostas `success` viram entrada no cache pra acelerar perguntas futuras.

Histórico das últimas 10 mensagens entra como contexto (turnos sem resposta válida são pulados). Saudações/chitchat/fora-do-corpus → `answer=""`, `citations=[]`, `status=insufficient_information` (sem `token` events).

---

## Endpoints

Auth obrigatória (JWT) em tudo, exceto `POST /auth/register`, `POST /auth/login`, `GET /health` e `/docs`.

| Grupo | Rotas |
|---|---|
| Auth | `POST /auth/register` • `POST /auth/login` • `GET /auth/me` |
| Admin (só `admin`) | `GET POST /admin/categories` • `PATCH DELETE /admin/categories/{id}` • `GET /admin/users` • `PATCH /admin/users/{id}/role` • `PATCH /admin/users/{id}/active` • `GET POST /admin/users/{id}/categories` • `DELETE /admin/users/{id}/categories/{cat_id}` |
| Documentos | `GET /documents` (filtrar por `?category_id=`) • `POST /documents/upload` (campos `kind` = `file\|image\|text` e `category_id` obrigatório; re-upload do mesmo `file_name` → nova versão automática) • `GET /documents/search` • `GET DELETE /documents/{id}` • `GET /documents/{id}/download` • `GET /documents/{id}/versions/{n}/download` |
| Pastas de chat | `GET POST /chat-folders` • `PUT DELETE /chat-folders/{id}` |
| Chats | `GET /chats` • `GET PATCH DELETE /chats/{chat_id}` |
| Mensagens | `POST /chats/messages` |

> Não existe `POST /chats` — chat é criado pela primeira mensagem. `PATCH /chats/{id}` permite renomear ou mover de pasta depois.

### Papéis e acesso por categoria

Três papéis (`users.role`): **`admin`** (cria categorias, gerencia usuários e vincula usuários ↔ categorias), **`editor`** (sobe e consulta documentos) e **`viewer`** (só consulta). Quem se registra por `POST /auth/register` nasce `viewer` já vinculado à categoria default **`GERAL`** — o admin concede acesso a outras categorias depois.

Categorias são normalizadas na criação: acentos e caracteres especiais removidos, espaços internos viram `_`, pontas aparadas, salvas em UPPERCASE (ex.: `"  Recursos   Humanos! "` → `RECURSOS_HUMANOS`). O `slug` é a versão minúscula, usado como chave única.

Documentos pertencem a uma categoria. Listagem, busca (`/documents/search`) e RAG do chat só enxergam as categorias vinculadas ao usuário; o admin vê tudo. O upload exige um `category_id` ao qual o usuário tenha acesso e papel `editor`/`admin`.

> **Bootstrap do admin:** a migração não tem como saber quem é admin. Depois de migrar, promova um usuário manualmente:
> ```sql
> UPDATE users SET role = 'admin' WHERE email = 'voce@exemplo.com';
> ```
> Sem isso ninguém consegue criar categorias.

### Resposta de `POST /chats/messages` (NDJSON stream)

Content-Type: `text/event-stream`. Cada linha do corpo é um **objeto JSON inteiro** (uma linha = um evento — não usa o formato SSE `data:` / `event:`). Eventos possíveis:

| `type` | Quando | Payload |
|---|---|---|
| `meta` | sempre, primeiro evento | `chat_id`, `query_id`, `response_id` |
| `citations` | uma vez, **antes** dos tokens | `citations` (array completo de objetos resolvidos com `document_id`, `document_version_id`, `version_number`, `file_name`, `page`, `excerpt`, `confidence_score`, `download_url`) |
| `token` | deltas token-a-token do `answer` (texto crescendo) | `content` |
| `done` | sempre, último evento | `status` (`success` \| `insufficient_information` \| `error`), `time_ms` |
| `error` | só em falha de LLM | `kind`, `message` |

**Gates:**
1. **Sem contexto** — se a busca híbrida não retorna chunk algum, devolve `insufficient_information` sem chamar o LLM.
2. **Sem citação fundamentada** — se nenhuma citação sobrevive ao filtro `MIN_CITATION_CONFIDENCE=0.6` (saudações, chitchat, pergunta fora dos docs), o stream é interrompido antes de qualquer `token` e devolve `insufficient_information`. Como as citações vêm antes do `answer` no schema, isso é detectado sem vazar texto.

**Exemplo (sucesso):**
```
{"type":"meta","chat_id":"...","query_id":"...","response_id":"..."}
{"type":"citations","citations":[{"document_id":"...","page":4,"excerpt":"...","confidence_score":0.93,"file_name":"x.pdf","download_url":"/documents/.../download"}]}
{"type":"token","content":"A "}
{"type":"token","content":"==**meta**=="}
{"type":"token","content":" de "}
{"type":"token","content":"2026..."}
{"type":"done","status":"success","time_ms":1840}
```

**Exemplo (sem fundamento nos docs):**
```
{"type":"meta",...}
{"type":"citations","citations":[]}
{"type":"done","status":"insufficient_information","time_ms":210}
```

> Em `insufficient_information` nenhum `token` é emitido. O frontend renderiza estado vazio baseado no `status` do `done`.

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
| `ask_question` | `question`, `chat_id?` | dict com `chat_id`, `query_id`, `response_id`, `question`, `status`, `answer`, `citations`, `time_ms` |

**Auth:** cada chamada precisa de um `Authorization: Bearer <JWT>` no request HTTP do MCP — o mesmo `access_token` retornado por `POST /auth/login`. O `user_id` sai do `sub` do token. Não há fallback de env var.

**Configurar:**

```bash
# 1. obter o token
curl -s -X POST http://localhost:8080/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"...","password":"..."}' | jq -r .access_token
# 2. apontar o cliente MCP pra http://<host>:8080/mcp com o header
#    Authorization: Bearer <token-do-passo-1>
```

Aponte qualquer cliente MCP (Claude Desktop, etc.) pro endpoint `http://<host>:8080/mcp` enviando o Bearer token.

---

## Variáveis de ambiente

| Variável | Exemplo | Descrição |
|---|---|---|
| `POSTGRES_USER` / `_PASSWORD` / `_DB` / `_HOST` / `_PORT` | `spotdata` / `spotdata123` / `spotdata` / `localhost` / `5432` | Postgres (com extensão pgvector). A migration `e5f6a7b8c9d0` cria `CREATE EXTENSION vector` na primeira execução. |
| `LLM_CHAT_MODEL` / `LLM_EMBEDDING_MODEL` | `openai:gpt-4o-mini` / `openai:text-embedding-3-large` | Modelos (formato `<provider>:<model>`). Trocar de embedding model exige re-indexar todo o corpus (dimensões diferentes). |
| `EMBEDDING_DIMENSION` | `3072` (text-embedding-3-large) / `1536` (3-small ou ada-002) / `768` (google text-embedding-004) | Dimensão do vetor armazenado em `vector_chunks.embedding` e `qa_cache_entries.embedding`. Deve casar com o modelo de embedding. |
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
- Rate limiting no endpoint de LLM
- CI (lint, type-check, tests)
- Autorização granular (ACL por documento/pasta/chat)
