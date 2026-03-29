from dotenv import load_dotenv

load_dotenv()

from src.Data.postgres_client import engine, Base
from src.Enums.content_type import ContentType
from src.Models.spot import Spot
from src.Services.vector_service import insert, search


def main():
    # Cria as tabelas no Postgres (se não existirem)
    Base.metadata.create_all(bind=engine)

    # Exemplo: inserir um PDF
    # doc_id = insert("caminho/do/arquivo.pdf", content_type=ContentType.PDF, source_name="contrato.pdf")

    # Exemplo: inserir uma foto (OCR)
    # doc_id = insert("caminho/da/foto.png", content_type=ContentType.FOTO, source_name="nota-fiscal.png")

    # Exemplo: inserir texto puro
    # doc_id = insert("caminho/do/texto.txt", content_type=ContentType.TEXTO, source_name="anotacao.txt")

    # Exemplo: buscar
    results = search("onde está o contrato?")
    for r in results:
        print(f"[{r['distance']:.4f}] {r['source_name']} ({r['content_type']})")
        print(f"  {r['document'][:200]}")
        print()


if __name__ == "__main__":
    main()
