from __future__ import annotations

from skyle_ai.services.nlp import analyze_text


def test_english_heuristic_reports_matches_and_patterns():
    result = analyze_text("Skyle Lab released a great, helpful update on 2026-11-03 at https://example.test.")
    assert result["language_hint"] == "English/Latin-script"
    assert result["sentiment"]["label"] == "positive"
    assert any(entity["type"] == "url" for entity in result["entities"])
    assert any(entity["type"] == "date" for entity in result["entities"])
    assert result["method"].startswith("Local lexicon")


def test_amharic_script_hint_and_unknown_are_not_overstated():
    result = analyze_text("ይህ ጥሩ ሥራ ነው")
    assert result["language_hint"] == "Amharic-script"
    assert result["sentiment"]["label"] == "positive"
    assert "not a trained or benchmarked model" in result["method"]


def test_empty_and_router_behaviors(client):
    assert client.post("/api/v1/analyze/text", json={"text": "   "}).status_code == 422
    response = client.post("/api/v1/chat", json={"question": "sentiment: this is a good result"})
    assert response.status_code == 200
    assert response.json()["route"] == "text_analysis"
    assert response.json()["plan"][0]["status"] == "complete"
    general = client.post("/api/v1/chat", json={"question": "Tell me a story"}).json()
    assert general["route"] == "assistant_help"
    assert general["external_llm_used"] is False
