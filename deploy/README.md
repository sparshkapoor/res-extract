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

There are two ways to run this, depending on whether a GUI/loginwindow
session actually exists on the machine.

### 2a. LaunchAgent (needs an active GUI session)

`LaunchAgent`s attach to a user's `gui/<uid>` launchd domain, which only
exists once that user has actually logged in via loginwindow — SSH alone
does not create one. If you have (or set up) auto-login for a user
(`sudo sysadminctl -autologin set -userName <user> -password <password>`,
requires FileVault to be off, and a reboot to take effect), use this path:

```
sed "s|/Users/REPLACE_ME|$HOME|g" deploy/launchd/com.resextract.backend.plist > ~/Library/LaunchAgents/com.resextract.backend.plist
launchctl load -w ~/Library/LaunchAgents/com.resextract.backend.plist
```

### 2b. LaunchDaemon (no GUI session needed — SSH-only access)

Runs system-wide at boot, independent of any user session. This is what
you want if the machine is only ever accessed over SSH. Requires root to
install (the plist must be root-owned or launchd refuses to load it):

```
sed "s|/Users/REPLACE_ME|$(whoami)|g; s|REPLACE_ME|$(whoami)|g" deploy/launchd/com.resextract.backend.daemon.plist | sudo tee /Library/LaunchDaemons/com.resextract.backend.plist > /dev/null
sudo chown root:wheel /Library/LaunchDaemons/com.resextract.backend.plist
sudo launchctl load -w /Library/LaunchDaemons/com.resextract.backend.plist
```

Either way, `KeepAlive` + `RunAtLoad` mean it restarts automatically on
crash or reboot. On startup, `app/main.py` sweeps any job left in a
non-terminal state from before the restart and marks it failed, so
nothing hangs.

**Known unknown, verified per-deployment**: `ocrmac`'s Vision framework
calls may behave differently when the process has no interactive window-
server session — this is more likely to actually matter under the
LaunchDaemon path (2b) than the LaunchAgent path (2a), since a LaunchDaemon
runs in a more restricted context than even a headless-but-logged-in GUI
session. If OCR silently returns nothing once the service is up, test
`ocrmac` directly against a real image while running as the daemon's user
to isolate whether it's a TCC/session issue.

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

The app is then reachable on the LAN at whatever host port you set in
`docker-compose.yml`. On a shared server, run `docker ps` first to check
for conflicts with anything else already running before picking a port.

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
