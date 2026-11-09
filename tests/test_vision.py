from __future__ import annotations

import io

from PIL import Image

from skyle_ai.services.vision import VisionError, inspect_image


def png_bytes() -> bytes:
    image = Image.new("RGB", (24, 12), (215, 40, 70))
    draw = Image.new("RGB", (12, 12), (20, 80, 210))
    image.paste(draw, (12, 0))
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def test_local_image_diagnostics_measure_only_pixels_not_scene(client):
    response = client.post(
        "/api/v1/vision", files={"file": ("sample.png", png_bytes(), "image/png")}, data={"question": "describe"}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["width"] == 24 and result["height"] == 12
    assert result["format"] == "PNG"
    assert result["semantic_description"] is None
    assert result["external_llm_used"] is False
    assert result["analysis_mode"] == "local computer-vision diagnostics"
    assert result["dominant_colors"]


def test_invalid_image_rejected(client):
    response = client.post("/api/v1/vision", files={"file": ("broken.jpg", b"not an image", "image/jpeg")})
    assert response.status_code == 422


def test_image_service_rejects_empty_bytes():
    try:
        inspect_image(b"", "empty.png")
    except VisionError:
        pass
    else:
        raise AssertionError("expected empty image to fail")
