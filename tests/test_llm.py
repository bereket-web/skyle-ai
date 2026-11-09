from __future__ import annotations

import base64

import httpx
import pytest

from skyle_ai.config import Settings
from skyle_ai.llm import LLMUnavailable, OpenAICompatibleClient


def test_llm_disabled_without_explicit_enablement(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("disabled adapter must not make a request")

    monkeypatch.setattr(httpx, "post", fail)
    client = OpenAICompatibleClient(
        Settings(data_dir=tmp_path, llm_enabled=False, llm_base_url="https://invalid.test/v1", llm_model="mock")
    )
    assert not client.enabled
    with pytest.raises(LLMUnavailable):
        client.answer_with_evidence("question", [{"citation_id": "S1", "text": "evidence"}])


def test_llm_citation_gate_and_explicit_external_request(tmp_path, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "The answer is 42 [S1]."}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    settings = Settings(
        data_dir=tmp_path,
        llm_enabled=True,
        llm_base_url="https://example.test/v1",
        llm_model="mock-model",
        llm_api_key="test-only",
    )
    client = OpenAICompatibleClient(settings)
    answer = client.answer_with_evidence("What is the answer?", [{"citation_id": "S1", "text": "The answer is 42."}])
    assert answer.endswith("[S1].")
    assert calls[0][0] == "https://example.test/v1/chat/completions"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-only"

    def invalid_post(url, **kwargs):
        return httpx.Response(
            200, request=httpx.Request("POST", url), json={"choices": [{"message": {"content": "Uncited answer."}}]}
        )

    monkeypatch.setattr(httpx, "post", invalid_post)
    with pytest.raises(LLMUnavailable, match="valid source citations"):
        client.answer_with_evidence("What is the answer?", [{"citation_id": "S1", "text": "The answer is 42."}])


def test_multimodal_adapter_encodes_image_only_when_explicitly_enabled(tmp_path, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": "A blue square."}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient(
        Settings(
            data_dir=tmp_path,
            llm_enabled=True,
            llm_base_url="https://example.test/v1",
            llm_model="mock-model",
        )
    )
    assert client.describe_image("Describe this", b"synthetic image bytes", "image/png") == "A blue square."
    payload = calls[0][1]
    image_content = payload["messages"][1]["content"][1]["image_url"]["url"]
    assert image_content == f"data:image/png;base64,{base64.b64encode(b'synthetic image bytes').decode()}"
