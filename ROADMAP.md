# ROADMAP

Larger improvements identified during the hardening pass that were intentionally
**not** done in one shot because they need an architecture/infra decision or a
migration that should land as its own reviewed change. Roughly ordered by value.

## Reliability / correctness

- **Independent grounding verifier.** The anti-hallucination gate currently
  trusts the LLM's self-reported `confidence`. Add an independent check before
  persisting an answer — an entailment/NLI pass or a cheap LLM judge (the evals
  already have one) — and/or combine confidence with the objective embedding
  distance of the cited chunk. This is the real fix for the "Alan Turing"
  synthesis case; the prompt rule added in this pass only mitigates it.
- **Async DB access.** `ChatService.ask_stream` is `async` but runs synchronous
  SQLAlchemy commits on the event loop, and the same `Session` is shared across
  threads via DI. Migrate to `AsyncSession` + `asyncpg` (or make every DB call
  go through `asyncio.to_thread` consistently and stop sharing sessions across
  services).
- **LLM request timeout + streaming-chat retries.** Embedding calls now retry;
  add an explicit provider request timeout and decide on a safe retry strategy
  for the streaming structured-output call (naive retry re-emits partials).

## Scale

- **Background vectorization.** Uploads run extraction + embedding synchronously
  and block the HTTP request; large PDFs risk client timeouts. Move to a job
  queue with real lifecycle states (`PENDING/PROCESSING/COMPLETED/FAILED`) and a
  status endpoint. The `vectorization_status` enum is a starting point.
- **Shared/invalidatable cache.** The L1 Q&A cache is per-worker; `_generation`
  is computed but never read on lookup, so `invalidate_category` doesn't reach
  other workers. Use a shared cache (Redis) with pub/sub invalidation, or
  consult `_generation` on lookup. Consider a TTL on the L2 (pgvector) cache.
- **ANN index for embeddings.** Search does a sequential scan because
  `text-embedding-3-large` (3072 dims) exceeds pgvector's HNSW limit. Move to
  `halfvec` + HNSW, or adopt a 1536-dim model.

## Retrieval quality

- **Chunking.** Fallback path hard-cuts mid-sentence; there is no overlap across
  page boundaries and no table/heading handling. Preserve sentence boundaries
  and add cross-page overlap.
- **Lexical arm.** `to_tsquery` ORs every token and the language is hardcoded to
  `portuguese`; make the language configurable/detected and weight tokens.

## Code quality

- **Adopt `ruff format` repo-wide.** ~47 files differ from the formatter; do this
  as its own commit so it doesn't drown out logic changes, then add
  `ruff format --check` back to CI.
- **De-duplicate.** Citation serialization exists in three places (one with an
  N+1 query); the `try/except: rollback(); raise` block is repeated ~20× (a
  unit-of-work context manager would remove it).
- **Typed domain payloads.** Services pass `dict`/`list[dict]` internally;
  `TypedDict`/dataclasses for citations and RAG context would prevent shape
  drift and let mypy tighten beyond the current pragmatic config.
- **`Settings` object.** Validate config once at startup (pydantic-settings)
  instead of reading `os.getenv` per call, so a missing `JWT_SECRET` fails at
  boot, not on first login.
- **Split `chat_service.py`** (712 lines) into repository / streaming
  orchestrator / citation layers.

## Testing / CI / delivery

- **HTTP endpoint coverage.** Beyond the new auth guard tests, add `TestClient`
  coverage for login/JWT, upload/download, chat streaming and the exception
  handlers. Cover the PDF and image (OCR) extractors.
- **Formalize evals.** Extract a shared harness, replace hardcoded category IDs
  with a seeded corpus fixture, and add a CI job that fails if the out-of-corpus
  refusal rate drops or hallucination rate rises. See `evals/README.md`.
- **CD.** No image is published and there is no staging. Add a build+push job
  (tag by SHA/version) and a deploy pipeline; consider secrets management
  (Vault/SSM/Docker secrets) instead of plaintext env.
- **Model relationships typing.** Models were given `TYPE_CHECKING` imports for
  forward refs; keep them in sync as relationships change.
