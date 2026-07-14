# Evals — anti-hallucination harness

End-to-end evaluations of the RAG pipeline (real DB + embeddings + LLM). They
measure the grounding gate: whether the assistant answers in-corpus questions
faithfully and *refuses* out-of-corpus ones instead of hallucinating.

| Script | What it measures |
|---|---|
| `eval_antialucinacao.py` | in-corpus answers vs out-of-corpus refusals; LLM-judge hallucination check |
| `eval_antialucinacao_v2.py` | cross-category isolation matrix, paraphrases, wider out-of-corpus set |
| `eval_antialucinacao_v3.py` | repeated runs + an "adjacent-but-not-covered" block (the Alan Turing synthesis case) |
| `eval_probe.py` | quick qualitative probe of a few suspicious questions |

## Running

These hit a live database and the configured LLM/embedding provider, so they
need the same environment variables as the app (see `.env.example`) plus valid
API keys. From the repo root:

```bash
python -m evals.eval_antialucinacao
```

Run outputs are written under `evals/results/` (gitignored).

## Known limitations (see ../ROADMAP.md)

- Category IDs are currently hardcoded to a specific dev database — they need a
  reproducible seed corpus/fixture to be portable and CI-runnable.
- Shared helpers (`_clamp`, citation-survival, judge) are duplicated across the
  scripts and should be extracted into a shared harness.
- Not yet wired into CI as a regression guardrail.
