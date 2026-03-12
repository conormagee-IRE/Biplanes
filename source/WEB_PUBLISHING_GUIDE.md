# Flight Game Web Publishing Guide

## 1. Pygbag Compatibility Assessment

Current status: partially compatible, with a realistic path to a browser build.

What already fits pygbag well:
- Pure Python game logic.
- Pygame drawing built mostly from primitives and surfaces.
- No native extensions or external binary assets.
- Keyboard and mouse input are already centralized through pygame events.

Main blockers that existed in the desktop version:
- Persistent stats were written to a local JSON file beside the script.
- The game used blocking desktop-style loops driven only by `clock.tick(FPS)`.
- Publishing instructions and a browser packaging path were not set up.

What has now been changed in [Flight Game 3 V3.py](c:/Users/conor/Game%201/Flight%20Game%203%20V3.py):
- The web build now calls a score server API instead of browser-only local storage.
- The web build can also load a static `flight-game-config.json` and use Supabase directly for shared scores.
- The main game loop, name-entry loop, and top-scores loop now use async frame stepping so they can yield in a browser runtime.

Residual web risks:
- `pygame` browser behavior depends on the exact pygbag version.
- Keyboard handling may need minor browser-specific tweaks after the first live test.
- Public hosting will need the score server deployed behind the same site or exposed with CORS enabled.
- Fullscreen, resizing, mobile controls, and audio are not yet designed for web release.

Assessment result: good candidate for a first browser prototype with pygbag, but not yet a fully polished public web release.

## 2. How To Build With Pygbag

Recommended local steps:

1. Install pygbag:

```powershell
py -m pip install pygbag
```

2. In the web folder, run:

```powershell
cd "c:\Users\conor\Game 1\web"
.\build-flight-game-v3.ps1
```

3. Pygbag will generate a web build directory and a local preview server from `web/flight-game-v3/main.py`.

4. Start the score server before testing the browser build:

```powershell
cd "c:\Users\conor\Game 1\web"
python .\flight_game_score_server.py
```

5. Test these areas first:
- Name entry on first load.
- Player registration after entering names.
- Match completion updating wins and losses once per finished game.
- Admin page loading at `http://localhost:8765/admin/flight-game-scores`.
- Admin protection with browser login or token auth enabled.
- Exporting and restoring the scoreboard from the admin page.
- Audit log entries after admin edits, imports, resets, and deletions.
- Supabase loading correctly when `flight-game-config.json` is populated.
- Keyboard controls for both players.
- Weather timing and top-scores screen.

## 3. Publishing Options

Good hosting targets for a pygbag build:
- itch.io as an HTML game.
- GitHub Pages for simple static hosting.
- Netlify or Vercel for static deployment.

If you want a quick public prototype, itch.io is usually the least friction.

## 4. Recommended Next Steps

Short-term:
- Run the first pygbag build locally.
- Fix any browser-specific input or rendering issues.
- Add a start screen that explains controls.

Medium-term:
- Replace keyboard-only assumptions with remappable controls.
- Add browser-friendly scaling and fullscreen behavior.
- Move the score server behind your production web host or proxy it under `/api/flight-game-scores`.
- Protect the admin routes with `FLIGHT_GAME_ADMIN_USERNAME` and `FLIGHT_GAME_ADMIN_PASSWORD`, or keep `FLIGHT_GAME_ADMIN_TOKEN` behind your hosting gateway before public release.

## 6. Simplest Shared Score Setup

For the simplest public setup, use:

1. GitHub Pages for the game.
2. Supabase for the live scoreboard.
3. A `flight-game-config.json` file beside the published `index.html` that contains your Supabase URL and anon key.

See [web/SUPABASE_SETUP.md](c:/Users/conor/Game%201/web/SUPABASE_SETUP.md) for the exact table schema and config format.

## 5. Recommended Production Proxy

On Windows, Caddy is the lowest-friction production proxy for this project because it can:
- Automatically provision and renew HTTPS certificates.
- Redirect HTTP to HTTPS.
- Serve the static pygbag build.
- Reverse proxy the score API and admin page to the Python backend running on `127.0.0.1:8765`.

Use [web/Caddyfile.flight-game](c:/Users/conor/Game%201/web/Caddyfile.flight-game) as the starting point.

Recommended backend environment for production:

```powershell
$env:FLIGHT_GAME_SCORE_SERVER_HOST = "127.0.0.1"
$env:FLIGHT_GAME_TRUST_PROXY_HEADERS = "1"
$env:FLIGHT_GAME_ADMIN_USERNAME = "admin"
$env:FLIGHT_GAME_ADMIN_PASSWORD = "choose-a-strong-password"
python .\flight_game_score_server.py
```

Then run Caddy with:

```powershell
$env:FLIGHT_GAME_DOMAIN = "flightgame.example.com"
$env:FLIGHT_GAME_ACME_EMAIL = "you@example.com"
$env:FLIGHT_GAME_WEB_ROOT = "c:/Users/conor/Game 1/web/flight-game-v3/build/web"
caddy run --config .\Caddyfile.flight-game
```

This keeps the Python server off the public network while Caddy handles HTTPS and forwards only the required routes.

Long-term:
- If you want a polished public web game, rebuild in Phaser or Godot HTML5.