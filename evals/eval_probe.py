"""Sonda detalhada: ver exatamente o que o pipeline faz com perguntas suspeitas."""
from __future__ import annotations

import asyncio

from src.data.postgres_client import SessionLocal
from src.integrations.llm import get_llm_client
from src.prompts.rag_prompt import RagAnswer, build_messages
from src.services.chat_service import MIN_CITATION_CONFIDENCE, RAG_TOP_K
from src.services.text_chunker import get_text_chunker
from src.services.vector_index_service import VectorIndexService

PROBES = [
    "Qual a velocidade da luz no vácuo?",
    "Quem foi Alan Turing?",            # nome que pode aparecer no livro de SO
    "Qual a fórmula química da água?",
]


async def last(llm, msgs, schema):
    out = None
    async for p in llm.chat_stream_structured(msgs, schema):
        out = p
    return out if isinstance(out, dict) else (out.model_dump() if out else {})


async def main():
    s = SessionLocal()
    try:
        llm = get_llm_client()
        vix = VectorIndexService(s, get_text_chunker(), llm)
        for q in PROBES:
            print("\n" + "=" * 70)
            print("PERGUNTA:", q)
            ctx = vix.search(q, RAG_TOP_K, None, None)
            snap = await last(llm, build_messages(q, ctx), RagAnswer)
            ans = (snap.get("answer") or "").strip()
            raw = snap.get("citations") or []
            print(f"  contextos recuperados: {len(ctx)}")
            print(f"  citações brutas do LLM: {raw}")
            kept = [c for c in raw if isinstance(c, dict)
                    and isinstance(c.get('context_index'), int)
                    and 0 <= c['context_index'] < len(ctx)
                    and (c.get('confidence') or 0) >= MIN_CITATION_CONFIDENCE]
            print(f"  citações que passaram do 0.6: {kept}")
            print(f"  RESPOSTA: {ans[:500] if ans else '(vazia)'}")
            decision = "ANSWER" if (ans and kept) else "ABSTAIN"
            print(f"  >>> DECISÃO: {decision}")
            for c in kept:
                idx = c['context_index']
                print(f"  --- trecho citado [{idx}] (conf={c.get('confidence')}): "
                      f"{ctx[idx].get('snippet','')[:220]}")
    finally:
        s.close()


if __name__ == "__main__":
    asyncio.run(main())
