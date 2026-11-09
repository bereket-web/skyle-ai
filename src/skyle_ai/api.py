from __future__ import annotations

import hmac
import io
import logging
import mimetypes
import time
import uuid
from pathlib import Path
from typing import Annotated, Literal

import pandas as pd
from fastapi import APIRouter, Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from skyle_ai import __version__
from skyle_ai.config import Settings
from skyle_ai.ingestion import chunk_pages, extract_pages, fingerprint
from skyle_ai.llm import LLMUnavailable, OpenAICompatibleClient
from skyle_ai.services.analytics import CSVAnalysisError, profile_csv
from skyle_ai.services.forecast import ForecastError, forecast_series
from skyle_ai.services.nlp import analyze_text
from skyle_ai.services.orchestrator import Orchestrator
from skyle_ai.services.vision import VisionError, inspect_image
from skyle_ai.storage import Store, tokenize

logger = logging.getLogger("skyle_ai")
PACKAGE_ROOT = Path(__file__).resolve().parent
STATIC_ROOT = PACKAGE_ROOT / "static"
DEMO_ROOT = PACKAGE_ROOT / "data" / "demo"


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=6_000)
    mode: Literal["auto", "knowledge", "text"] = "auto"


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)
    top_k: int = Field(default=4, ge=1, le=8)


