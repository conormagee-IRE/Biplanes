# Biplanes

This repository currently serves the published web build from the repository root.

Source for the current Python/Pygame version and the score server lives under [source](source):

- [source/Flight Game 3 V3.py](source/Flight%20Game%203%20V3.py): current game source
- [source/WEB_PUBLISHING_GUIDE.md](source/WEB_PUBLISHING_GUIDE.md): build and publishing notes
- [source/web](source/web): web build scripts, score server, admin page, and reverse-proxy config

For public hosting, the intended production setup is:

1. Serve the static web build from the repository root or another static host.
2. Run the score server from [source/web/flight_game_score_server.py](source/web/flight_game_score_server.py) behind HTTPS.
3. Put a reverse proxy such as Caddy in front of it using [source/web/Caddyfile.flight-game](source/web/Caddyfile.flight-game).

Generated runtime files such as scores and audit logs are intentionally excluded from git.