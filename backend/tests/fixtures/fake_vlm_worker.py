"""Stand-in for _vlm_worker.py used by test_vlm.py's persistent-manager
tests — mimics the real worker's ready-handshake/JSONL-serve-loop protocol
without needing mlx_vlm or a real model, so those tests run fast and
portably.

Behavior, driven entirely by the request payload (no real model):
- Normal request: echoes back {"id": ..., "echo": True} per request.
- A request with "crash": true anywhere in the batch: exits nonzero with
  no output, simulating a mid-batch worker crash for the
  crash-respawn-once test.
- {"cmd": "shutdown"}: exits cleanly, same as the real worker.
"""

import json
import sys


def main() -> None:
    print(json.dumps({"ready": True}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        payload = json.loads(line)

        if isinstance(payload, dict) and payload.get("cmd") == "shutdown":
            break

        if any(req.get("crash") for req in payload):
            sys.exit(1)

        print(json.dumps([{"id": req["id"], "echo": True} for req in payload]), flush=True)


if __name__ == "__main__":
    main()
