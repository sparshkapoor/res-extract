"""Run before writing/running any pipeline code: verifies the interpreter
has working, Metal-backed mlx/mlx-whisper and a working ocrmac (Vision
framework) install. See plan section 5.1 — if this fails under system
Python, the fallback is a pyenv-managed 3.12 venv."""

import sys


def main() -> None:
    failures: list[str] = []

    try:
        import mlx.core as mx
        device = mx.default_device()
        print(f"[ok] mlx imports, default device: {device}")
        if "gpu" not in str(device).lower():
            failures.append(f"mlx default device is not GPU/Metal: {device}")
    except Exception as e:  # noqa: BLE001
        failures.append(f"mlx import failed: {e}")

    try:
        import mlx_whisper  # noqa: F401
        print("[ok] mlx_whisper imports")
    except Exception as e:  # noqa: BLE001
        failures.append(f"mlx_whisper import failed: {e}")

    try:
        from ocrmac import ocrmac  # noqa: F401
        print("[ok] ocrmac imports (Vision framework wrapper)")
    except Exception as e:  # noqa: BLE001
        failures.append(f"ocrmac import failed: {e}")

    for name in ("fastapi", "pydantic", "yt_dlp", "youtube_transcript_api", "ollama", "aiosqlite"):
        try:
            __import__(name)
            print(f"[ok] {name} imports")
        except Exception as e:  # noqa: BLE001
            failures.append(f"{name} import failed: {e}")

    print(f"\nPython: {sys.version}")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        print(
            "\nIf mlx/mlx-whisper failed under this Python version, fall back to a "
            "pyenv-managed 3.12 venv (see plan section 5.1)."
        )
        sys.exit(1)

    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
