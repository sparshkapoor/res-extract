# Deploying to the headless M1 Air

This assumes the repo has been rsynced over and all setup steps from the
plan (`brew install ffmpeg yt-dlp colima`, Python venv, `ollama pull
qwen2.5:7b`) have already been run on the M1 Air itself.

## 1. Ollama (bare-metal, keep resident)

Homebrew's `ollama` formula manages its own launchd service:

```
brew services start ollama
```

To keep the model pinned in memory (avoid cold-start latency on every
request), set `OLLAMA_KEEP_ALIVE=-1` in that service's environment:

```
launchctl setenv OLLAMA_KEEP_ALIVE -1
brew services restart ollama
```

## 2. Backend (bare-metal FastAPI, launchd-managed)

Edit `deploy/launchd/com.resextract.backend.plist`, replacing every
`REPLACE_ME` with the actual path to the repo on the M1 Air, then:

```
cp deploy/launchd/com.resextract.backend.plist ~/Library/LaunchAgents/
launchctl load -w ~/Library/LaunchAgents/com.resextract.backend.plist
```

`KeepAlive` + `RunAtLoad` mean it restarts automatically on crash or
reboot. On startup, `app/main.py` sweeps any job left in a non-terminal
state from before the restart and marks it failed, so nothing hangs.

**Known unknown, verify on the real M1 Air**: `ocrmac`'s Vision framework
calls may behave differently when the process has no interactive window-
server session (LaunchAgent vs LaunchDaemon, TCC permissions). If OCR
silently returns nothing under launchd but works when run manually from a
terminal, this is the first thing to check — see the plan's verification
section for the fallback options.

## 3. Frontend build + Colima/nginx

```
cd frontend && npm run build   # outputs to frontend/dist

colima start --cpu 2 --memory 2 --vm-type vz --mount-type virtiofs
docker context use colima
cd deploy/colima && docker compose up -d
```

Colima's nginx container is deliberately small and does nothing but serve
`frontend/dist` and reverse-proxy `/api` + `/media` to
`host.lima.internal:8000` (the bare-metal backend). Do not add other
services to `docker-compose.yml` — see the comments in that file and
`nginx.conf` for why.

The app is then reachable on the LAN at `http://<m1-air-hostname>.local:8080`.

## 4. Instagram cookies

`yt-dlp --cookies-from-browser <browser>` only works if that browser is
installed and logged in on the same machine running yt-dlp — which the
headless M1 Air won't have. Export a `cookies.txt` from a machine with a
logged-in browser instead:

```
yt-dlp --cookies-from-browser firefox --cookies instagram_cookies.txt --skip-download "<any-public-reel-url>"
```

Copy that file to the M1 Air and point `INSTAGRAM_COOKIES_FILE` in
`backend/.env` at it. Cookies expire — re-export periodically when
Instagram downloads start failing with an auth error.
