"""
Harness de avaliação do filtro anti-alucinação do SpotData.

Roda o PIPELINE REAL (embeddings + busca híbrida pgvector + LLM estruturado +
filtro MIN_CITATION_CONFIDENCE=0.6) sem gravar nada no banco, e mede:

  - Recusa correta  (perguntas FORA da base que o sistema corretamente NÃO responde)
  - Recusa falsa    (perguntas COM resposta na base que o sistema recusa à toa)
  - Alucinação      (respostas dadas que NÃO são sustentadas pelos trechos citados)

Uso:  .venv/bin/python eval_antialucinacao.py
"""
from __future__ import annotations

import asyncio
import json
import time

from pydantic import BaseModel, Field

from src.data.postgres_client import SessionLocal
from src.integrations.llm import get_llm_client
from src.prompts.rag_prompt import RagAnswer, build_messages
from src.services.chat_service import MIN_CITATION_CONFIDENCE, RAG_TOP_K
from src.services.text_chunker import get_text_chunker
from src.services.vector_index_service import VectorIndexService

# category_id=None => busca em TODAS as categorias (corpus inteiro).
SCOPE_CATEGORY_ID = None

# -------------------- Conjunto de teste rotulado --------------------
# Perguntas COM resposta na base (Tanenbaum "Sistemas Operacionais Modernos"
# + "Codigo-de-Conduta-Starian" + "Porcentagem no cotidiano"). Esperado: RESPONDE.
IN_CORPUS = [
    "O que é um processo em um sistema operacional?",
    "O que é um deadlock (impasse) e quais condições são necessárias para ele ocorrer?",
    "O que é memória virtual?",
    "O que é escalonamento de processos (scheduling)?",
    "O que é uma thread e como ela difere de um processo?",
    "O que é paginação de memória?",
    "Para que serve um sistema de arquivos?",
    "Como funciona o algoritmo de escalonamento round-robin?",
    "Qual é o objetivo do código de conduta da Starian?",
    "Como a porcentagem é utilizada no cotidiano?",
]

# Perguntas FORA da base (conhecimento geral, sem relação com os documentos).
# Esperado: RECUSA (não sei).
OUT_OF_CORPUS = [
    "Qual é a capital da Austrália?",
    "Quem venceu a Copa do Mundo de futebol de 2022?",
    "Qual é a receita de um bolo de cenoura?",
    "Quanto custa um iPhone 15 Pro no Brasil?",
    "Quais são os sintomas da dengue?",
    "Qual a altura do Monte Everest?",
    "Como trocar o pneu de um carro?",
    "Quem pintou a Mona Lisa?",
    "Qual é a população atual do Japão?",
    "Quais são os ingredientes de uma feijoada tradicional?",
]


class GroundingVerdict(BaseModel):
    """Veredito do juiz sobre se a resposta é sustentada pelos trechos citados."""
    grounded: bool = Field(
        description="True se TODA afirmação factual da RESPOSTA é sustentada pelos "
        "TRECHOS fornecidos; False se houver qualquer afirmação sem suporte."
    )
    reason: str = Field(description="Justificativa curta (1 frase).")


def _clamp_confidence(raw) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return max(0.0, min(1.0, value))


def _surviving_citations(raw_citations, n_contexts):
    """Replica MIN_CITATION_CONFIDENCE + validação de índice + dedupe
    (mesma regra de chat_service._build_and_persist_citations, sem persistir)."""
    kept, seen = [], set()
    for c in raw_citations or []:
        if not isinstance(c, dict):
            continue
        idx = c.get("context_index")
        if not isinstance(idx, int) or idx < 0 or idx >= n_contexts:
            continue
        conf = _clamp_confidence(c.get("confidence"))
        if conf is None or conf < MIN_CITATION_CONFIDENCE:
            continue
        if idx in seen:
            continue
        seen.add(idx)
        kept.append({"context_index": idx, "confidence": conf})
    return kept


async def _structured_last(llm, messages, schema):
    """Consome o stream estruturado e devolve o último snapshot (dict)."""
    last = None
    async for partial in llm.chat_stream_structured(messages, schema):
        last = partial
    if last is None:
        return {}
    if isinstance(last, dict):
        return last
    if hasattr(last, "model_dump"):
        return last.model_dump()
    return {}


async def run_question(llm, vix, question):
    """Replica fielmente a decisão de ask_stream (sem escrever no banco)."""
    contexts = vix.search(question, RAG_TOP_K, None, SCOPE_CATEGORY_ID)
    if not contexts:
        return {"decision": "ABSTAIN", "reason": "sem contexto recuperado",
                "answer": "", "citations": [], "contexts": []}

    messages = build_messages(question, contexts)
    snap = await _structured_last(llm, messages, RagAnswer)
    answer = (snap.get("answer") or "").strip() if isinstance(snap, dict) else ""
    raw_cits = snap.get("citations") if isinstance(snap, dict) else []
    cits = _surviving_citations(raw_cits, len(contexts))

    # Regra de produção: só é "resposta" se sobrou citação E há texto.
    decision = "ANSWER" if (answer and cits) else "ABSTAIN"
    return {"decision": decision, "answer": answer, "citations": cits,
            "contexts": contexts}


