from enum import StrEnum

from pydantic import BaseModel, Field


class Platform(StrEnum):
    youtube = "youtube"
    instagram = "instagram"


class JobStatus(StrEnum):
    queued = "queued"
    downloading = "downloading"
    downloaded = "downloaded"
    transcribing = "transcribing"
    transcribed = "transcribed"
    extracting = "extracting"
    extracted = "extracted"
    extracting_frames = "extracting_frames"
    frames_done = "frames_done"
    ocr = "ocr"
    done = "done"
    failed = "failed"


class TranscriptSegment(BaseModel):
    text: str
    start: float
    end: float


class TranscriptResult(BaseModel):
    segments: list[TranscriptSegment]
    source: str  # "captions" | "asr"

    @property
    def full_text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments).strip()


# --- Recipe schema -----------------------------------------------------
# Structured as a Recipe1M+/YouCook2-style imperative "program": each step
# names its action, cites the transcript, and resolves to a timestamp/frame.
# This same schema is passed to Ollama's `format=` for constrained decoding.


class Ingredient(BaseModel):
    name: str
    quantity: str | None = Field(default=None, description="e.g. '1', '1/2', '2-3'")
    unit: str | None = Field(default=None, description="e.g. 'cup', 'tbsp', 'cloves'")
    is_estimated: bool = Field(
        default=False,
        description="True when quantity/unit were not stated in the transcript or on-screen "
        "text and were instead estimated from typical recipe conventions for this dish.",
    )


class Step(BaseModel):
    index: int
    instruction: str = Field(description="Imperative action, e.g. 'Melt butter in a pan over medium heat.'")
    verbatim_transcript_citation: str = Field(
        description="An exact substring copied from the transcript that this step is derived from. "
        "Must not be paraphrased."
    )
    timestamp_seconds: float | None = None
    image_path: str | None = None


class Recipe(BaseModel):
    title: str
    source_url: str
    platform: Platform
    ingredients: list[Ingredient]
    steps: list[Step]


class SavedRecipeSummary(BaseModel):
    """Lightweight entry for the Saved Recipes gallery — see
    result_cache.list_cached() for why this is separate from Recipe."""

    url_hash: str
    url: str
    title: str
    platform: Platform
    thumbnail: str | None
    created_at: str


# --- API request/response models ---------------------------------------


class JobCreateRequest(BaseModel):
    url: str


class JobCreateResponse(BaseModel):
    job_id: str
    status: JobStatus
    cached: bool


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage_message: str | None = None
    error: str | None = None
    updated_at: str


class JobEvent(BaseModel):
    stage: JobStatus
    status: str  # "in_progress" | "success" | "failed"
    message: str | None = None
    ts: float
