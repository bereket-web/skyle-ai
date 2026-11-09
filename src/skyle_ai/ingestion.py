from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path


def extract_pages(filename: str, data: bytes) -> list[tuple[int | None, str]]:
    suffix = Path(filename).suffix.lower()
    if not data:
        raise ValueError("The uploaded file is empty.")
    if suffix in {".txt", ".md"}:
        try:
            text = data.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("Text files must be UTF-8 encoded.") from exc
        if not text:
            raise ValueError("No readable text was found.")
        return [(None, text)]
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            pages = [
                (index + 1, (page.extract_text() or "").strip())
                for index, page in enumerate(PdfReader(io.BytesIO(data)).pages)
            ]
        except Exception as exc:
            raise ValueError(
                "The PDF could not be parsed. Password-protected and malformed PDFs are unsupported."
            ) from exc
        pages = [(page, text) for page, text in pages if text]
        if not pages:
            raise ValueError(
                "No text layer was found in this PDF. Scanned/image-only PDFs need OCR, which is not included."
            )
        return pages
    if suffix == ".docx":
        try:
            from docx import Document

            doc = Document(io.BytesIO(data))
            blocks = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            blocks.extend(
                " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                for table in doc.tables
                for row in table.rows
            )
            text = "\n".join(block for block in blocks if block)
        except Exception as exc:
            raise ValueError("The DOCX file could not be parsed.") from exc
        if not text:
            raise ValueError("No readable text was found.")
        return [(None, text)]
    raise ValueError("Supported formats are .txt, .md, .pdf and .docx.")


def chunk_pages(pages: list[tuple[int | None, str]], size: int = 180, overlap: int = 30) -> list[dict[str, object]]:
    if size < 20 or overlap < 0 or overlap >= size:
        raise ValueError("Chunk size and overlap are invalid.")
    chunks: list[dict[str, object]] = []
    for page_number, text in pages:
        words = re.findall(r"\S+", text)
        step = size - overlap
        for start in range(0, len(words), step):
            body = " ".join(words[start : start + size]).strip()
            if body:
                chunks.append({"ordinal": len(chunks), "page": page_number, "body": body})
    return chunks


def fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
