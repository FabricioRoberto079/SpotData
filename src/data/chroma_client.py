import os

import chromadb
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def get_chroma_client() -> chromadb.HttpClient:
    host = _required("CHROMA_HOST")
    port = int(_required("CHROMA_PORT"))
    return chromadb.HttpClient(host=host, port=port)
