# Flight Game V3 Web Build

This folder contains a pygbag-ready copy of the current V3 game.

## Files

- `flight-game-v3/main.py`: browser entrypoint for pygbag
- `build-flight-game-v3.ps1`: copies the latest `Flight Game 3 V3.py`, installs or upgrades pygbag, then starts a local web build/test server
- `package-flight-game-v3.ps1`: rebuilds the current game and creates an upload zip from the generated web output
- `embed-flight-game-v3.html`: example host page that embeds the published game with an iframe
- `flight_game_score_server.py`: shared scoreboard API server for the web version
- `flight_game_score_admin.html`: browser admin page served by the score server
- `Caddyfile.flight-game`: HTTPS reverse-proxy config for public hosting
- `flight-game-config.json`: static web config file for Supabase or custom score API settings
- `SUPABASE_SETUP.md`: setup guide for the GitHub Pages plus Supabase scoreboard path

## Local test

From PowerShell:

```powershell
Set-Location "c:\Users\conor\Game 1\web"
python .\flight_game_score_server.py
```

In a second PowerShell window:

```powershell
Set-Location "c:\Users\conor\Game 1\web"
.\build-flight-game-v3.ps1
```

Then open `http://localhost:8000` in a browser.

The web build will automatically call the score server at `http://localhost:8765/api/flight-game-scores` when running on `localhost`.

If `flight-game-config.json` contains a Supabase URL and anon key, the web build will use Supabase instead of the custom score server.

The admin page is available at `http://localhost:8765/admin/flight-game-scores`.

The generated browser files are written under `flight-game-v3/build/web`.

## Publish

To create an upload-ready zip from the current game:

```powershell
Set-Location "c:\Users\conor\Game 1\web"
.\package-flight-game-v3.ps1
```

The upload archive is written to:

```text
c:\Users\conor\Game 1\web\flight-game-v3\flight-game-v3-upload.zip
```

After you package and publish the pygbag output to a site, host the generated game page at a path such as:

```text
/games/flight-game-v3/index.html
```

Then you can embed it in any page with:

```html
<iframe
  src="/games/flight-game-v3/index.html"
  width="1280"
  height="720"
  style="border:0; max-width:100%;"
  allowfullscreen>
</iframe>
```

## HTTPS Reverse Proxy

For public hosting on Windows, the simplest setup here is Caddy in front of the Python score server.

1. Keep the Python score server bound to loopback only:

```powershell
$env:FLIGHT_GAME_SCORE_SERVER_HOST = "127.0.0.1"
$env:FLIGHT_GAME_TRUST_PROXY_HEADERS = "1"
$env:FLIGHT_GAME_ADMIN_USERNAME = "admin"
$env:FLIGHT_GAME_ADMIN_PASSWORD = "choose-a-strong-password"
python .\flight_game_score_server.py
```

2. Point Caddy at your public domain and built game files:

```powershell
$env:FLIGHT_GAME_DOMAIN = "flightgame.example.com"
$env:FLIGHT_GAME_ACME_EMAIL = "you@example.com"
$env:FLIGHT_GAME_WEB_ROOT = "c:/Users/conor/Game 1/web/flight-game-v3/build/web"
caddy run --config .\Caddyfile.flight-game
```

3. Caddy will terminate HTTPS, redirect plain HTTP to HTTPS automatically, serve the static web build, and reverse proxy these routes to the local Python server:
- `/api/flight-game-scores`
- `/admin/flight-game-scores`

With this setup, admin credentials are sent only over HTTPS to the reverse proxy rather than over plain HTTP to the backend.

## Notes

- The web build registers every named player when a match starts.
- Wins and losses only change when a full match finishes and a winner reaches the match win threshold.
- The leaderboard is ordered by wins first, then by fewest losses among tied players, and displays wins, losses, and net score.
- For GitHub Pages, the preferred shared-score setup is a static `flight-game-config.json` plus Supabase.
- The score server stores data in `web/flight_game_web_scores.json` by default.
- The admin page can refresh scores, edit or create player records, delete players, and reset the entire scoreboard.
- Set `FLIGHT_GAME_ADMIN_USERNAME` and `FLIGHT_GAME_ADMIN_PASSWORD` before starting the score server if you want browser login protection on the admin page and admin APIs.
- If you prefer token-based admin protection instead, set `FLIGHT_GAME_ADMIN_TOKEN`. The admin page will send that token in the `X-Admin-Token` header.
- The admin page can export the scoreboard to JSON and import it again either by replacing the current scoreboard or merging records into it.
- Admin changes are written to `web/flight_game_admin_audit.jsonl` by default.
- Set `FLIGHT_GAME_AUDIT_LOG_FILE` to change the audit log location.
- Set `FLIGHT_GAME_TRUST_PROXY_HEADERS=1` when the server is behind Caddy or another trusted reverse proxy so audit logs record the real client IP.
- The browser build uses `asyncio.run(main())` and `await asyncio.sleep(0)` in the loop.
- The build script is pinned to the installed Python 3.12 interpreter used for this project.