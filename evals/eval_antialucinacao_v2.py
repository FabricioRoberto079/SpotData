"""
Harness de avaliação v2 — teste PROFUNDO do filtro anti-alucinação + escopo de categoria.

Núcleo do teste (a pedido): MESMA PERGUNTA em CONTEXTOS (categorias) DIFERENTES.
Mede se o escopo de categoria isola de verdade e se o sistema RECUSA quando a
resposta existe mas está fora do contexto buscado (em vez de inventar/vazar).

Blocos:
  A) Matriz cross-categoria: cada pergunta rodada em 4 escopos (casa / categoria
     errada / categoria vazia / todas). O caso crítico: pergunta de SO escopada
     em AFONSO ou em categoria vazia DEVE recusar.
  B) Robustez a paráfrases: mesma intenção, várias redações.
  C) Fora-da-base ampliado (escopo = todas).

Roda o pipeline REAL (embeddings + busca pgvector + gpt-4o-mini + filtro 0.6),
sem gravar no banco. Juiz LLM checa alucinação só nas respostas dadas.

Uso:  .venv/bin/python eval_antialucinacao_v2.py
"""
from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, Field
from sqlalchemy import text

from src.data.postgres_client import SessionLocal
from src.integrations.llm import get_llm_client
from src.prompts.rag_prompt import RagAnswer, build_messages
from src.services.chat_service import MIN_CITATION_CONFIDENCE, RAG_TOP_K
from src.services.text_chunker import get_text_chunker
from src.services.vector_index_service import VectorIndexService

GERAL = "00000000-0000-0000-0000-000000000001"
AFONSO = "8ed541b0-2ea5-4b5b-b0d8-0783deb33a91"
CSDCD = "be32988b-6574-4d06-bb92-2bfd26b610c1"

CAT_NAME = {GERAL: "GERAL", AFONSO: "AFONSO", CSDCD: "CSDCD(vazia?)", None: "TODAS"}

OS_QUESTIONS = [
    "O que é um processo em um sistema operacional?",
    "O que é um deadlock (impasse)?",
    "O que é memória virtual?",
    "O que é uma thread?",
    "Como funciona o escalonamento round-robin?",
    "O que é paginação de memória?",
]
PERCENT_QUESTIONS = [
    "Como a porcentagem é usada no cotidiano?",
    "Como calcular um desconto percentual em uma compra?",
]

PARAPHRASES = {
    "O que é um processo (SO)": (GERAL, "ANSWER", [
        "O que é um processo em um sistema operacional?",
        "Pode me explicar o conceito de processo em SO?",
        "Em sistemas operacionais, o que significa um processo?",
        "Defina processo no contexto de sistemas operacionais.",
    ]),
    "Fora-da-base: capital da Austrália": (GERAL, "ABSTAIN", [
        "Qual é a capital da Austrália?",
        "Me diga qual cidade é a capital australiana.",
        "Austrália tem qual capital?",
    ]),
}

OUT_OF_CORPUS = [
    "Qual é a capital da França?",
    "Quem escreveu Dom Casmurro?",
    "Qual o ponto de ebulição da água ao nível do mar?",
    "Quantos planetas tem o sistema solar?",
    "Qual a moeda oficial do Japão?",
    "Quem foi o primeiro presidente dos Estados Unidos?",
    "Qual a velocidade da luz no vácuo?",
    "Em que ano o homem pisou na Lua?",
    "Qual o maior oceano do planeta?",
    "Como se faz pão caseiro?",
    "Qual a fórmula de Bhaskara?",
    "Quem ganhou o Oscar de melhor filme em 2020?",
]


class GroundingVerdict(BaseModel):
    grounded: bool = Field(description="True se TODA afirmação factual da RESPOSTA "
                           "é sustentada pelos TRECHOS; False caso contrário.")
    reason: str = Field(description="Justificativa curta.")


def _clamp(raw):
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v != v:
        return None
    return max(0.0, min(1.0, v))


