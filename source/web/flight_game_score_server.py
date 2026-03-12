import json
import os
import time
import base64
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


SERVER_HOST = os.environ.get("FLIGHT_GAME_SCORE_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.environ.get("FLIGHT_GAME_SCORE_SERVER_PORT", "8765"))
DEFAULT_SCORE_FILE = os.path.join(os.path.dirname(__file__), "flight_game_web_scores.json")
SCORE_FILE = os.environ.get("FLIGHT_GAME_SCOREBOARD_FILE", DEFAULT_SCORE_FILE)
LOCK_FILE = f"{SCORE_FILE}.lock"
LOCK_TIMEOUT = 5.0
LOCK_POLL_INTERVAL = 0.1
API_ROOT = "/api/flight-game-scores"
ADMIN_ROOT = "/admin/flight-game-scores"
ADMIN_PAGE_PATH = os.path.join(os.path.dirname(__file__), "flight_game_score_admin.html")
ADMIN_TOKEN = os.environ.get("FLIGHT_GAME_ADMIN_TOKEN", "")
ADMIN_USERNAME = os.environ.get("FLIGHT_GAME_ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.environ.get("FLIGHT_GAME_ADMIN_PASSWORD", "")
DEFAULT_AUDIT_LOG_FILE = os.path.join(os.path.dirname(__file__), "flight_game_admin_audit.jsonl")
AUDIT_LOG_FILE = os.environ.get("FLIGHT_GAME_AUDIT_LOG_FILE", DEFAULT_AUDIT_LOG_FILE)
TRUST_PROXY_HEADERS = os.environ.get("FLIGHT_GAME_TRUST_PROXY_HEADERS", "0").strip().lower() in ("1", "true", "yes", "on")


AUDIT_LOG_MUTEX = threading.Lock()


def normalize_player_name(name):
    return " ".join(str(name).strip().split())


def get_empty_player_record(name):
    return {"name": name, "wins": 0, "losses": 0, "games_started": 0}


def sanitize_player_record(entry, fallback_name=""):
    if not isinstance(entry, dict):
        entry = {}

    name = normalize_player_name(entry.get("name", fallback_name))
    if not name:
        return None

    cleaned = get_empty_player_record(name)
    for field in ("wins", "losses", "games_started"):
        try:
            cleaned[field] = max(0, int(entry.get(field, 0)))
        except (TypeError, ValueError):
            cleaned[field] = 0
    return cleaned


@contextmanager
def scoreboard_lock():
    lock_fd = None
    start_time = time.time()
    while lock_fd is None:
        try:
            lock_fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            if time.time() - start_time >= LOCK_TIMEOUT:
                raise TimeoutError("Timed out waiting for the scoreboard lock.")
            time.sleep(LOCK_POLL_INTERVAL)

    try:
        yield
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass


def load_scoreboard_unlocked():
    if not os.path.exists(SCORE_FILE):
        return {}

    try:
        with open(SCORE_FILE, "r", encoding="utf-8") as score_file:
            payload = json.load(score_file)
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(payload, dict):
        return {}

    players = payload.get("players", {})
    if not isinstance(players, dict):
        return {}

    cleaned_players = {}
    for key, entry in players.items():
        cleaned_entry = sanitize_player_record(entry, key)
        if cleaned_entry is not None:
            cleaned_players[key] = cleaned_entry
    return cleaned_players


def save_scoreboard_unlocked(player_stats):
    payload = {"players": player_stats}
    with open(SCORE_FILE, "w", encoding="utf-8") as score_file:
        json.dump(payload, score_file, indent=2)


def ensure_player_profile(player_stats, name):
    normalized_name = normalize_player_name(name)
    if not normalized_name:
        return None

    player_key = normalized_name.casefold()
    player_entry = player_stats.get(player_key)
    if player_entry is None:
        player_entry = get_empty_player_record(normalized_name)
        player_stats[player_key] = player_entry
    else:
        player_entry["name"] = normalized_name
    return player_key


def register_players(player_stats, player_names):
    registered_keys = []
    for name in player_names:
        player_key = ensure_player_profile(player_stats, name)
        if player_key is None:
            continue
        player_stats[player_key]["games_started"] += 1
        registered_keys.append(player_key)
    return registered_keys


def record_match_result(player_stats, winner_name, loser_name):
    winner_key = ensure_player_profile(player_stats, winner_name)
    loser_key = ensure_player_profile(player_stats, loser_name)
    if winner_key is None or loser_key is None or winner_key == loser_key:
        return False

    player_stats[winner_key]["wins"] += 1
    player_stats[loser_key]["losses"] += 1
    return True


def upsert_player_record(player_stats, player_data):
    cleaned_entry = sanitize_player_record(player_data)
    if cleaned_entry is None:
        return None

    player_key = cleaned_entry["name"].casefold()
    player_stats[player_key] = cleaned_entry
    return player_key


def delete_player_record(player_stats, name):
    normalized_name = normalize_player_name(name)
    if not normalized_name:
        return False

    player_key = normalized_name.casefold()
    if player_key not in player_stats:
        return False

    del player_stats[player_key]
    return True


def get_sorted_top_scores(player_stats):
    return sorted(
        player_stats.values(),
        key=lambda entry: (
            -(entry["wins"] - entry["losses"]),
            -entry["wins"],
            entry["losses"],
            entry["name"].casefold(),
        ),
    )


def merge_scoreboards(existing_stats, imported_stats):
    merged_stats = {
        key: sanitize_player_record(entry, key)
        for key, entry in existing_stats.items()
        if sanitize_player_record(entry, key) is not None
    }

    for key, entry in imported_stats.items():
        cleaned_entry = sanitize_player_record(entry, key)
        if cleaned_entry is None:
            continue

        current_entry = merged_stats.get(key)
        if current_entry is None:
            merged_stats[key] = cleaned_entry
            continue

        current_entry["name"] = cleaned_entry["name"]
        current_entry["wins"] = max(current_entry["wins"], cleaned_entry["wins"])
        current_entry["losses"] = max(current_entry["losses"], cleaned_entry["losses"])
        current_entry["games_started"] = max(current_entry["games_started"], cleaned_entry["games_started"])

    return merged_stats


def parse_imported_scoreboard(payload):
    if not isinstance(payload, dict):
        raise ValueError("import payload must be a JSON object")

    players = payload.get("players", payload)
    if not isinstance(players, dict):
        raise ValueError("import payload must contain a players object")

    imported_stats = {}
    for key, entry in players.items():
        cleaned_entry = sanitize_player_record(entry, key)
        if cleaned_entry is not None:
            imported_stats[cleaned_entry["name"].casefold()] = cleaned_entry
    return imported_stats


def append_audit_event(event):
    os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
    line = json.dumps(event, sort_keys=True)
    with AUDIT_LOG_MUTEX:
        with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as audit_file:
            audit_file.write(line)
            audit_file.write("\n")


class FlightGameScoreHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_common_headers("application/json; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed_url = urlparse(self.path)
        route = parsed_url.path.rstrip("/") or "/"
        query = parse_qs(parsed_url.query)

        try:
            if route == ADMIN_ROOT:
                if not self.is_admin_authorized():
                    self.send_admin_auth_challenge()
                    return
                self.write_audit_event("admin_page_view")
                self.send_admin_page()
                return

            if route == API_ROOT:
                with scoreboard_lock():
                    player_stats = load_scoreboard_unlocked()
                self.send_json(200, {"players": player_stats})
                return

            if route == f"{API_ROOT}/register":
                names = query.get("name", [])
                with scoreboard_lock():
                    player_stats = load_scoreboard_unlocked()
                    register_players(player_stats, names)
                    save_scoreboard_unlocked(player_stats)
                self.send_json(200, {"players": player_stats})
                return

            if route == f"{API_ROOT}/record-match":
                winner_name = query.get("winner", [""])[0]
                loser_name = query.get("loser", [""])[0]
                with scoreboard_lock():
                    player_stats = load_scoreboard_unlocked()
                    if not record_match_result(player_stats, winner_name, loser_name):
                        self.send_json(400, {"error": "winner and loser must be different non-empty names"})
                        return
                    save_scoreboard_unlocked(player_stats)
                self.send_json(200, {"players": player_stats})
                return

            if route == f"{API_ROOT}/admin/export":
                if not self.is_admin_authorized():
                    self.send_admin_auth_challenge()
                    return

                with scoreboard_lock():
                    player_stats = load_scoreboard_unlocked()
                self.write_audit_event(
                    "admin_export",
                    details={"player_count": len(player_stats)},
                )
                self.send_bytes(
                    200,
                    json.dumps({"players": player_stats}, indent=2).encode("utf-8"),
                    "application/json; charset=utf-8",
                    extra_headers={"Content-Disposition": 'attachment; filename="flight-game-scoreboard-backup.json"'},
                )
                return

            if route == "/health":
                self.send_json(200, {"status": "ok"})
                return

            self.send_json(404, {"error": "not found"})
        except TimeoutError as exc:
            self.send_json(503, {"error": str(exc)})
        except OSError as exc:
            self.send_json(500, {"error": str(exc)})

    def do_POST(self):
        parsed_url = urlparse(self.path)
        route = parsed_url.path.rstrip("/") or "/"

        try:
            if route == f"{API_ROOT}/admin/upsert":
                if not self.is_admin_authorized():
                    self.send_admin_auth_challenge(json_payload={"error": "admin authentication required"})
                    return

                payload = self.read_json_payload()
                player_payload = payload.get("player") if isinstance(payload, dict) else None
                if not isinstance(player_payload, dict):
                    self.send_json(400, {"error": "player payload is required"})
                    return

                with scoreboard_lock():
                    player_stats = load_scoreboard_unlocked()
                    player_key = upsert_player_record(player_stats, player_payload)
                    if player_key is None:
                        self.send_json(400, {"error": "a valid player name is required"})
                        return
                    save_scoreboard_unlocked(player_stats)
                self.write_audit_event(
                    "admin_upsert",
                    details={"player_key": player_key, "player": player_stats.get(player_key, {})},
                )
                self.send_json(200, {"players": player_stats, "player_key": player_key})
                return

            if route == f"{API_ROOT}/admin/delete":
                if not self.is_admin_authorized():
                    self.send_admin_auth_challenge(json_payload={"error": "admin authentication required"})
                    return

                payload = self.read_json_payload()
                player_name = payload.get("name", "") if isinstance(payload, dict) else ""
                with scoreboard_lock():
                    player_stats = load_scoreboard_unlocked()
                    if not delete_player_record(player_stats, player_name):
                        self.send_json(404, {"error": "player not found"})
                        return
                    save_scoreboard_unlocked(player_stats)
                self.write_audit_event(
                    "admin_delete",
                    details={"player_name": normalize_player_name(player_name)},
                )
                self.send_json(200, {"players": player_stats})
                return

            if route == f"{API_ROOT}/admin/reset":
                if not self.is_admin_authorized():
                    self.send_admin_auth_challenge(json_payload={"error": "admin authentication required"})
                    return

                with scoreboard_lock():
                    player_stats = {}
                    save_scoreboard_unlocked(player_stats)
                self.write_audit_event("admin_reset")
                self.send_json(200, {"players": player_stats})
                return

            if route == f"{API_ROOT}/admin/import":
                if not self.is_admin_authorized():
                    self.send_admin_auth_challenge(json_payload={"error": "admin authentication required"})
                    return

                payload = self.read_json_payload()
                mode = str(payload.get("mode", "replace")).lower()
                if mode not in ("replace", "merge"):
                    self.send_json(400, {"error": "mode must be replace or merge"})
                    return

                imported_stats = parse_imported_scoreboard(payload.get("scoreboard", payload))
                with scoreboard_lock():
                    player_stats = load_scoreboard_unlocked()
                    if mode == "replace":
                        player_stats = imported_stats
                    else:
                        player_stats = merge_scoreboards(player_stats, imported_stats)
                    save_scoreboard_unlocked(player_stats)
                self.write_audit_event(
                    "admin_import",
                    details={"mode": mode, "imported_player_count": len(imported_stats), "result_player_count": len(player_stats)},
                )
                self.send_json(200, {"players": player_stats, "mode": mode})
                return

            self.send_json(404, {"error": "not found"})
        except TimeoutError as exc:
            self.send_json(503, {"error": str(exc)})
        except OSError as exc:
            self.send_json(500, {"error": str(exc)})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})

    def log_message(self, format_string, *args):
        return

    def send_common_headers(self, content_type):
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Token")

    def get_authenticated_admin_identity(self):
        if self.has_valid_basic_auth():
            return ADMIN_USERNAME, "basic"
        if ADMIN_TOKEN and self.headers.get("X-Admin-Token", "") == ADMIN_TOKEN:
            return "token-admin", "token"
        return "anonymous", "none"

    def get_client_ip(self):
        if TRUST_PROXY_HEADERS:
            forwarded_for = self.headers.get("X-Forwarded-For", "")
            if forwarded_for:
                return forwarded_for.split(",")[0].strip() or self.client_address[0]
        return self.client_address[0]

    def write_audit_event(self, action, details=None):
        actor, auth_type = self.get_authenticated_admin_identity()
        event = {
            "action": action,
            "actor": actor,
            "auth_type": auth_type,
            "client_ip": self.get_client_ip(),
            "forwarded_proto": self.headers.get("X-Forwarded-Proto", ""),
            "method": self.command,
            "path": self.path,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if details:
            event["details"] = details
        append_audit_event(event)

    def admin_basic_auth_enabled(self):
        return bool(ADMIN_USERNAME and ADMIN_PASSWORD)

    def has_valid_basic_auth(self):
        if not self.admin_basic_auth_enabled():
            return False

        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return False

        try:
            decoded = base64.b64decode(auth_header[6:].encode("ascii")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False

        username, separator, password = decoded.partition(":")
        if not separator:
            return False
        return username == ADMIN_USERNAME and password == ADMIN_PASSWORD

    def read_json_payload(self):
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw_body:
            return {}
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid JSON payload") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def is_admin_authorized(self):
        if self.has_valid_basic_auth():
            return True
        if self.admin_basic_auth_enabled():
            return False
        if not ADMIN_TOKEN:
            return True
        header_token = self.headers.get("X-Admin-Token", "")
        return header_token == ADMIN_TOKEN

    def send_admin_auth_challenge(self, json_payload=None):
        self.write_audit_event("admin_auth_failed")
        if self.admin_basic_auth_enabled():
            if json_payload is None:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="Flight Game Admin"')
                self.send_common_headers("text/plain; charset=utf-8")
                body = b"Authentication required"
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            encoded_payload = json.dumps(json_payload, indent=2).encode("utf-8")
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="Flight Game Admin"')
            self.send_common_headers("application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded_payload)))
            self.end_headers()
            self.wfile.write(encoded_payload)
            return

        self.send_json(403, json_payload or {"error": "admin token required"})

    def send_admin_page(self):
        with open(ADMIN_PAGE_PATH, "rb") as admin_file:
            page_bytes = admin_file.read()
        self.send_response(200)
        self.send_common_headers("text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page_bytes)))
        self.end_headers()
        self.wfile.write(page_bytes)

    def send_bytes(self, status_code, payload, content_type, extra_headers=None):
        self.send_response(status_code)
        self.send_common_headers(content_type)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status_code, payload):
        encoded_payload = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_common_headers("application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded_payload)))
        self.end_headers()
        self.wfile.write(encoded_payload)


def main():
    os.makedirs(os.path.dirname(SCORE_FILE), exist_ok=True)
    server = ThreadingHTTPServer((SERVER_HOST, SERVER_PORT), FlightGameScoreHandler)
    print(f"Flight Game score server listening on http://{SERVER_HOST}:{SERVER_PORT}{API_ROOT}")
    print(f"Admin page: http://{SERVER_HOST}:{SERVER_PORT}{ADMIN_ROOT}")
    print(f"Score file: {SCORE_FILE}")
    print(f"Audit log file: {AUDIT_LOG_FILE}")
    if ADMIN_USERNAME and ADMIN_PASSWORD:
        print("Admin protection: HTTP Basic auth enabled")
    elif ADMIN_TOKEN:
        print("Admin protection: X-Admin-Token enabled")
    else:
        print("Admin protection: disabled")
    if TRUST_PROXY_HEADERS:
        print("Proxy headers: trusted for logging")
    else:
        print("Proxy headers: ignored")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()