import logging
import os
import shutil
from contextlib import asynccontextmanager

import defusedxml
from dotenv import load_dotenv

# Patch stdlib XML parsers (used transitively by python-docx, pypdf, langchain) so
# malicious DOCX/PDF uploads can't trigger XXE or billion-laughs attacks.
defusedxml.defuse_stdlib()

load_dotenv()

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.auth import limiter
from src.controllers.auth_controller import router as auth_router
from src.controllers.chat_controller import router as chat_router
from src.controllers.document_controller import router as document_router
from src.controllers.folder_controller import chat_folder_router
from src.exceptions import DomainError
from src.integrations.llm import LlmError
from src.logging_config import setup_logging
from src.mcp import mcp_server
from src.schemas.system import HealthResponse

setup_logging()


_REQUIRED_SYSTEM_BINARIES = ("tesseract", "antiword")


def _check_system_dependencies() -> None:
    log = logging.getLogger("spotdata.bootstrap")
    missing = [b for b in _REQUIRED_SYSTEM_BINARIES if shutil.which(b) is None]
    if missing:
        log.warning(
            "Ferramentas de sistema ausentes no PATH: %s. "
            "Os uploads que dependem delas vão falhar. "
            "Veja a seção 'Instalar dependências de sistema' no README.",
            ", ".join(missing),
        )


_check_system_dependencies()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp_server.session_manager.run():
        yield

API_DESCRIPTION = """\
SpotData — ingest, organize and query documents using RAG.

**Pipeline:** upload (text / PDF / image with OCR / Word) -> chunking -> embeddings
-> Postgres + pgvector -> semantic search -> structured-output LLM -> response with citations.
Chat model and embedding model are configured via `LLM_CHAT_MODEL` /
`LLM_EMBEDDING_MODEL` (LangChain format: `<provider>:<model>`).

## Authentication

JWT is required on every endpoint except:

- `POST /auth/register` and `POST /auth/login`
- `GET /health`
- `GET /docs`, `GET /redoc`, `GET /openapi.json`

To use Swagger UI: click **Authorize**, log in via `/auth/login` in another
tab and paste the returned `access_token`.
"""

app = FastAPI(
    title="SpotData API",
    description=API_DESCRIPTION,
    version="0.1.0",
    contact={"name": "SpotData"},
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

cors_origins = os.getenv("CORS_ORIGINS")
if not cors_origins:
    raise RuntimeError("Missing required env var: CORS_ORIGINS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(document_router)
app.include_router(chat_folder_router)
app.include_router(chat_router)

mcp_app = mcp_server.streamable_http_app()


@app.exception_handler(DomainError)
async def _domain_error_handler(request: Request, exc: DomainError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


@app.exception_handler(LlmError)
async def _llm_error_handler(request: Request, exc: LlmError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": {"kind": exc.kind, "message": exc.detail}},
    )


mcp_app.add_exception_handler(DomainError, _domain_error_handler)
mcp_app.add_exception_handler(LlmError, _llm_error_handler)
app.mount("/mcp", mcp_app)


@app.get(
    "/health",
    tags=["system"],
    response_model=HealthResponse,
    summary="Healthcheck",
)
async def health():
    return {"status": "ok"}


_PUBLIC_OPERATIONS = {
    ("post", "/auth/register"),
    ("post", "/auth/login"),
    ("get", "/health"),
}


def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        contact=app.contact,
    )
    schema.setdefault("components", {}).setdefault("securitySchemes", {})[
        "BearerAuth"
    ] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": "Paste the `access_token` returned by `/auth/login`.",
    }

    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            if (method, path) in _PUBLIC_OPERATIONS:
                continue
            op.setdefault("security", [{"BearerAuth": []}])

    schema["tags"] = [
        {"name": "auth", "description": "Registration, login and current-user introspection."},
        {"name": "documents", "description": "Upload, versioning and semantic search."},
        {"name": "chat-folders", "description": "Folder tree for chats."},
        {"name": "chats", "description": "Conversations and RAG messages (search + LLM + citations)."},
        {"name": "system", "description": "Healthcheck and utilities."},
    ]

    app.openapi_schema = schema
    return schema


app.openapi = _custom_openapi


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
