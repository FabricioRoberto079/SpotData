"""
Harness v3 — medição honesta e profunda do anti-alucinação.

Diferenças do v2:
  - REPETE cada pergunta N vezes (capta o não-determinismo do LLM).
  - Zona "ADJACENTE-DIFÍCIL": perguntas cujos termos APARECEM no corpus mas a
    resposta correta NÃO está coberta — é onde mora a alucinação por síntese.
  - JULGA o grounding de TODA resposta dada (não só de um bloco).
  - Salva as respostas alucinadas pra inspeção manual.

Métricas: recusa fora-da-base, fidelidade no núcleo, taxa de alucinação global,
e estabilidade (quantas perguntas dão sempre a mesma decisão em N repetições).

Uso:  .venv/bin/python eval_antialucinacao_v3.py
"""
from __future__ import annotations

import asyncio
import json
from collections import Counter

from pydantic import BaseModel, Field

from src.data.postgres_client import SessionLocal
from src.integrations.llm import get_llm_client
from src.prompts.rag_prompt import RagAnswer, build_messages
from src.services.chat_service import MIN_CITATION_CONFIDENCE, RAG_TOP_K
from src.services.text_chunker import get_text_chunker
from src.services.vector_index_service import VectorIndexService

REPS = 3

CORE = [
    "O que é um processo em um sistema operacional?",
    "O que é um deadlock (impasse)?",
    "O que é memória virtual?",
    "O que é uma thread?",
    "Como funciona o escalonamento round-robin?",
    "O que é paginação de memória?",
    "Para que serve um sistema de arquivos?",
    "O que é um semáforo em sistemas operacionais?",
]
ADJACENT = [
    "Quem foi Alan Turing?",
    "Quem criou o CERT?",
    "O que foi o verme de Morris?",
    "Quem foi Konrad Zuse?",
    "Quando foi construído o primeiro computador digital?",
    "O que aconteceu em Bletchley Park?",
    "Qual a biografia de Linus Torvalds?",
    "Quem inventou o sistema operacional UNIX e em que ano?",
]
OUT = [
    "Qual é a capital da França?",
    "Quem escreveu Dom Casmurro?",
    "Quantos planetas tem o sistema solar?",
    "Qual a moeda oficial do Japão?",
    "Em que ano o homem pisou na Lua?",
    "Qual o maior oceano do planeta?",
    "Como se faz pão caseiro?",
    "Quem ganhou o Oscar de melhor filme em 2020?",
]


class Verdict(BaseModel):
    grounded: bool = Field(description="True só se TODA afirmação factual da "
                           "RESPOSTA é diretamente sustentada pelos TRECHOS.")
    reason: str = Field(description="Justificativa curta.")


def _clamp(r):
    try:
        v = float(r)
    except (TypeError, ValueError):
        return None
    return None if v != v else max(0.0, min(1.0, v))


def _surv(raw, n):
    kept, seen = [], set()
    for c in raw or []:
        if not isinstance(c, dict):
            continue
        i = c.get("context_index")
        cf = _clamp(c.get("confidence"))
        if (isinstance(i, int) and 0 <= i < n and cf is not None
                and cf >= MIN_CITATION_CONFIDENCE and i not in seen):
            seen.add(i)
            kept.append({"i": i, "cf": cf})
    return kept


async def _last(llm, msgs, schema):
    out = None
    async for p in llm.chat_stream_structured(msgs, schema):
        out = p
    return out if isinstance(out, dict) else (out.model_dump() if out else {})


async def ask(llm, vix, q):
    ctx = vix.search(q, RAG_TOP_K, None, None)
    if not ctx:
        return "ABSTAIN", "", [], ctx
    snap = await _last(llm, build_messages(q, ctx), RagAnswer)
    ans = (snap.get("answer") or "").strip() if isinstance(snap, dict) else ""
    cits = _surv(snap.get("citations") if isinstance(snap, dict) else [], len(ctx))
    return ("ANSWER" if (ans and cits) else "ABSTAIN"), ans, cits, ctx


async def judge(llm, q, ans, snippets):
    block = "\n\n".join(f"[trecho {i}] {s}" for i, s in enumerate(snippets))
    v = await _last(llm, [
        {"role": "system", "content":
            "Avaliador rigoroso de alucinação. Dada PERGUNTA, RESPOSTA e TRECHOS, "
            "responda grounded=true só se CADA afirmação factual da RESPOSTA tiver "
            "suporte DIRETO nos TRECHOS. Conhecimento geral correto mas ausente "
            "dos trechos => grounded=false."},
        {"role": "user", "content":
            f"PERGUNTA: {q}\n\nRESPOSTA:\n{ans}\n\nTRECHOS:\n{block}"}],
        Verdict)
    return bool(v.get("grounded")), v.get("reason", "")


