from __future__ import annotations

import io
import warnings

from PIL import Image, ImageStat, UnidentifiedImageError


class VisionError(ValueError):
    pass


def inspect_image(data: bytes, filename: str) -> dict:
    if not data:
        raise VisionError("The image file is empty.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            width, height = image.size
            if width * height > 25_000_000:
                raise VisionError("Images above 25 megapixels are not accepted.")
            image.load()
    except VisionError:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise VisionError("Could not safely decode this image. Use a valid PNG, JPEG, or WebP file.") from exc
    if image.format not in {"PNG", "JPEG", "WEBP", "GIF", "BMP", "TIFF"}:
        raise VisionError("Supported image formats are PNG, JPEG, WebP, GIF, BMP and TIFF.")
    rgb = image.convert("RGB")
    gray = rgb.convert("L")
    mean_brightness = round(float(ImageStat.Stat(gray).mean[0]), 2)
    contrast = round(float(ImageStat.Stat(gray).stddev[0]), 2)
    palette_image = rgb.copy()
    palette_image.thumbnail((256, 256))
    colors = palette_image.quantize(colors=5, method=Image.Quantize.MEDIANCUT).convert("RGB").getcolors(256 * 256) or []
    colors.sort(reverse=True)
    palette = [
        {"hex": "#{:02x}{:02x}{:02x}".format(*color), "share_pct": round(count / sum(n for n, _ in colors) * 100, 1)}
        for count, color in colors[:5]
    ]
    return {
        "filename": filename,
        "format": image.format,
        "width": int(width),
        "height": int(height),
        "aspect_ratio": round(width / height, 4),
        "mode": image.mode,
        "mean_luminance_0_255": mean_brightness,
        "grayscale_contrast_stddev": contrast,
        "dominant_colors": palette,
        "analysis_mode": "local computer-vision diagnostics",
        "semantic_description": None,
        "notes": (
            "This local path reports image properties and color statistics only; it does not identify objects "
            "or infer scene meaning."
        ),
    }
