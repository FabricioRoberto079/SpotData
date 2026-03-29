import chromadb
from chromadb.config import Settings
import os


def get_chroma_client() -> chromadb.HttpClient:
    host = os.getenv("CHROMA_HOST", "localhost")
    port = int(os.getenv("CHROMA_PORT", "8000"))
    return chromadb.HttpClient(host=host, port=port)