def _surviving(raw_citations, n):
    kept, seen = [], set()
    for c in raw_citations or []:
        if not isinstance(c, dict):
            continue
        idx = c.get("context_index")
        if not isinstance(idx, int) or not (0 <= idx < n):
            continue
        conf = _clamp(c.get("confidence"))
        if conf is None or conf < MIN_CITATION_CONFIDENCE or idx in seen:
            continue
        seen.add(idx)
        kept.append({"context_index": idx, "confidence": conf})
    return kept


async def _last(llm, messages, schema):
    last = None
    async for p in llm.chat_stream_structured(messages, schema):
        last = p
    if last is None:
        return {}
    return last if isinstance(last, dict) else (
        last.model_dump() if hasattr(last, "model_dump") else {})


async def ask(llm, vix, question, category_id):
    contexts = vix.search(question, RAG_TOP_K, None, category_id)
    if not contexts:
        return {"decision": "ABSTAIN", "answer": "", "citations": [], "contexts": []}
    snap = await _last(llm, build_messages(question, contexts), RagAnswer)
    answer = (snap.get("answer") or "").strip() if isinstance(snap, dict) else ""
    cits = _surviving(snap.get("citations") if isinstance(snap, dict) else [],
                      len(contexts))
    return {"decision": "ANSWER" if (answer and cits) else "ABSTAIN",
            "answer": answer, "citations": cits, "contexts": contexts}


async def judge(llm, question, answer, snippets):
    block = "\n\n".join(f"[trecho {i}] {s}" for i, s in enumerate(snippets))
    msgs = [
        {"role": "system", "content":
            "Avaliador rigoroso de alucinação em RAG. Dada PERGUNTA, RESPOSTA e "
            "TRECHOS, decida se TODA afirmação factual da RESPOSTA está sustentada "
            "pelos TRECHOS. Sem suporte direto => grounded=false."},
        {"role": "user", "content":
            f"PERGUNTA: {question}\n\nRESPOSTA:\n{answer}\n\nTRECHOS:\n{block}"},
    ]
    v = await _last(llm, msgs, GroundingVerdict)
    return bool(v.get("grounded")), v.get("reason", "")


async def maybe_judge(llm, q, r):
    r["grounded"] = None
    if r["decision"] == "ANSWER":
        sn = [r["contexts"][c["context_index"]].get("snippet", "")
              for c in r["citations"]]
        r["grounded"], r["grounded_reason"] = await judge(llm, q, r["answer"], sn)
    r.pop("contexts", None)
    return r


def print_dist(session):
    print("=== distribuição de chunks (is_latest) por categoria ===")
    rows = session.execute(text(
        "select coalesce(c.name,'(NULL)') cat, count(*) n "
        "from vector_chunks v left join categories c on c.id=v.category_id "
        "where v.is_latest=true group by c.name order by n desc")).all()
    for name, n in rows:
        print(f"  {name:<28} {n}")
    nulls = session.execute(text(
        "select count(*) from vector_chunks "
        "where is_latest=true and category_id is null")).scalar()
    print(f"  -> chunks SEM categoria (aparecem em TODA busca): {nulls}")
    print()


