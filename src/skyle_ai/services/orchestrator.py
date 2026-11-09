from __future__ import annotations

from dataclasses import dataclass

from skyle_ai.services.nlp import analyze_text
from skyle_ai.storage import Store, tokenize


@dataclass
class OrchestrationResult:
    route: str
    route_reason: str
    plan: list[dict]
    answer: str
    sources: list[dict]
    mode: str


class Orchestrator:
    """Explicit rule-based routing; it is not an autonomous planning LLM or a multi-agent graph."""

    def __init__(self, store: Store):
        self.store = store

    def run(self, question: str, requested_mode: str = "auto") -> OrchestrationResult:
        text = question.strip()
        lower = text.lower()
        if not text:
            raise ValueError("Enter a message first.")
        if requested_mode not in {"auto", "knowledge", "text"}:
            raise ValueError("Mode must be auto, knowledge or text.")
        if requested_mode == "text" or (
            requested_mode == "auto"
            and any(
                word in lower for word in ("sentiment", "analyze text", "analyse text", "entities in", "keywords in")
            )
        ):
            payload = text.split(":", 1)[1].strip() if ":" in text else text
            result = analyze_text(payload)
            return OrchestrationResult(
                route="text_analysis",
                route_reason="The request explicitly asked for text analysis or sentiment.",
                plan=[{"step": 1, "tool": "local_text_analysis", "status": "complete"}],
                answer=(
                    f"Text analysis completed. Heuristic sentiment: {result['sentiment']['label']} "
                    f"(score {result['sentiment']['score']}). It found {result['token_count']} tokens and "
                    f"{len(result['entities'])} pattern-based entity matches. This is a lightweight local "
                    "heuristic, not a trained model."
                ),
                sources=[],
                mode="heuristic",
            )
        if requested_mode == "knowledge" or any(
            word in lower
            for word in (
                "document",
                "uploaded",
                "according to",
                "in my files",
                "from my files",
                "knowledge base",
                "policy",
            )
        ):
            hits = self.store.search(tokenize(text), limit=4)
            sources = [{"citation_id": f"S{index}", **hit} for index, hit in enumerate(hits, 1)]
            if sources:
                answer = (
                    "I found these relevant local passages. Use the citations to inspect the source text; "
                    "this local baseline does not synthesize unsupported claims."
                )
            else:
                answer = (
                    "I couldn't find matching evidence in the local knowledge base. Add relevant documents "
                    "or rephrase the question; I won't invent a source-backed answer."
                )
            return OrchestrationResult(
                route="knowledge_retrieval",
                route_reason="The request refers to documents, uploaded files or the knowledge base.",
                plan=[{"step": 1, "tool": "sqlite_fts5_retrieval", "status": "complete" if sources else "no_evidence"}],
                answer=answer,
                sources=sources,
                mode="extractive",
            )
        return OrchestrationResult(
            route="assistant_help",
            route_reason="No enabled local tool matched the message; no external model was called.",
            plan=[{"step": 1, "tool": "capability_router", "status": "complete"}],
            answer=(
                "I can search uploaded documents, analyze text sentiment and patterns, profile a CSV, compare a "
                "simple time-series forecast, or inspect image properties. Choose a tool or ask a document question "
                "after adding files. General LLM responses are unavailable until an endpoint is explicitly configured."
            ),
            sources=[],
            mode="capability_help",
        )
