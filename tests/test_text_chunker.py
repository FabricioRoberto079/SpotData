from src.services.text_chunker import TextChunker


def test_empty_text_returns_empty_list():
    assert TextChunker().chunk("") == []
    assert TextChunker().chunk("   ") == []


def test_short_text_returns_single_chunk():
    chunker = TextChunker(max_chars=100, overlap=10)
    result = chunker.chunk("texto curto")
    assert result == ["texto curto"]


def test_splits_long_text_into_multiple_chunks():
    chunker = TextChunker(max_chars=80, overlap=15)
    paragraphs = [f"Parágrafo número {i} com algum conteúdo." for i in range(20)]
    text = "\n\n".join(paragraphs)
    chunks = chunker.chunk(text)
    assert len(chunks) >= 2
    assert all(len(c) <= 80 + 15 for c in chunks)


def test_paragraphs_grouped_when_below_max():
    chunker = TextChunker(max_chars=200, overlap=20)
    text = "Para 1.\n\nPara 2.\n\nPara 3."
    assert chunker.chunk(text) == [text]
