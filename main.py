from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI

from src.Controller.document_controller import router as document_router
from src.Data.postgres_client import engine
from src.Models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="SpotData API",
    description="Ingestao e busca semantica de documentos (texto, imagem, PDF)",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(document_router)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