def create_app(settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = store or Store(settings.database_path)
    llm = OpenAICompatibleClient(settings)
    app = FastAPI(
        title="Skyle AI",
        version=__version__,
        description="Local-first modular AI workbench with retrieval, text, data, forecasting and image diagnostics.",
    )
    app.state.settings = settings
    app.state.store = store
    app.state.llm = llm

    def record_operation(action: str, status: str, started_at: float, summary: dict) -> None:
        duration_ms = max(1, round((time.perf_counter() - started_at) * 1000))
        store.record_activity(action, status, duration_ms, summary)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    def require_api_key(authorization: Annotated[str | None, Header()] = None) -> None:
        if not settings.api_key:
            return
        supplied = (
            authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else ""
        )
        if not hmac.compare_digest(supplied, settings.api_key):
            raise HTTPException(
                status_code=401, detail="A valid bearer token is required.", headers={"WWW-Authenticate": "Bearer"}
            )

    api = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])

    @app.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(STATIC_ROOT / "index.html")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "skyle-ai", "version": __version__}

    @api.get("/system")
    def system_status() -> dict:
        return {
            "service": "Skyle AI",
            "version": __version__,
            "status": "ready",
            "auth_required": bool(settings.api_key),
            "storage": {"engine": "SQLite + FTS5", "scope": "local workspace", **store.counts()},
            "llm": {
                "configured": llm.enabled,
                "mode": "opt-in OpenAI-compatible endpoint" if llm.enabled else "disabled; no remote request is made",
                "model": settings.llm_model if llm.enabled else None,
            },
            "privacy": (
                "Uploaded documents remain in the local SQLite index. CSV and image uploads are processed in memory. "
                "Raw request text is not included in activity records."
            ),
        }

    @api.get("/capabilities")
    def capabilities() -> dict:
        return {
            "capabilities": [
                {
                    "id": "rag",
                    "label": "Knowledge retrieval",
                    "state": "local",
                    "method": "SQLite FTS5 lexical retrieval with source passages; no embedding model is loaded.",
                },
                {
                    "id": "agents",
                    "label": "Tool orchestration",
                    "state": "local",
                    "method": (
                        "Transparent rule-based routing to a small tool registry; not an autonomous multi-agent model."
                    ),
                },
                {
                    "id": "nlp",
                    "label": "Text analysis",
                    "state": "local heuristic",
                    "method": "English/Amharic-script lexicon and regex patterns; unbenchmarked.",
                },
                {
                    "id": "data",
                    "label": "CSV analysis",
                    "state": "local",
                    "method": "Pandas profile, missingness, duplicates and numeric summaries; upload is not persisted.",
                },
                {
                    "id": "forecast",
                    "label": "Time-series baseline",
                    "state": "local",
                    "method": "Chronological holdout compares last-value and linear trend.",
                },
                {
                    "id": "vision",
                    "label": "Image diagnostics",
                    "state": "local",
                    "method": "Pillow metadata, luminance and color palette; no local object recognition.",
                },
                {
                    "id": "llm",
                    "label": "LLM / semantic vision",
                    "state": "enabled" if llm.enabled else "disabled",
                    "method": (
                        "Explicitly configured OpenAI-compatible endpoint only; "
                        "relevant prompts/media leave this machine when enabled."
                    ),
                },
            ],
        }

    @api.get("/documents")
    def documents() -> dict:
        return {"documents": store.list_documents(), **store.counts()}

    @api.post("/documents/upload")
    def upload_documents(request: Request, files: Annotated[list[UploadFile], File()]) -> dict:
        started_at = time.perf_counter()
        if not files or len(files) > 10:
            raise HTTPException(status_code=422, detail="Upload between 1 and 10 files per request.")
        results = []
        indexed = 0
        for upload in files:
            filename = Path(upload.filename or "document.txt").name[:180]
            data = upload.file.read(settings.max_document_bytes + 1)
            try:
                if len(data) > settings.max_document_bytes:
                    raise ValueError(f"File exceeds the {settings.max_document_bytes // (1024 * 1024)} MB limit.")
                pages = extract_pages(filename, data)
                chunks = chunk_pages(pages)
                if not chunks:
                    raise ValueError("No readable text was found.")
                media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                document, created = store.add_document(
                    filename=filename,
                    media_type=media_type,
                    size_bytes=len(data),
                    sha256=fingerprint(data),
                    chunks=chunks,
                )
                indexed += int(created)
                results.append({"status": "indexed" if created else "already_exists", "document": document})
            except ValueError as exc:
                results.append({"status": "error", "filename": filename, "error": str(exc)})
            except Exception as exc:
                logger.exception("Document indexing failed; request_id=%s", request.state.request_id)
                results.append(
                    {"status": "error", "filename": filename, "error": f"Indexing failed ({exc.__class__.__name__})."}
                )
            finally:
                upload.file.close()
        status = "success" if indexed else "partial_or_noop"
        record_operation("document_upload", status, started_at, {"files": len(files), "new_documents": indexed})
        return {"results": results, **store.counts()}

    @api.post("/demo/load")
    def load_demo() -> dict:
        started_at = time.perf_counter()
        results = []
        for path in sorted(DEMO_ROOT.glob("*.md")):
            data = path.read_bytes()
            pages = extract_pages(path.name, data)
            doc, created = store.add_document(
                filename=path.name,
                media_type="text/markdown",
                size_bytes=len(data),
                sha256=fingerprint(data),
                chunks=chunk_pages(pages),
                source="synthetic_demo",
            )
            results.append({"status": "indexed" if created else "already_exists", "document": doc})
        record_operation(
            "demo_load",
            "success",
            started_at,
            {"files": len(results), "new_documents": sum(x["status"] == "indexed" for x in results)},
        )
        return {"results": results, **store.counts(), "data_mode": "original fictional examples"}

    @api.delete("/documents/{document_id}")
    def delete_document(document_id: str) -> dict:
        started_at = time.perf_counter()
        deleted = store.delete_document(document_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found.")
        record_operation("document_delete", "success", started_at, {"documents": 1})
        return {"deleted": True, **store.counts()}

    @api.delete("/documents")
    def clear_documents() -> dict:
        started_at = time.perf_counter()
        count = store.clear_documents()
        record_operation("documents_clear", "success", started_at, {"documents": count})
        return {"cleared": count, **store.counts()}

    @api.post("/ask")
    def ask(request: AskRequest) -> dict:
        started_at = time.perf_counter()
        hits = store.search(tokenize(request.question), limit=request.top_k)
        sources = [{"citation_id": f"S{index}", **hit} for index, hit in enumerate(hits, 1)]
        if sources:
            answer = (
                "I found these relevant local passages. This extractive baseline does not infer facts "
                "beyond the cited text."
            )
        else:
            answer = "I couldn't find relevant evidence in the local index. Add a document or refine the query."
        external = False
        mode = "extractive"
        warnings_out = []
        if sources and llm.enabled:
            try:
                answer = llm.answer_with_evidence(request.question, sources)
                external = True
                mode = "configured_llm_with_citation_check"
            except LLMUnavailable as exc:
                mode = "extractive_fallback"
                warnings_out.append(str(exc))
        record_operation(
            "knowledge_qa",
            "success" if sources else "no_evidence",
            started_at,
            {"sources": len(sources), "external_llm_used": external},
        )
        return {
            "answer": answer,
            "sources": sources,
            "mode": mode,
            "external_llm_used": external,
            "warnings": warnings_out,
        }

    @api.post("/chat")
    def chat(request: ChatRequest) -> dict:
        started_at = time.perf_counter()
        try:
            result = Orchestrator(store).run(request.question, request.mode)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        mode = result.mode
        external = False
        warnings_out = []
        if result.route == "knowledge_retrieval" and result.sources and llm.enabled:
            try:
                answer = llm.answer_with_evidence(request.question, result.sources)
                result.answer = answer
                mode = "configured_llm_with_citation_check"
                external = True
            except LLMUnavailable as exc:
                mode = "extractive_fallback"
                warnings_out.append(str(exc))
        else:
            mode = result.mode
        record_operation(
            "agent_chat",
            "success",
            started_at,
            {"route": result.route, "sources": len(result.sources), "external_llm_used": external},
        )
        return {
            "answer": result.answer,
            "route": result.route,
            "route_reason": result.route_reason,
            "plan": result.plan,
            "sources": result.sources,
            "mode": mode,
            "external_llm_used": external,
            "warnings": warnings_out,
        }

    @api.post("/analyze/text")
    def text_analysis(request: TextRequest) -> dict:
        started_at = time.perf_counter()
        try:
            result = analyze_text(request.text)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        record_operation(
            "text_analysis",
            "success",
            started_at,
            {"tokens": result["token_count"], "language_hint": result["language_hint"]},
        )
        return result

    @api.post("/analyze/csv")
    def csv_analysis(file: Annotated[UploadFile, File()]) -> dict:
        started_at = time.perf_counter()
        filename = Path(file.filename or "data.csv").name[:180]
        data = file.file.read(settings.max_csv_bytes + 1)
        file.file.close()
        if len(data) > settings.max_csv_bytes:
            raise HTTPException(status_code=413, detail="CSV upload exceeds the configured size limit.")
        try:
            result = profile_csv(data, max_rows=settings.max_csv_rows)
        except CSVAnalysisError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result["filename"] = filename
        record_operation("csv_profile", "success", started_at, {"rows": result["rows"], "columns": result["columns"]})
        return result

    @api.post("/forecast")
    def series_forecast(
        file: Annotated[UploadFile, File()],
        value_column: Annotated[str, Form(min_length=1, max_length=120)],
        date_column: Annotated[str | None, Form(max_length=120)] = None,
        horizon: Annotated[int, Form(ge=1, le=30)] = 7,
    ) -> dict:
        started_at = time.perf_counter()
        filename = Path(file.filename or "series.csv").name[:180]
        data = file.file.read(settings.max_csv_bytes + 1)
        file.file.close()
        if len(data) > settings.max_csv_bytes:
            raise HTTPException(status_code=413, detail="CSV upload exceeds the configured size limit.")
        try:
            frame = pd.read_csv(io.BytesIO(data), nrows=settings.max_csv_rows + 1)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="Could not parse the CSV file.") from exc
        if len(frame) > settings.max_csv_rows:
            raise HTTPException(status_code=422, detail="CSV exceeds the configured row limit.")
        if value_column not in frame.columns:
            raise HTTPException(status_code=422, detail=f"Value column '{value_column}' was not found.")
        values = pd.to_numeric(frame[value_column], errors="coerce")
        if values.isna().any():
            raise HTTPException(
                status_code=422, detail="The selected value column must contain only numeric, non-empty values."
            )
        if date_column:
            if date_column not in frame.columns:
                raise HTTPException(status_code=422, detail=f"Date column '{date_column}' was not found.")
            dates = pd.to_datetime(frame[date_column], errors="coerce", utc=True)
            if dates.isna().any() or dates.duplicated().any():
                raise HTTPException(status_code=422, detail="Date values must parse and be unique.")
            frame = frame.assign(_forecast_date=dates, _forecast_value=values).sort_values("_forecast_date")
            values = frame["_forecast_value"]
        try:
            result = forecast_series(values.astype(float).tolist(), horizon=horizon)
        except ForecastError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        result.update(
            {
                "filename": filename,
                "value_column": value_column,
                "date_column": date_column,
                "data_mode": "uploaded local CSV; chronological order used"
                if date_column
                else "uploaded local CSV; row order treated as chronological",
            }
        )
        record_operation(
            "forecast",
            "success",
            started_at,
            {
                "observations": result["observations"],
                "horizon": horizon,
                "model": result["model_selected_on_holdout_mae"],
            },
        )
        return result

    @api.post("/vision")
    def image_analysis(
        file: Annotated[UploadFile, File()], question: Annotated[str, Form(max_length=1_000)] = ""
    ) -> dict:
        started_at = time.perf_counter()
        filename = Path(file.filename or "image.bin").name[:180]
        data = file.file.read(settings.max_image_bytes + 1)
        media_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        file.file.close()
        if len(data) > settings.max_image_bytes:
            raise HTTPException(status_code=413, detail="Image upload exceeds the configured size limit.")
        try:
            result = inspect_image(data, filename)
        except VisionError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        external = False
        if llm.enabled:
            try:
                actual_media_type = mimetypes.guess_type(f"image.{result['format'].lower()}")[0] or media_type
                result["semantic_description"] = llm.describe_image(question, data, actual_media_type)
                result["analysis_mode"] = "local diagnostics + configured external multimodal LLM"
                external = True
            except LLMUnavailable as exc:
                result["llm_warning"] = str(exc)
        result["external_llm_used"] = external
        record_operation(
            "image_analysis",
            "success",
            started_at,
            {"width": result["width"], "height": result["height"], "external_llm_used": external},
        )
        return result

    @api.get("/activity")
    def activity(limit: int = 30) -> dict:
        return {"events": store.list_activity(limit)}

    app.include_router(api)
    app.mount("/static", StaticFiles(directory=STATIC_ROOT), name="static")
    return app


app = create_app()