async def main():
    s = SessionLocal()
    try:
        llm = get_llm_client()
        vix = VectorIndexService(s, get_text_chunker(), llm)
        runs = 0
        records = []
        hallucinated = []

        blocks = [("NÚCLEO", CORE), ("ADJACENTE", ADJACENT), ("FORA", OUT)]
        for bname, qs in blocks:
            print(f"\n=== {bname} (x{REPS} cada) ===")
            for q in qs:
                decs = []
                for _ in range(REPS):
                    dec, ans, cits, ctx = await ask(llm, vix, q)
                    runs += 1
                    grounded = None
                    if dec == "ANSWER":
                        sn = [ctx[c["i"]].get("snippet", "") for c in cits]
                        grounded, why = await judge(llm, q, ans, sn)
                        if grounded is False:
                            hallucinated.append({"q": q, "block": bname,
                                                 "answer": ans[:600], "reason": why})
                    decs.append((dec, grounded))
                    records.append({"q": q, "block": bname, "decision": dec,
                                    "grounded": grounded})
                d = [x[0] for x in decs]
                stable = len(set(d)) == 1
                g = [x[1] for x in decs if x[1] is not None]
                gtxt = "" if not g else f" grounded={['ok' if x else 'NÃO' for x in g]}"
                print(f"  {q[:46]:<46} {Counter(d)} estável={'sim' if stable else 'NÃO'}{gtxt}")

        def pct(a, b):
            return f"{100.0*a/b:.0f}%" if b else "n/a"

        def block_runs(b):
            return [r for r in records if r["block"] == b]

        core, adj, out = block_runs("NÚCLEO"), block_runs("ADJACENTE"), block_runs("FORA")
        answered = [r for r in records if r["decision"] == "ANSWER"]
        halluc = [r for r in records if r["grounded"] is False]

        out_refuse = sum(1 for r in out if r["decision"] == "ABSTAIN")
        core_ans = sum(1 for r in core if r["decision"] == "ANSWER")
        core_grounded = sum(1 for r in core if r["grounded"] is True)
        adj_ans = sum(1 for r in adj if r["decision"] == "ANSWER")
        adj_grounded = sum(1 for r in adj if r["grounded"] is True)

        byq = {}
        for r in records:
            byq.setdefault(r["q"], []).append(r["decision"])
        stable_q = sum(1 for ds in byq.values() if len(set(ds)) == 1)

        print("\n" + "=" * 66)
        print(f"RESULTADO v3  ({runs} execuções reais, {REPS}x por pergunta)")
        print("=" * 66)
        print(f"FORA da base  — recusa correta : {out_refuse}/{len(out)} = {pct(out_refuse,len(out))}")
        print(f"NÚCLEO        — respondeu       : {core_ans}/{len(core)} = {pct(core_ans,len(core))}")
        print(f"NÚCLEO        — fiel à fonte    : {core_grounded}/{core_ans or 1} = {pct(core_grounded,core_ans)}")
        print(f"ADJACENTE     — respondeu       : {adj_ans}/{len(adj)} = {pct(adj_ans,len(adj))}")
        print(f"ADJACENTE     — fiel à fonte    : {adj_grounded}/{adj_ans or 1} = {pct(adj_grounded,adj_ans)}")
        print("-" * 66)
        print(f">>> ALUCINAÇÃO GLOBAL (respostas s/ suporte): "
              f"{len(halluc)}/{len(answered)} = {pct(len(halluc),len(answered))}")
        print(f">>> ESTABILIDADE (perguntas c/ decisão idêntica em {REPS}x): "
              f"{stable_q}/{len(byq)} = {pct(stable_q,len(byq))}")
        print("=" * 66)

        if hallucinated:
            print("\n⚠️  CASOS ALUCINADOS (pra inspeção):")
            for h in hallucinated:
                print(f"  [{h['block']}] {h['q']}")
                print(f"     motivo: {h['reason']}")
                print(f"     resposta: {h['answer'][:200]}...")

        json.dump({"runs": runs, "reps": REPS, "records": records,
                   "hallucinated": hallucinated},
                  open("eval_v3_resultados.json", "w"), ensure_ascii=False, indent=2)
        print("\nDetalhes em eval_v3_resultados.json")
    finally:
        s.close()


if __name__ == "__main__":
    asyncio.run(main())
