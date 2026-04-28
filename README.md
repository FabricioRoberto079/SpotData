# SpotData

API de ingestão e busca semântica de documentos (texto, PDF e imagens) usando **FastAPI**, **PostgreSQL** e **ChromaDB**.

O fluxo principal:

1. Usuário envia um arquivo (PDF, imagem ou texto).
2. O texto é extraído (pypdf para PDFs, Tesseract OCR para imagens).
3. O conteúdo original e o texto extraído ficam no Postgres.
4. O texto é vetorizado e indexado no ChromaDB para busca semântica.
5. Buscas retornam os trechos mais relevantes com referência ao documento original.

---

## Stack

- **Python 3.12+**
- **FastAPI** — API HTTP
- **SQLAlchemy + Alembic** — ORM e migrations
- **PostgreSQL 16** — armazenamento dos documentos e metadados
- **ChromaDB 1.5.7** — banco vetorial para busca semântica
- **pypdf** — extração de texto de PDFs
- **pytesseract / Pillow** — OCR de imagens

---

## Estrutura

```
SpotData/
├── alembic/                  # Migrations do banco
├── src/
│   ├── Controller/           # Endpoints HTTP (FastAPI routers)
│   ├── Data/                 # Clients de Postgres e ChromaDB
│   ├── Enums/                # Enums (ContentType, ResponseStatus, etc.)
│   ├── Integrations/         # Integrações externas (OpenAI, etc.)
│   ├── Models/               # Modelos SQLAlchemy
│   └── Services/             # Regras de negócio (extração, vetorização)
├── docker-compose.yml        # Postgres + ChromaDB
├── alembic.ini
├── main.py                   # Entry point da API
└── requirements.txt
```

---

## Como rodar

### 1. Subir Postgres e ChromaDB

```bash
docker compose up -d
```

### 2. Instalar dependências

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar variáveis de ambiente

Crie um arquivo `.env` na raiz:

```env
POSTGRES_USER=spotdata
POSTGRES_PASSWORD=spotdata123
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=spotdata

CHROMA_HOST=localhost
CHROMA_PORT=8000
```

### 4. Aplicar migrations

```bash
alembic upgrade head
```

### 5. Subir a API

```bash
python main.py
```

A API fica disponível em `http://localhost:8080`. A documentação interativa em `http://localhost:8080/docs`.

---

## Endpoints principais

| Método | Rota                | Descrição                                       |
|--------|---------------------|-------------------------------------------------|
| GET    | `/health`           | Healthcheck                                     |
| POST   | `/documents/upload` | Upload de arquivo (PDF, imagem, txt)            |
| POST   | `/documents/text`   | Ingestão de texto puro                          |
| GET    | `/documents/search` | Busca semântica (`?q=...&n_results=3`)          |

---

## Migrations (Alembic)

Criar uma nova migration a partir das alterações nos models:

```bash
alembic revision --autogenerate -m "descrição da mudança"
```

Aplicar todas as migrations pendentes:

```bash
alembic upgrade head
```

Reverter a última:

```bash
alembic downgrade -1
```

---

## Trabalhando com branches

Este projeto usa **trunk-based development** com branches de feature curtas. A branch principal é `main`.

### Padrão de nomes

```
<tipo>/<descrição-curta-em-kebab-case>
```

Tipos comuns:

- `feat/` — nova funcionalidade (ex.: `feat/add-config-database`)
- `fix/` — correção de bug (ex.: `fix/ocr-empty-result`)
- `refactor/` — refatoração sem mudança de comportamento
- `docs/` — apenas documentação
- `chore/` — tarefas de infra, dependências, configs

### Criar uma branch nova

Sempre parta da `main` atualizada:

```bash
# 1. Voltar para main e atualizar
git checkout main
git pull origin main

# 2. Criar a nova branch a partir de main
git checkout -b feat/nome-da-feature

# 3. Trabalhar normalmente
git add .
git commit -m "feat: descrição da mudança"

# 4. Subir a branch para o remote (primeira vez)
git push -u origin feat/nome-da-feature

# Pushes seguintes
git push
```

### Mensagens de commit

Seguimos [Conventional Commits](https://www.conventionalcommits.org/):

```
<tipo>: <descrição no imperativo>
```

Exemplos:

- `feat: adiciona endpoint de busca por id`
- `fix: corrige erro de OCR em imagens TIFF`
- `refactor: extrai client do ChromaDB para módulo próprio`
- `docs: atualiza README com instruções de migration`

### Abrir um Pull Request

1. Garanta que sua branch está atualizada com `main`:
   ```bash
   git checkout main
   git pull origin main
   git checkout feat/sua-branch
   git rebase main
   ```
2. Resolva eventuais conflitos e force-push (apenas em branch própria):
   ```bash
   git push --force-with-lease
   ```
3. Abra o PR pelo GitHub apontando para `main`.
4. Após o merge, apague a branch local:
   ```bash
   git checkout main
   git pull origin main
   git branch -d feat/sua-branch
   ```

### Boas práticas

- **Branches curtas**: prefira PRs pequenos e focados — fáceis de revisar e mais rápidos para mergear.
- **Não commite em `main` direto** — sempre via PR.
- **Não commite o `.env`** — já está no `.gitignore`.
- **Rode as migrations antes de subir mudanças nos models** para garantir que o `autogenerate` funcionou corretamente.
