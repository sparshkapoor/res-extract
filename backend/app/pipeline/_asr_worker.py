"""Standalone ASR worker, invoked as a subprocess by asr.py.

Running mlx-whisper in its own short-lived process (rather than importing it
in-process inside the long-lived FastAPI worker) is the most reliable way to
guarantee its Metal/unified-memory allocations are fully released before the
subsequent Ollama call — process exit reclaims everything, whereas relying on
`del` + `gc.collect()` on a long-running process risks leaving MLX buffer
caches resident depending on the mlx version. This is the memory-safety
requirement from the design plan (avoid OOM on the 16GB M1 Air target).

Usage: python _asr_worker.py <audio_path> <model_name>
Prints a single JSON line to stdout: {"segments": [{"text","start","end"}, ...]}
"""

import json
import sys


def main() -> None:
    audio_path, model_name = sys.argv[1], sys.argv[2]

    import mlx_whisper

    result = mlx_whisper.transcribe(audio_path, path_or_hf_repo=model_name, word_timestamps=False)
    segments = [
        {"text": seg["text"].strip(), "start": float(seg["start"]), "end": float(seg["end"])}
        for seg in result.get("segments", [])
    ]
    print(json.dumps({"segments": segments}))


if __name__ == "__main__":
    main()