async def main():
    session = SessionLocal()
    try:
        print_dist(session)
        llm = get_llm_client()
        vix = VectorIndexService(session, get_text_chunker(), llm)
        runs = 0

        print("=== BLOCO A — MESMA PERGUNTA, CONTEXTOS DIFERENTES ===")
        os_scopes = [(GERAL, "ANSWER"), (AFONSO, "ABSTAIN"),
                     (CSDCD, "ABSTAIN"), (None, "ANSWER")]
        pct_scopes = [(AFONSO, "ANSWER"), (GERAL, "ABSTAIN"),
                      (CSDCD, "ABSTAIN"), (None, "ANSWER")]
        matrix = []
        plan = ([("SO", q, os_scopes) for q in OS_QUESTIONS] +
                [("%", q, pct_scopes) for q in PERCENT_QUESTIONS])
        for tag, q, scopes in plan:
            line = []
            for cat, expected in scopes:
                r = await ask(llm, vix, q, cat)
                r = await maybe_judge(llm, q, r)
                runs += 1
                ok = r["decision"] == expected
                line.append((CAT_NAME[cat], r["decision"], expected, ok,
                             r["grounded"]))
                matrix.append({"q": q, "tag": tag, "scope": CAT_NAME[cat],
                               "decision": r["decision"], "expected": expected,
                               "ok": ok, "grounded": r["grounded"]})
            cells = "  ".join(
                f"{nm}:{'✓' if ok else '✗'}{dec[0]}" for nm, dec, exp, ok, g in line)
            print(f"  [{tag:>2}] {q[:42]:<42} | {cells}")

        print("\n=== BLOCO B — ROBUSTEZ A PARÁFRASES (escopo-casa) ===")
        para = []
        for name, (cat, expected, variants) in PARAPHRASES.items():
            decs = []
            for v in variants:
                r = await ask(llm, vix, v, cat)
                r = await maybe_judge(llm, v, r)
                runs += 1
                decs.append(r["decision"])
                para.append({"group": name, "variant": v,
                             "decision": r["decision"], "expected": expected})
            consistent = len(set(decs)) == 1
            allok = all(d == expected for d in decs)
            print(f"  {name:<40} esperado={expected:<8} "
                  f"decisões={decs} consistente={'sim' if consistent else 'NÃO'} "
                  f"tudo-ok={'sim' if allok else 'NÃO'}")

        print("\n=== BLOCO C — FORA-DA-BASE AMPLIADO (escopo=TODAS) ===")
        ooc = []
        for q in OUT_OF_CORPUS:
            r = await ask(llm, vix, q, None)
            r = await maybe_judge(llm, q, r)
            runs += 1
            ooc.append({"q": q, "decision": r["decision"]})
            print(f"  {'✓recusa' if r['decision']=='ABSTAIN' else '✗RESPONDEU':>10}  {q[:55]}")

        def pct(a, b):
            return f"{100.0*a/b:.0f}%" if b else "n/a"

        a_total = len(matrix)
        a_ok = sum(1 for m in matrix if m["ok"])
        crit = [m for m in matrix if m["expected"] == "ABSTAIN" and m["tag"] in ("SO", "%")]
        crit_ok = sum(1 for m in crit if m["ok"])
        home = [m for m in matrix if m["expected"] == "ANSWER"]
        home_ok = sum(1 for m in home if m["ok"])
        answered = [m for m in matrix if m["decision"] == "ANSWER"]
        halluc = sum(1 for m in matrix if m.get("grounded") is False)

        ooc_ok = sum(1 for o in ooc if o["decision"] == "ABSTAIN")

        print("\n" + "=" * 64)
        print(f"RESULTADO PROFUNDO  ({runs} execuções no pipeline real)")
        print("=" * 64)
        print(f"[A] Matriz cross-categoria acertou : {a_ok}/{a_total} = {pct(a_ok,a_total)}")
        print(f"    └─ RECUSA correta fora do contexto (crítico): "
              f"{crit_ok}/{len(crit)} = {pct(crit_ok,len(crit))}")
        print(f"    └─ Respondeu no contexto-casa: {home_ok}/{len(home)} = {pct(home_ok,len(home))}")
        print(f"[C] Recusa correta fora-da-base    : {ooc_ok}/{len(ooc)} = {pct(ooc_ok,len(ooc))}")
        print(f"[*] Alucinação (respostas s/ suporte): {halluc}/{len(answered)} "
              f"= {pct(halluc,len(answered))}")
        print("=" * 64)

        with open("eval_v2_resultados.json", "w") as f:
            json.dump({"runs": runs, "matrix": matrix, "paraphrases": para,
                       "out_of_corpus": ooc}, f, ensure_ascii=False, indent=2)
        print("Detalhes em eval_v2_resultados.json")
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
