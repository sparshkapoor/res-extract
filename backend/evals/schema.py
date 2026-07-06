"""Golden-case format for the eval harness.

A golden case freezes everything the LLM chain sees *before* any model
call — transcript, video description, and (optionally) OCR text — plus a
hand-corrected `expected` block. Freezing the inputs means a `--live` eval
run exercises only the LLM chain (extract_recipe.py's passes + citation_map
+ normalize), never yt-dlp/whisper/mlx-vlm, so it's fast, repeatable, and
only needs Ollama running.

`ocr_text` defaults to "" (no captured on-screen text) — this mirrors a
real simplification: capture.py only records the transcript/description
available *before* any LLM call, since real OCR text depends on frame
timestamps that only exist after a first extraction pass. An empty
ocr_text simply means the OCR-refine pass never fires in eval, exactly as
it wouldn't in the real pipeline for a video with no on-screen text.
"""

from pydantic import BaseModel, Field

from app.models import Platform, TranscriptResult


class ExpectedIngredient(BaseModel):
    name: str
    quantity: str | None = None
    unit: str | None = None


class Expected(BaseModel):
    title_contains: list[str] = Field(default_factory=list)
    ingredients: list[ExpectedIngredient] = Field(default_factory=list)
    steps_count_range: tuple[int, int] | None = None
    must_cite: bool = True
    # Optional, populated once WS4a's step-granularity metrics land —
    # absent/None means "not checked" for older golden cases.
    min_transcript_coverage: float | None = None
    max_terse_steps: int | None = None


class GoldenCase(BaseModel):
    id: str
    url: str
    platform: Platform
    transcript: TranscriptResult
    description: str = ""
    ocr_text: str = ""
    duration_seconds: float = 0.0
    expected: Expected
