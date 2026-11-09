# API reference

The interactive OpenAPI page is available at `/docs` while the local service is running. All application endpoints are under `/api/v1`; `/health` and `/` are public. If `SKYLE_API_KEY` is configured, send `Authorization: Bearer <value>` to every `/api/v1` endpoint.

| Method | Route | Purpose |
|---|---|---|
| GET | `/api/v1/system` | Version, storage counts, LLM/auth state and privacy note |
| GET | `/api/v1/capabilities` | Methods and limits by capability |
| GET | `/api/v1/documents` | Local document metadata |
| POST | `/api/v1/documents/upload` | Upload `.txt`, `.md`, `.pdf` or `.docx` |
| POST | `/api/v1/demo/load` | Index original fictional examples |
| POST | `/api/v1/ask` | Lexical retrieval with evidence/source cards |
| POST | `/api/v1/chat` | Deterministic routing to text analysis or retrieval |
| POST | `/api/v1/analyze/text` | Local text heuristics |
| POST | `/api/v1/analyze/csv` | In-memory CSV profile |
| POST | `/api/v1/forecast` | Chronological baseline forecast from multipart CSV |
| POST | `/api/v1/vision` | Local image-property diagnostics; optional remote multimodal path |
| GET | `/api/v1/activity` | Metadata-only recent activity |
| DELETE | `/api/v1/documents/{id}` | Delete one indexed file and its passages |
| DELETE | `/api/v1/documents` | Clear the complete local document index |

Uploads are bounded; per-request limits are documented in `/api/v1/capabilities` and the `.env.example`. Responses include explicit method/mode fields where useful. The activity log intentionally excludes raw prompt text and file rows/content.
