import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    refining = "refining"
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
    # validate_assignment so this also fires when a pipeline stage mutates
    # an existing Ingredient's .quantity/.unit in place (e.g. vlm.py's
    # merge), not just on initial construction.
    model_config = ConfigDict(validate_assignment=True)

    name: str
    quantity: str | None = Field(default=None, description="e.g. '1', '1/2', '2-3'")
    unit: str | None = Field(default=None, description="e.g. 'cup', 'tbsp', 'cloves'")
    is_estimated: bool = Field(
        default=False,
        description="True when quantity/unit were not stated in the transcript or on-screen "
        "text and were instead estimated from typical recipe conventions for this dish.",
    )
    name_is_generic: bool = Field(
        default=False,
        description="True when `name` is a generic category (e.g. 'spices', 'seasoning') "
        "because the transcript/on-screen text never named it specifically.",
    )

    @model_validator(mode="after")
    def _dedupe_unit_from_quantity(self) -> "Ingredient":
        # Every LLM pass that fills these fields (pass 1, OCR refinement,
        # VLM estimation) intermittently embeds the unit word in `quantity`
        # too (e.g. quantity="1.8 kg", unit="kg"), producing a duplicated
        # "1.8 kg kg" when the two are joined for display. Centralizing the
        # cleanup here — rather than in each call site — means every
        # current and future path gets it for free.
        #
        # Matches simple singular/plural variants too, not just the exact
        # unit string: quantity="1 cup", unit="cups" previously survived as
        # "1 cup cups" because "cups" (the unit) is not a substring of "cup"
        # (what's actually embedded in quantity).
        if self.quantity and self.unit:
            unit_word = self.unit.strip()
            variants = {unit_word}
            variants.add(unit_word[:-1] if unit_word.endswith("s") else unit_word + "s")
            alternation = "|".join(re.escape(v) for v in variants if v)
            pattern = re.compile(rf"(^|\s)(?:{alternation})(\s|$)", re.IGNORECASE)
            cleaned = pattern.sub(" ", self.quantity).strip()
            # Bypass pydantic's validated __setattr__ here — going through
            # `self.quantity = ...` would re-trigger this same validator
            # (validate_assignment=True) and recurse infinitely.
            object.__setattr__(self, "quantity", cleaned or None)
        return self


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
    hero_image_path: str | None = Field(
        default=None,
        description="A dedicated finished-dish shot, selected independently of any "
        "step's own image (see vlm.py task='hero') — never a step's instructional "
        "frame. Null on older cached recipes; falls back to the last step's image.",
    )
    cook_time_minutes: int | None = Field(
        default=None, description="Total cook time in minutes, if stated or clearly implied."
    )
    servings: int | None = Field(
        default=None, description="Number of servings the recipe yields, if stated or clearly implied."
    )
    calories: int | None = Field(
        default=None, description="Estimated calories per serving, if stated on-screen or in the transcript."
    )
    oven_temp_f: int | None = Field(
        default=None,
        description="Oven temperature in Fahrenheit, if the recipe uses an oven and a temperature is stated.",
    )


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