async def judge_grounding(llm, question, answer, cited_snippets):
    block = "\n\n".join(f"[trecho {i}] {s}" for i, s in enumerate(cited_snippets))
    messages = [
        {"role": "system", "content":
            "Você é um avaliador rigoroso de alucinação em RAG. Dada uma PERGUNTA, "
            "uma RESPOSTA e os TRECHOS que a embasam, decida se TODA afirmação "
            "factual da RESPOSTA está sustentada pelos TRECHOS. Se qualquer "
            "afirmação não tiver suporte direto, grounded=false."},
        {"role": "user", "content":
            f"PERGUNTA: {question}\n\nRESPOSTA:\n{answer}\n\nTRECHOS:\n{block}"},
    ]
    verdict = await _structured_last(llm, messages, GroundingVerdict)
    return bool(verdict.get("grounded")), verdict.get("reason", "")


async def main():
    session = SessionLocal()
    try:
        llm = get_llm_client()
        vix = VectorIndexService(session, get_text_chunker(), llm)

        results = []
        cases = ([("in", q) for q in IN_CORPUS] +
                 [("out", q) for q in OUT_OF_CORPUS])

        for label, q in cases:
            t0 = time.perf_counter()
            r = await run_question(llm, vix, q)
            r["label"], r["question"] = label, q
            r["time_ms"] = int((time.perf_counter() - t0) * 1000)

            # Juiz de alucinação só nas que RESPONDERAM.
            r["grounded"] = None
            if r["decision"] == "ANSWER":
                snippets = [r["contexts"][c["context_index"]].get("snippet", "")
                            for c in r["citations"]]
                grounded, why = await judge_grounding(llm, q, r["answer"], snippets)
                r["grounded"], r["grounded_reason"] = grounded, why

            results.append(r)
            mark = {"ANSWER": "responde", "ABSTAIN": "recusa"}[r["decision"]]
            g = "" if r["grounded"] is None else (
                " | grounded=OK" if r["grounded"] else " | ⚠️ALUCINOU")
            print(f"[{label:>3}] {mark:>8}{g}  ({r['time_ms']}ms)  {q[:60]}")

        # -------------------- métricas --------------------
        ins = [r for r in results if r["label"] == "in"]
        outs = [r for r in results if r["label"] == "out"]
        answered = [r for r in results if r["decision"] == "ANSWER"]

        out_correct = sum(1 for r in outs if r["decision"] == "ABSTAIN")
        in_answered = sum(1 for r in ins if r["decision"] == "ANSWER")
        in_false_refusal = sum(1 for r in ins if r["decision"] == "ABSTAIN")
        halluc = sum(1 for r in answered if r["grounded"] is False)

        def pct(a, b):
            return f"{(100.0 * a / b):.0f}%" if b else "n/a"

        print("\n" + "=" * 60)
        print("RESULTADOS — FILTRO ANTI-ALUCINAÇÃO (medido no pipeline real)")
        print("=" * 60)
        print(f"Perguntas COM base : {len(ins)}   |  FORA da base: {len(outs)}")
        print("-" * 60)
        print(f"Recusa correta (fora da base) : {out_correct}/{len(outs)}  "
              f"= {pct(out_correct, len(outs))}   << anti-alucinação")
        print(f"Respondeu corretamente (na base): {in_answered}/{len(ins)}  "
              f"= {pct(in_answered, len(ins))}")
        print(f"Recusa falsa (na base)         : {in_false_refusal}/{len(ins)}  "
              f"= {pct(in_false_refusal, len(ins))}")
        print(f"Alucinação (respostas s/ suporte): {halluc}/{len(answered)}  "
              f"= {pct(halluc, len(answered))}")
        grounded_ok = sum(1 for r in answered if r["grounded"] is True)
        print(f"Respostas fiéis à fonte         : {grounded_ok}/{len(answered)}  "
              f"= {pct(grounded_ok, len(answered))}")
        print("=" * 60)

        with open("eval_antialucinacao_resultados.json", "w") as f:
            slim = [{k: v for k, v in r.items() if k != "contexts"}
                    for r in results]
            json.dump({"min_citation_confidence": MIN_CITATION_CONFIDENCE,
                       "rag_top_k": RAG_TOP_K, "results": slim}, f,
                      ensure_ascii=False, indent=2)
        print("Detalhes por pergunta salvos em eval_antialucinacao_resultados.json")
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
