import asyncio
from pathlib import Path

from ocrmac import ocrmac


def _ocr_sync(image_path: Path) -> list[str]:
    annotations = ocrmac.OCR(str(image_path)).recognize()
    # annotations: list of (text, confidence, bbox)
    return [text.strip() for text, _confidence, _bbox in annotations if text.strip()]


async def ocr_frame(image_path: Path) -> list[str]:
    """Apple Vision OCR (via ocrmac) — bare-metal only, wraps the macOS
    Vision framework, unavailable inside a Linux container."""
    return await asyncio.to_thread(_ocr_sync, image_path)


def dedupe_ocr_text(per_frame_text: list[list[str]]) -> str:
    """Frames often repeat the same on-screen boilerplate/watermark text.
    Dedupe across all frames and join into one context string for the LLM."""
    seen: dict[str, None] = {}
    for frame_texts in per_frame_text:
        for text in frame_texts:
            key = text.lower()
            if key not in seen:
                seen[key] = None
    return "\n".join(seen.keys())
