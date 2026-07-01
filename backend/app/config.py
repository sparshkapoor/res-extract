from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage
    storage_dir: Path = BACKEND_DIR / "storage"
    db_path: Path = BACKEND_DIR / "storage" / "db.sqlite3"

    # Ollama (bare-metal, host-only)
    ollama_host: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b"
    ollama_keep_alive: int = -1
    # Ollama defaults to a small context window (2048-4096 tokens) unless
    # told otherwise, which risks silently truncating longer video
    # transcripts. Qwen2.5 7B supports up to 131072, but KV-cache memory
    # scales with context length (~56KB/token for this model) — 131072
    # would cost ~7.3GB on top of the ~4.7GB of resident weights, too tight
    # against the 16GB M1 Air budget once the VLM pass's ~3.5GB is added.
    # 32768 costs ~1.8GB and comfortably covers even a long-form recipe
    # video's transcript, so it's the practical ceiling here, not the
    # architectural one.
    ollama_num_ctx: int = 32768

    # ASR (mlx-whisper, bare-metal, Metal-backed)
    # "small" chosen over "large-v3" deliberately: the 16GB M1 Air deployment
    # target has little headroom once Qwen2.5 7B (~5.5GB resident) is loaded.
    asr_model_name: str = "mlx-community/whisper-small-mlx"

    # VLM (mlx-vlm, bare-metal, Metal-backed). 3B chosen over 7B for memory
    # headroom — runs in its own subprocess (see _vlm_worker.py) after
    # Ollama's Qwen2.5 7B text pass, so the two must coexist in unified
    # memory even though ASR is unloaded by then. ~3.5GB peak observed.
    vlm_model_name: str = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"

    # Empty-transcript guard — below this, narration is too sparse to trust on
    # its own, so the pipeline falls back to vision-based narration instead of
    # failing outright (see vision_narration.py).
    empty_transcript_min_chars: int = 40
    empty_transcript_min_words: int = 8

    # Vision-narration fallback (silent/low-narration videos). Bounded frame
    # count keeps this from ballooning runtime on longer videos — each sampled
    # frame costs one OCR call + one sequential VLM call.
    vision_narration_max_frames: int = 18
    vision_narration_min_interval_seconds: float = 1.5

    # Instagram auth (yt-dlp needs a cookie export; see deploy notes)
    instagram_cookies_file: Path | None = None

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def downloads_dir(self) -> Path:
        return self.storage_dir / "downloads"

    @property
    def frames_dir(self) -> Path:
        return self.storage_dir / "frames"

    @property
    def cache_dir(self) -> Path:
        return self.storage_dir / "cache"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    for d in (settings.storage_dir, settings.downloads_dir, settings.frames_dir, settings.cache_dir):
        d.mkdir(parents=True, exist_ok=True)
    return settings
