# Skyle AI: quality, evidence and limitations

## What is locally implemented

- A FastAPI v1 service and responsive static workbench UI.
- Persistent local SQLite/FTS5 text indexing with upload, chunking, cited retrieval, duplicate detection and explicit deletion.
- Local English/Amharic-script lexicon sentiment hints, regex patterns and frequent terms.
- In-memory CSV descriptive profiling and a chronological last-value versus linear-trend holdout comparison.
- Safe image decoding and local dimensions, luminance, contrast and color palette diagnostics.
- Deterministic capability routing, request IDs, structured metadata-only activity history, optional bearer-key auth and input size limits.
- An opt-in OpenAI-compatible chat completion adapter with citation-ID checks for retrieval and a multimodal image request path.

## What the numbers mean

Synthetic demo documents are original fiction. Unit and API tests establish deterministic software behavior, not retrieval quality, sentiment validity, forecasting accuracy, vision understanding, user adoption or production readiness. Forecast MAE/RMSE are only measured on the last chronological holdout segment of the uploaded series. The sentiment lexicon and named-phrase patterns are unvalidated heuristics. No trained model or external benchmark is included.

## Data and security boundaries

Documents that are uploaded for RAG are stored as extracted text in the local SQLite database until individually deleted or cleared. Original upload bytes are not stored. CSV and image requests are processed in memory and are not retained in the workspace activity history. Activity records store operation names, aggregate counts, selected route and measured elapsed time, not raw query text, CSV rows, image bytes or document excerpts. The system uses SQLite and is intended for a single local operator, not concurrent multi-user production.

By default, the server binds to `127.0.0.1` and makes no outbound LLM request. If `SKYLE_LLM_ENABLED=true` plus a base URL and model are configured, retrieval questions and their matching excerpts, and images submitted to the vision endpoint, may be sent to the configured provider. The user/operator must assess that provider's data handling. The bearer token is a single shared access gate, not account-based authentication or document ACLs. TLS, rate limiting, CSRF controls, encryption-at-rest, tenant isolation, durable distributed queues and formal threat modeling are not implemented.

## Known technical limits

- Retrieval is lexical FTS5 plus token overlap; no embeddings, semantic retrieval or reranker are loaded.
- Scanned PDFs/OCR, layout/table extraction and large corpora are unsupported; the exact local index is for a small workspace.
- Amharic support is a script/word-list smoke capability, not a validated language model; token boundaries and sentiment coverage are limited.
- CSV correlations are descriptive Pearson associations, not causal or inferential claims.
- Forecasting ignores frequency inference, seasonality, uncertainty intervals and exogenous drivers.
- Local vision is image diagnostics, not object detection, OCR or semantic understanding. Semantic description exists only through the explicit remote LLM adapter and is not model-verified in the default local build.
- Docker/Compose is an optional packaging path; local CI/tests do not imply a hosted deployment.
