import math
import random
import json
import os
import sys
import asyncio
import time
import traceback
from contextlib import contextmanager
from urllib.parse import urlencode
import pygame

try:
    from platform import window as browser_window
except ImportError:
    browser_window = None

# ---------- Config ----------
WIDTH, HEIGHT = 1280, 720
GROUND_HEIGHT = 80

FPS = 120
DT = 1 / FPS
SIMULATION_SPEED = 0.75
MAX_FRAME_TIME = 0.1

# Physics constants
GRAVITY = 200.0
STALL_SPEED = 150.0
MAX_THRUST_ACCEL = 300.0
DRAG_COEFF = 0.002
AOA_DRAG_FACTOR = 0.5
THROTTLE_RAMP_RATE = 2
LANDING_MAX_SPEED = 250.0
LANDING_MAX_DESCENT = 200.0
GROUND_FRICTION = 180.0
BULLET_MUZZLE_SPEED = 500.0
MAX_ACTIVE_BULLETS = 3
CLOUD_COUNT = 7
CLOUD_MIN_SCALE = 1.7
CLOUD_MAX_SCALE = 4.0
CLOUD_MIN_SPEED = 10.0
CLOUD_MAX_SPEED = 35.0
LIGHTNING_MIN_INTERVAL = 1.8
LIGHTNING_MAX_INTERVAL = 4.5
LIGHTNING_FLASH_DURATION = 0.22
BUILDING_WIDTH = 150
BUILDING_HEIGHT = 64
WIND_GUST_MIN_INTERVAL = 2.0
WIND_GUST_MAX_INTERVAL = 5.0
WIND_GUST_MIN_DURATION = 2.0
WIND_GUST_MAX_DURATION = 4.0
WIND_GUST_MIN_WIDTH = 220
WIND_GUST_MAX_WIDTH = 420
WIND_GUST_MIN_HEIGHT = 160
WIND_GUST_MAX_HEIGHT = 320
WIND_GUST_MIN_SPEED = 500.0
WIND_GUST_MAX_SPEED = 500.0
WEATHER_CLEAR_DURATION = 60.0
WEATHER_CLOUD_DURATION = 0.0
WEATHER_STORM_DURATION = 30.0
STORM_CLOUD_FADE_DURATION = 4.0
MATCH_WIN_SCORE = 5
DEFAULT_PLAYER_STATS_FILE = os.path.join(os.path.dirname(__file__), "flight_game_global_scores.json")
PLAYER_STATS_FILE = os.environ.get("FLIGHT_GAME_SCOREBOARD_FILE", DEFAULT_PLAYER_STATS_FILE)
PLAYER_STATS_STORAGE_KEY = "flight-game-player-stats"
PLAYER_STATS_LOCK_FILE = f"{PLAYER_STATS_FILE}.lock"
PLAYER_STATS_LOCK_TIMEOUT = 5.0
PLAYER_STATS_LOCK_POLL_INTERVAL = 0.1
DEFAULT_WEB_SCORE_API_PATH = "/api/flight-game-scores"
DEFAULT_WEB_SCORE_API_PORT = "8765"
WEB_SCORE_REQUEST_TIMEOUT = 5.0
DEFAULT_WEB_CONFIG_FILE = "flight-game-config.json"
DEFAULT_SUPABASE_URL = "https://ezcrxevguuzktxbvljfp.supabase.co"
DEFAULT_SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImV6Y3J4ZXZndXV6a3R4YnZsamZwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMzNTQ3NzQsImV4cCI6MjA4ODkzMDc3NH0.loatpd6jMaEC7hPuN2gZnJfaks1hey0x2K3S96vC8eU"
DEFAULT_SUPABASE_TABLE = "flight_game_scores"
IS_WEB = sys.platform in ("emscripten", "wasi") or browser_window is not None
UI_FONT_NAME = "arial" if IS_WEB else "consolas"
WEB_RUNTIME_CONFIG = None

# Plane drawing
PLANE_LENGTH = 32
PLANE_WIDTH = 16

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("2D Flight Simulator - Dogfight Mode")
clock = pygame.time.Clock()
font = pygame.font.SysFont(UI_FONT_NAME, 22 if IS_WEB else 20)
title_font = pygame.font.SysFont(UI_FONT_NAME, 50 if IS_WEB else 40, bold=True)
subtitle_font = pygame.font.SysFont(UI_FONT_NAME, 32 if IS_WEB else 28, bold=True)
small_font = pygame.font.SysFont(UI_FONT_NAME, 22 if IS_WEB else 18)


def normalize_player_name(name):
    return " ".join(name.strip().split())


def get_empty_player_record(name):
    return {"name": name, "wins": 0, "losses": 0, "games_started": 0}


def sanitize_player_record(entry, fallback_name=""):
    if not isinstance(entry, dict):
        entry = {}

    name = normalize_player_name(str(entry.get("name", fallback_name)))
    if not name:
        return None

    cleaned_entry = get_empty_player_record(name)
    for field in ("wins", "losses", "games_started"):
        try:
            cleaned_entry[field] = max(0, int(entry.get(field, 0)))
        except (TypeError, ValueError):
            cleaned_entry[field] = 0
    return cleaned_entry


def get_player_net_score(entry):
    return entry["wins"] - entry["losses"]


def get_browser_hostname():
    if browser_window is None:
        return ""

    try:
        return str(browser_window.location.hostname)
    except Exception:
        return ""


def get_window_config_value(name):
    if browser_window is None:
        return None

    try:
        value = getattr(browser_window, name, None)
    except Exception:
        return None
    return value if value not in (None, "") else None


def get_cached_web_config_value(name):
    if not isinstance(WEB_RUNTIME_CONFIG, dict):
        return None
    value = WEB_RUNTIME_CONFIG.get(name)
    return value if value not in (None, "") else None


def get_web_runtime_config_urls():
    if browser_window is None:
        return [DEFAULT_WEB_CONFIG_FILE]

    try:
        href = str(browser_window.location.href).split("#", 1)[0].split("?", 1)[0]
    except Exception:
        href = ""

    try:
        origin = str(browser_window.location.origin).rstrip("/")
    except Exception:
        origin = ""

    try:
        pathname = str(browser_window.location.pathname)
    except Exception:
        pathname = ""

    candidate_urls = [DEFAULT_WEB_CONFIG_FILE]

    if href and "/" in href:
        candidate_urls.append(f"{href.rsplit('/', 1)[0]}/{DEFAULT_WEB_CONFIG_FILE}")

    normalized_path = pathname.split("#", 1)[0].split("?", 1)[0].strip()
    if normalized_path:
        if normalized_path.endswith("/"):
            base_path = normalized_path.rstrip("/")
        elif "." in normalized_path.rsplit("/", 1)[-1]:
            base_path = normalized_path.rsplit("/", 1)[0]
        else:
            base_path = normalized_path

        if origin:
            if base_path:
                candidate_urls.append(f"{origin}{base_path}/{DEFAULT_WEB_CONFIG_FILE}")
            candidate_urls.append(f"{origin}/{DEFAULT_WEB_CONFIG_FILE}")

    unique_urls = []
    seen_urls = set()
    for candidate in candidate_urls:
        if not candidate or candidate in seen_urls:
            continue
        seen_urls.add(candidate)
        unique_urls.append(candidate)
    return unique_urls


async def fetch_browser_text_via_js(url, method="GET", headers=None, body=None):
    if browser_window is None:
        return None

    eval_function = getattr(browser_window, "eval", None)
    if eval_function is None:
        return None

    request_id = f"flight_game_fetch_{pygame.time.get_ticks()}_{random.randint(1000, 9999)}"
    request_script = f"""
(() => {{
  const store = window.__flightGameFetchResults || (window.__flightGameFetchResults = {{}});
  fetch({json.dumps(url)}, {{
    method: {json.dumps(method)},
    headers: {json.dumps(headers or {})},
    body: {json.dumps(body) if body is not None else 'null'}
  }})
    .then(async (response) => {{
      const text = await response.text();
      store[{json.dumps(request_id)}] = JSON.stringify({{
        ok: !!response.ok,
        status: response.status,
        text
      }});
    }})
    .catch((error) => {{
      store[{json.dumps(request_id)}] = JSON.stringify({{
        ok: false,
        status: 0,
        error: String(error)
      }});
    }});
}})();
"""

    try:
        eval_function(request_script)
    except Exception:
        return None

    request_lookup = f"window.__flightGameFetchResults && window.__flightGameFetchResults[{json.dumps(request_id)}]"
    request_cleanup = f"if (window.__flightGameFetchResults) delete window.__flightGameFetchResults[{json.dumps(request_id)}]"
    deadline = time.monotonic() + WEB_SCORE_REQUEST_TIMEOUT
    while time.monotonic() < deadline:
        try:
            result_payload = eval_function(request_lookup)
        except Exception:
            result_payload = None

        if result_payload not in (None, "", "undefined"):
            try:
                eval_function(request_cleanup)
            except Exception:
                pass

            try:
                result_data = json.loads(str(result_payload))
            except (TypeError, ValueError, json.JSONDecodeError):
                return None

            if not result_data.get("ok"):
                return None
            return str(result_data.get("text", ""))

        await asyncio.sleep(0.05)

    try:
        eval_function(request_cleanup)
    except Exception:
        pass
    return None


async def fetch_browser_json(url, params=None, method="GET", headers=None, body=None):
    if browser_window is None:
        return None

    query_params = list(params or [])
    query_params.append(("_ts", str(pygame.time.get_ticks())))
    query_string = urlencode(query_params, doseq=True)
    if query_string:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query_string}"

    fetch_options = {"method": method}
    if headers:
        fetch_options["headers"] = headers
    if body is not None:
        fetch_options["body"] = body

    if headers or body is not None:
        payload = await fetch_browser_text_via_js(url, method=method, headers=headers, body=body)
        if payload is None:
            return None

        try:
            return json.loads(str(payload))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    try:
        response = await asyncio.wait_for(browser_window.fetch(url, fetch_options), timeout=WEB_SCORE_REQUEST_TIMEOUT)
        status_ok = bool(response.ok)
    except Exception:
        return None

    if not status_ok:
        return None

    try:
        payload = await asyncio.wait_for(response.text(), timeout=WEB_SCORE_REQUEST_TIMEOUT)
    except Exception:
        return None

    try:
        return json.loads(str(payload))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


async def ensure_web_runtime_config_loaded():
    global WEB_RUNTIME_CONFIG

    if isinstance(WEB_RUNTIME_CONFIG, dict) and WEB_RUNTIME_CONFIG:
        return WEB_RUNTIME_CONFIG

    if browser_window is None:
        WEB_RUNTIME_CONFIG = {}
        return WEB_RUNTIME_CONFIG

    for config_url in get_web_runtime_config_urls():
        payload = await fetch_browser_json(config_url, params=[])
        if isinstance(payload, dict):
            WEB_RUNTIME_CONFIG = payload
            return WEB_RUNTIME_CONFIG

    WEB_RUNTIME_CONFIG = {}
    return WEB_RUNTIME_CONFIG


def get_supabase_url():
    configured_value = get_window_config_value("FLIGHT_GAME_SUPABASE_URL")
    if configured_value is None:
        configured_value = get_cached_web_config_value("supabaseUrl")
    if configured_value is None:
        configured_value = DEFAULT_SUPABASE_URL
    return str(configured_value).rstrip("/")


def get_supabase_anon_key():
    configured_value = get_window_config_value("FLIGHT_GAME_SUPABASE_ANON_KEY")
    if configured_value is None:
        configured_value = get_cached_web_config_value("supabaseAnonKey")
    if configured_value is None:
        configured_value = DEFAULT_SUPABASE_ANON_KEY
    return str(configured_value)


def get_supabase_table_name():
    configured_value = get_cached_web_config_value("supabaseTable")
    if configured_value is None:
        return DEFAULT_SUPABASE_TABLE
    return str(configured_value)


def should_use_supabase():
    return bool(get_supabase_url() and get_supabase_anon_key())


def should_use_web_score_api():
    if browser_window is None:
        return False

    configured_url = get_window_config_value("FLIGHT_GAME_SCORE_API_URL")
    if configured_url is None:
        configured_url = get_cached_web_config_value("scoreApiUrl")

    if configured_url:
        return True

    hostname = get_browser_hostname()
    if hostname in ("localhost", "127.0.0.1"):
        return True

    if hostname.endswith(".github.io") or hostname == "github.io":
        return False

    return True


def get_web_score_api_url():
    if browser_window is None:
        return DEFAULT_WEB_SCORE_API_PATH

    configured_url = get_window_config_value("FLIGHT_GAME_SCORE_API_URL")
    if configured_url is None:
        configured_url = get_cached_web_config_value("scoreApiUrl")

    if configured_url:
        return str(configured_url).rstrip("/")

    try:
        origin = str(browser_window.location.origin)
    except Exception:
        origin = ""

    hostname = get_browser_hostname()

    if hostname in ("localhost", "127.0.0.1"):
        return f"http://{hostname}:{DEFAULT_WEB_SCORE_API_PORT}{DEFAULT_WEB_SCORE_API_PATH}"

    if origin and origin != "null":
        return f"{origin}{DEFAULT_WEB_SCORE_API_PATH}"
    return DEFAULT_WEB_SCORE_API_PATH


async def fetch_web_score_json(endpoint="", params=None):
    if browser_window is None or not should_use_web_score_api():
        return None
    url = f"{get_web_score_api_url().rstrip('/')}{endpoint}"
    return await fetch_browser_json(url, params=params)


def deserialize_supabase_rows(rows):
    if not isinstance(rows, list):
        return {}

    cleaned_players = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        player_key = str(row.get("player_key", "")).strip().casefold()
        cleaned_entry = sanitize_player_record(row, str(row.get("name", player_key)))
        if not player_key or cleaned_entry is None:
            continue
        cleaned_players[player_key] = cleaned_entry
    return cleaned_players


def build_supabase_headers(include_json_content=False, prefer_header=None):
    anon_key = get_supabase_anon_key()
    headers = {
        "apikey": anon_key,
        "Authorization": f"Bearer {anon_key}",
        "Accept": "application/json",
    }
    if include_json_content:
        headers["Content-Type"] = "application/json"
    if prefer_header:
        headers["Prefer"] = prefer_header
    return headers


def build_supabase_record(player_key, entry):
    return {
        "player_key": player_key,
        "name": entry["name"],
        "wins": entry["wins"],
        "losses": entry["losses"],
        "games_started": entry["games_started"],
    }


async def load_supabase_player_stats():
    rows = await fetch_browser_json(
        f"{get_supabase_url()}/rest/v1/{get_supabase_table_name()}",
        params=[("select", "player_key,name,wins,losses,games_started")],
        headers=build_supabase_headers(),
    )
    return deserialize_supabase_rows(rows)


async def upsert_supabase_player_stats(player_stats, player_keys):
    payload = []
    for player_key in player_keys:
        entry = player_stats.get(player_key)
        if entry is None:
            continue
        payload.append(build_supabase_record(player_key, entry))

    if not payload:
        return False

    rows = await fetch_browser_json(
        f"{get_supabase_url()}/rest/v1/{get_supabase_table_name()}",
        params=[("on_conflict", "player_key")],
        method="POST",
        headers=build_supabase_headers(
            include_json_content=True,
            prefer_header="resolution=merge-duplicates,return=representation",
        ),
        body=json.dumps(payload),
    )

    if not isinstance(rows, list):
        return False

    latest_rows = deserialize_supabase_rows(rows)
    for player_key, entry in latest_rows.items():
        player_stats[player_key] = entry
    return True


def apply_player_stats_snapshot(player_stats, snapshot):
    player_stats.clear()
    player_stats.update(snapshot)


@contextmanager
def player_stats_lock():
    if IS_WEB:
        yield
        return

    lock_fd = None
    start_time = time.time()
    while lock_fd is None:
        try:
            lock_fd = os.open(PLAYER_STATS_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            if time.time() - start_time >= PLAYER_STATS_LOCK_TIMEOUT:
                raise TimeoutError("Timed out waiting for the shared score file lock.")
            time.sleep(PLAYER_STATS_LOCK_POLL_INTERVAL)

    try:
        yield
    finally:
        if lock_fd is not None:
            os.close(lock_fd)
        try:
            os.remove(PLAYER_STATS_LOCK_FILE)
        except FileNotFoundError:
            pass


def read_stats_payload():
    if IS_WEB and browser_window is not None:
        try:
            payload = browser_window.localStorage.getItem(PLAYER_STATS_STORAGE_KEY)
        except Exception:
            return None
        return payload if payload else None

    if not os.path.exists(PLAYER_STATS_FILE):
        return None

    try:
        with open(PLAYER_STATS_FILE, "r", encoding="utf-8") as stats_file:
            return stats_file.read()
    except OSError:
        return None


def write_stats_payload(payload):
    if IS_WEB and browser_window is not None:
        try:
            browser_window.localStorage.setItem(PLAYER_STATS_STORAGE_KEY, payload)
        except Exception:
            pass
        return

    with open(PLAYER_STATS_FILE, "w", encoding="utf-8") as stats_file:
        stats_file.write(payload)


def deserialize_player_stats(payload):
    if not payload:
        return {}

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}

    if not isinstance(data, dict):
        return {}

    players = data.get("players", {})
    if not isinstance(players, dict):
        return {}

    cleaned_players = {}
    for key, entry in players.items():
        cleaned_entry = sanitize_player_record(entry, str(key))
        if cleaned_entry is None:
            continue
        cleaned_players[key] = cleaned_entry
    return cleaned_players


async def load_player_stats():
    if IS_WEB:
        await ensure_web_runtime_config_loaded()
        if should_use_supabase():
            return await load_supabase_player_stats()
        response_payload = await fetch_web_score_json()
        if isinstance(response_payload, dict):
            return deserialize_player_stats(json.dumps(response_payload))
        return {}

    return deserialize_player_stats(read_stats_payload())


def merge_player_stats(existing_stats, updated_stats):
    merged_stats = {
        key: sanitize_player_record(entry, key)
        for key, entry in existing_stats.items()
        if sanitize_player_record(entry, key) is not None
    }

    for key, entry in updated_stats.items():
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


def save_player_stats(player_stats):
    if IS_WEB:
        return

    with player_stats_lock():
        stored_stats = deserialize_player_stats(read_stats_payload())
        merged_stats = merge_player_stats(stored_stats, player_stats)
        write_stats_payload(json.dumps({"players": merged_stats}, indent=2))

    apply_player_stats_snapshot(player_stats, merged_stats)


async def register_players_for_match(player_stats, player_names):
    if IS_WEB:
        await ensure_web_runtime_config_loaded()
        if should_use_supabase():
            updated_keys = []
            for name in player_names:
                player_key = ensure_player_profile(player_stats, name)
                player_stats[player_key]["games_started"] += 1
                updated_keys.append(player_key)

            if await upsert_supabase_player_stats(player_stats, updated_keys):
                return

        response_payload = await fetch_web_score_json(
            "/register",
            [("name", name) for name in player_names],
        )
        if isinstance(response_payload, dict):
            apply_player_stats_snapshot(player_stats, deserialize_player_stats(json.dumps(response_payload)))
            return

    for name in player_names:
        player_key = ensure_player_profile(player_stats, name)
        player_stats[player_key]["games_started"] += 1

    if not IS_WEB:
        save_player_stats(player_stats)


async def record_match_result(player_stats, winner_key, loser_key):
    winner_entry = player_stats.get(winner_key)
    loser_entry = player_stats.get(loser_key)
    if winner_entry is None or loser_entry is None:
        return

    if IS_WEB:
        await ensure_web_runtime_config_loaded()
        if should_use_supabase():
            winner_entry["wins"] += 1
            loser_entry["losses"] += 1
            if await upsert_supabase_player_stats(player_stats, [winner_key, loser_key]):
                return

        response_payload = await fetch_web_score_json(
            "/record-match",
            [("winner", winner_entry["name"]), ("loser", loser_entry["name"])],
        )
        if isinstance(response_payload, dict):
            apply_player_stats_snapshot(player_stats, deserialize_player_stats(json.dumps(response_payload)))
        return

    with player_stats_lock():
        stored_stats = deserialize_player_stats(read_stats_payload())
        merged_stats = merge_player_stats(stored_stats, player_stats)
        merged_winner = merged_stats.setdefault(
            winner_key,
            get_empty_player_record(winner_entry["name"]),
        )
        merged_loser = merged_stats.setdefault(
            loser_key,
            get_empty_player_record(loser_entry["name"]),
        )
        merged_winner["name"] = winner_entry["name"]
        merged_loser["name"] = loser_entry["name"]
        merged_winner["wins"] += 1
        merged_loser["losses"] += 1
        write_stats_payload(json.dumps({"players": merged_stats}, indent=2))

    apply_player_stats_snapshot(player_stats, merged_stats)


async def wait_for_next_frame():
    if IS_WEB:
        await asyncio.sleep(0)
    else:
        clock.tick(FPS)


async def get_frame_time(previous_ticks):
    if IS_WEB:
        await asyncio.sleep(0)
        current_ticks = pygame.time.get_ticks()
        frame_time = (current_ticks - previous_ticks) / 1000.0
        return min(MAX_FRAME_TIME, max(0.0, frame_time)), current_ticks

    frame_time = clock.tick(FPS) / 1000.0
    return min(MAX_FRAME_TIME, max(0.0, frame_time)), previous_ticks


def ensure_player_profile(player_stats, name):
    normalized_name = normalize_player_name(name)
    player_key = normalized_name.casefold()
    if player_key not in player_stats:
        player_stats[player_key] = get_empty_player_record(normalized_name)
    else:
        player_stats[player_key]["name"] = normalized_name
    return player_key


def get_sorted_top_scores(player_stats):
    return sorted(
        player_stats.values(),
        key=lambda entry: (-get_player_net_score(entry), -entry["wins"], entry["losses"], entry["name"].casefold()),
    )


def plane2_fire_pressed(keys):
    return keys[pygame.K_RCTRL] or keys[pygame.K_LCTRL] or keys[pygame.K_SLASH]


def draw_text_centered(surface, text, text_font, color, center_x, top_y):
    image = text_font.render(text, True, color)
    rect = image.get_rect(midtop=(center_x, top_y))
    surface.blit(image, rect)
    return rect


def draw_rect_compat(surface, color, rect, width=0, border_radius=0):
    if border_radius <= 0:
        return pygame.draw.rect(surface, color, rect, width)

    try:
        return pygame.draw.rect(surface, color, rect, width, border_radius=border_radius)
    except TypeError:
        return pygame.draw.rect(surface, color, rect, width)


async def show_fatal_error_screen(error):
    error_lines = traceback.format_exception_only(type(error), error)
    rendered_lines = ["Flight Game failed to start."]
    rendered_lines.extend(line.strip() for line in error_lines if line.strip())
    rendered_lines.append("Press refresh after the issue is fixed.")

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

        screen.fill((18, 22, 32))
        panel_rect = pygame.Rect(80, 80, WIDTH - 160, HEIGHT - 160)
        draw_rect_compat(screen, (238, 241, 246), panel_rect, border_radius=16)
        draw_rect_compat(screen, (138, 28, 28), panel_rect, width=4, border_radius=16)

        y = panel_rect.y + 28
        draw_text_centered(screen, rendered_lines[0], subtitle_font, (120, 18, 18), WIDTH // 2, y)
        y += 64

        for line in rendered_lines[1:]:
            if not line:
                continue
            line_image = small_font.render(line[:110], True, (38, 48, 68))
            screen.blit(line_image, (panel_rect.x + 20, y))
            y += line_image.get_height() + 12

        pygame.display.flip()
        await wait_for_next_frame()


def reset_weather_state():
    return {
        "round_timer": 0.0,
        "clouds": [create_cloud(x=-random.uniform(160, WIDTH + 320)) for _ in range(CLOUD_COUNT)],
        "storm_clouds": [create_storm_cloud(force_visible=False) for _ in range(CLOUD_COUNT)],
        "wind_gust": None,
        "wind_spawn_timer": random.uniform(WIND_GUST_MIN_INTERVAL, WIND_GUST_MAX_INTERVAL),
    }


def reset_round_state(plane1, plane2):
    plane1.reset()
    plane2.reset()
    return reset_weather_state()


def get_weather_stage(round_timer):
    if round_timer < WEATHER_CLEAR_DURATION:
        return "clear"
    if round_timer < WEATHER_CLEAR_DURATION + WEATHER_CLOUD_DURATION:
        return "clouds"
    if round_timer < WEATHER_CLEAR_DURATION + WEATHER_CLOUD_DURATION + WEATHER_STORM_DURATION:
        return "storm"
    return "wind"


def get_storm_fade_progress(round_timer):
    storm_start_time = WEATHER_CLEAR_DURATION + WEATHER_CLOUD_DURATION
    fade_elapsed = max(0.0, round_timer - storm_start_time)
    return max(0.0, min(1.0, fade_elapsed / STORM_CLOUD_FADE_DURATION))


def update_weather(weather_state, dt):
    weather_state["round_timer"] += dt
    stage = get_weather_stage(weather_state["round_timer"])

    if stage in ("clear", "clouds"):
        update_clouds(weather_state["clouds"], dt, recycle=True)

    if stage in ("storm", "wind"):
        update_clouds(weather_state["clouds"], dt, recycle=False)

    if stage in ("storm", "wind"):
        for storm_cloud in weather_state["storm_clouds"]:
            update_storm_cloud(storm_cloud, dt)

    if stage == "wind":
        weather_state["wind_gust"], weather_state["wind_spawn_timer"] = update_wind_gust(
            weather_state["wind_gust"],
            dt,
            weather_state["wind_spawn_timer"],
        )
    else:
        weather_state["wind_gust"] = None

    return stage


def draw_weather(surface, weather_state, stage):
    if stage == "wind":
        draw_wind_gust(surface, weather_state["wind_gust"])

    if stage in ("clear", "clouds", "storm", "wind"):
        draw_clouds(surface, weather_state["clouds"])

    if stage in ("storm", "wind"):
        fade_progress = get_storm_fade_progress(weather_state["round_timer"])
        for storm_cloud in weather_state["storm_clouds"]:
            draw_storm_cloud(surface, storm_cloud, fade_progress)


def get_active_wind(weather_state, stage):
    if stage != "wind":
        return None
    return weather_state["wind_gust"]


def validate_player_names(input_names):
    normalized_names = [normalize_player_name(name) for name in input_names]
    if not normalized_names[0] or not normalized_names[1]:
        return None, "Both players need a name."
    if normalized_names[0].casefold() == normalized_names[1].casefold():
        return None, "Players need different names."
    return normalized_names, ""


def draw_name_entry_screen(input_names, active_index, error_message, player_stats):
    screen.fill((52, 112, 188))
    panel_rect = pygame.Rect(110, 56, WIDTH - 220, HEIGHT - 112)
    draw_rect_compat(screen, (234, 240, 248), panel_rect, border_radius=18)
    draw_rect_compat(screen, (28, 60, 98), panel_rect, width=4, border_radius=18)

    title_top = panel_rect.y + 34
    subtitle_top = title_top + 64
    label_x = panel_rect.x + 112
    field_x = label_x
    field_width = panel_rect.width - 224
    field_height = 64 if IS_WEB else 56
    first_field_top = subtitle_top + 94
    field_gap = 144 if IS_WEB else 135

    draw_text_centered(screen, "Enter Pilot Names", title_font, (24, 36, 52), WIDTH // 2, title_top)
    draw_text_centered(screen, "Starting a match registers each pilot on the global web leaderboard.", small_font, (54, 74, 102), WIDTH // 2, subtitle_top)

    field_rects = []
    for index, label in enumerate(("Player 1", "Player 2")):
        top = first_field_top + index * field_gap
        label_image = subtitle_font.render(label, True, (32, 46, 68))
        screen.blit(label_image, (label_x, top))

        field_rect = pygame.Rect(field_x, top + 48, field_width, field_height)
        field_rects.append(field_rect)
        border_color = (24, 92, 178) if active_index == index else (112, 136, 166)
        draw_rect_compat(screen, (255, 255, 255), field_rect, border_radius=10)
        draw_rect_compat(screen, border_color, field_rect, width=3, border_radius=10)

        entry_text = input_names[index] if input_names[index] else "Type a player name"
        entry_color = (30, 34, 42) if input_names[index] else (142, 148, 160)
        entry_image = font.render(entry_text, True, entry_color)
        screen.blit(entry_image, (field_rect.x + 18, field_rect.y + (field_rect.height - entry_image.get_height()) // 2))

        existing_name = normalize_player_name(input_names[index])
        existing_profile = player_stats.get(existing_name.casefold()) if existing_name else None
        info_text = "New player"
        if existing_profile is not None:
            info_text = (
                f"Record: {existing_profile['wins']}-{existing_profile['losses']}"
                f"  Net: {get_player_net_score(existing_profile)}"
            )
        info_image = small_font.render(info_text, True, (70, 88, 116))
        screen.blit(info_image, (field_rect.x, field_rect.bottom + 8))

    button_rect = pygame.Rect(WIDTH // 2 - 150, panel_rect.bottom - 110, 300, 64)
    draw_rect_compat(screen, (24, 96, 54), button_rect, border_radius=12)
    draw_rect_compat(screen, (18, 64, 38), button_rect, width=3, border_radius=12)
    draw_text_centered(screen, "Start Match", subtitle_font, (244, 248, 244), button_rect.centerx, button_rect.y + 12)

    if error_message:
        draw_text_centered(screen, error_message, small_font, (180, 46, 46), WIDTH // 2, button_rect.y - 42)

    pygame.display.flip()
    return field_rects, button_rect


async def prompt_for_player_names(player_stats):
    input_names = ["", ""]
    active_index = 0
    error_message = ""

    while True:
        field_rects, button_rect = draw_name_entry_screen(input_names, active_index, error_message, player_stats)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if field_rects[0].collidepoint(event.pos):
                    active_index = 0
                elif field_rects[1].collidepoint(event.pos):
                    active_index = 1
                elif button_rect.collidepoint(event.pos):
                    validated_names, error_message = validate_player_names(input_names)
                    if validated_names is not None:
                        return validated_names

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    active_index = (active_index + 1) % 2
                    continue

                if event.key == pygame.K_RETURN:
                    validated_names, error_message = validate_player_names(input_names)
                    if validated_names is not None:
                        return validated_names
                    continue

                if event.key == pygame.K_BACKSPACE:
                    input_names[active_index] = input_names[active_index][:-1]
                    error_message = ""
                    continue

                if event.unicode and event.unicode.isprintable() and len(input_names[active_index]) < 20:
                    input_names[active_index] += event.unicode
                    error_message = ""

        await wait_for_next_frame()


async def show_top_scores_screen(player_stats, winner_name):
    continue_button = pygame.Rect(WIDTH // 2 - 120, HEIGHT - 110, 240, 54)
    leaderboard = get_sorted_top_scores(player_stats)
    row_height = 38
    top_margin = 214
    bottom_limit = continue_button.y - 26
    rows_per_page = max(1, (bottom_limit - top_margin) // row_height)
    scroll_offset = 0

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return True
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_DOWN, pygame.K_PAGEDOWN):
                scroll_offset = min(max(0, len(leaderboard) - rows_per_page), scroll_offset + 1)
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_PAGEUP):
                scroll_offset = max(0, scroll_offset - 1)
            if event.type == pygame.MOUSEWHEEL:
                scroll_offset = max(0, min(max(0, len(leaderboard) - rows_per_page), scroll_offset - event.y))
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and continue_button.collidepoint(event.pos):
                return True

        screen.fill((34, 54, 94))
        panel_rect = pygame.Rect(190, 56, WIDTH - 380, HEIGHT - 112)
        draw_rect_compat(screen, (240, 242, 247), panel_rect, border_radius=18)
        draw_rect_compat(screen, (18, 30, 54), panel_rect, width=4, border_radius=18)

        draw_text_centered(screen, f"{winner_name} wins the match", title_font, (22, 34, 50), WIDTH // 2, 96)
        draw_text_centered(screen, "Top Scores", subtitle_font, (50, 68, 94), WIDTH // 2, 150)

        header_y = 196
        draw_rect_compat(screen, (210, 218, 231), pygame.Rect(panel_rect.x + 52, header_y, panel_rect.width - 104, 32), border_radius=8)
        screen.blit(small_font.render("Rank", True, (26, 36, 52)), (panel_rect.x + 68, header_y + 6))
        screen.blit(small_font.render("Pilot", True, (26, 36, 52)), (panel_rect.x + 146, header_y + 6))
        screen.blit(small_font.render("W", True, (26, 36, 52)), (panel_rect.right - 252, header_y + 6))
        screen.blit(small_font.render("L", True, (26, 36, 52)), (panel_rect.right - 182, header_y + 6))
        screen.blit(small_font.render("Net", True, (26, 36, 52)), (panel_rect.right - 112, header_y + 6))

        if leaderboard:
            visible_entries = leaderboard[scroll_offset:scroll_offset + rows_per_page]
            for local_index, entry in enumerate(visible_entries, start=1):
                index = scroll_offset + local_index
                row_y = top_margin + (local_index - 1) * row_height
                row_rect = pygame.Rect(panel_rect.x + 70, row_y, panel_rect.width - 140, 34)
                draw_rect_compat(screen, (222, 228, 238), row_rect, border_radius=8)
                rank_text = font.render(f"{index}.", True, (26, 36, 52))
                name_text = font.render(entry["name"], True, (26, 36, 52))
                wins_text = font.render(str(entry["wins"]), True, (26, 36, 52))
                losses_text = font.render(str(entry["losses"]), True, (26, 36, 52))
                net_text = font.render(str(get_player_net_score(entry)), True, (26, 36, 52))
                screen.blit(rank_text, (row_rect.x + 16, row_rect.y + 7))
                screen.blit(name_text, (row_rect.x + 64, row_rect.y + 7))
                screen.blit(wins_text, (panel_rect.right - 246, row_rect.y + 7))
                screen.blit(losses_text, (panel_rect.right - 176, row_rect.y + 7))
                screen.blit(net_text, (panel_rect.right - 112, row_rect.y + 7))

            if len(leaderboard) > rows_per_page:
                scroll_text = small_font.render(
                    f"Showing {scroll_offset + 1}-{min(len(leaderboard), scroll_offset + rows_per_page)} of {len(leaderboard)}  |  Up/Down to scroll",
                    True,
                    (70, 88, 116),
                )
                scroll_rect = scroll_text.get_rect(midtop=(WIDTH // 2, continue_button.y - 56))
                screen.blit(scroll_text, scroll_rect)
        else:
            draw_text_centered(screen, "No saved scores yet.", font, (52, 64, 82), WIDTH // 2, top_margin)

        draw_rect_compat(screen, (24, 96, 54), continue_button, border_radius=12)
        draw_rect_compat(screen, (18, 64, 38), continue_button, width=3, border_radius=12)
        draw_text_centered(screen, "Continue", subtitle_font, (244, 248, 244), continue_button.centerx, continue_button.y + 9)

        pygame.display.flip()
        await wait_for_next_frame()


def build_biplane_sprite(body_color, wing_color):
    sprite = pygame.Surface((52, 28), pygame.SRCALPHA)

    pygame.draw.ellipse(sprite, body_color, (10, 10, 24, 8))
    pygame.draw.polygon(sprite, body_color, [(31, 10), (46, 14), (31, 18)])
    pygame.draw.polygon(sprite, body_color, [(8, 14), (2, 10), (2, 18)])
    draw_rect_compat(sprite, wing_color, pygame.Rect(13, 5, 21, 4), border_radius=2)
    draw_rect_compat(sprite, wing_color, pygame.Rect(13, 19, 21, 4), border_radius=2)
    draw_rect_compat(sprite, (70, 60, 45), pygame.Rect(18, 9, 2, 10), border_radius=1)
    draw_rect_compat(sprite, (70, 60, 45), pygame.Rect(27, 9, 2, 10), border_radius=1)
    pygame.draw.polygon(sprite, (160, 120, 60), [(4, 11), (1, 14), (4, 17)])
    pygame.draw.circle(sprite, (230, 230, 240), (20, 14), 3)
    pygame.draw.circle(sprite, (40, 40, 40), (20, 14), 1)
    return sprite


def build_cloud_sprite(scale, edge_color=(252, 252, 255, 92), puff_color=(248, 248, 252, 255), shade_color=(222, 228, 236, 120)):
    width = int(90 * scale)
    height = int(42 * scale)
    sprite = pygame.Surface((width, height), pygame.SRCALPHA)

    border = max(3, int(height * 0.09))
    puffs = [
        (int(width * 0.16), int(height * 0.63), int(height * 0.24)),
        (int(width * 0.31), int(height * 0.44), int(height * 0.27)),
        (int(width * 0.48), int(height * 0.30), int(height * 0.32)),
        (int(width * 0.66), int(height * 0.42), int(height * 0.28)),
        (int(width * 0.83), int(height * 0.60), int(height * 0.22)),
    ]
    outer_body = pygame.Rect(int(width * 0.13), int(height * 0.48), int(width * 0.72), int(height * 0.26))
    inner_body = pygame.Rect(int(width * 0.18), int(height * 0.53), int(width * 0.62), int(height * 0.18))

    for x, y, radius in puffs:
        pygame.draw.circle(sprite, edge_color, (x, y), radius + border)
    pygame.draw.ellipse(sprite, edge_color, outer_body)

    for x, y, radius in puffs:
        pygame.draw.circle(sprite, puff_color, (x, y), radius)
    pygame.draw.ellipse(sprite, puff_color, inner_body)

    pygame.draw.ellipse(
        sprite,
        shade_color,
        pygame.Rect(int(width * 0.24), int(height * 0.66), int(width * 0.46), int(height * 0.10)),
    )
    return sprite


def create_cloud(x=None, force_visible=False):
    scale = random.uniform(CLOUD_MIN_SCALE, CLOUD_MAX_SCALE)
    sprite = build_cloud_sprite(scale)
    y_limit = HEIGHT // 2 - sprite.get_height()
    if x is None:
        if force_visible:
            min_x = -sprite.get_width() * 0.2
            max_x = WIDTH - sprite.get_width() * 0.8
            x = random.uniform(min_x, max(min_x + 1, max_x))
        else:
            x = random.uniform(-WIDTH * 0.1, WIDTH)
    return {
        "x": x,
        "y": random.uniform(20, max(21, y_limit)),
        "speed": random.uniform(CLOUD_MIN_SPEED, CLOUD_MAX_SPEED),
        "sprite": sprite,
        "active": True,
    }


def update_clouds(clouds, dt, recycle=True):
    right_edge = WIDTH + 80
    for cloud in clouds:
        if not cloud.get("active", True):
            continue

        cloud["x"] += cloud["speed"] * dt
        if cloud["x"] > right_edge:
            if recycle:
                reset_cloud = create_cloud(-cloud["sprite"].get_width() - random.uniform(40, 220))
                cloud.update(reset_cloud)
            else:
                cloud["active"] = False


def draw_clouds(surface, clouds):
    for cloud in clouds:
        if not cloud.get("active", True):
            continue
        surface.blit(cloud["sprite"], (int(cloud["x"]), int(cloud["y"])))


def create_storm_cloud(force_visible=False):
    sprite = build_cloud_sprite(
        random.uniform(2.0, 3.2),
        edge_color=(110, 116, 134, 90),
        puff_color=(84, 90, 110, 255),
        shade_color=(46, 52, 66, 160),
    )
    y_limit = HEIGHT // 2 - sprite.get_height()
    if force_visible:
        min_x = -sprite.get_width() * 0.1
        max_x = WIDTH - sprite.get_width() * 0.9
        x = random.uniform(min_x, max(min_x + 1, max_x))
    else:
        x = -sprite.get_width() - random.uniform(60, 200)

    return {
        "x": x,
        "y": random.uniform(25, max(26, y_limit)),
        "speed": random.uniform(CLOUD_MIN_SPEED * 0.7, CLOUD_MAX_SPEED * 0.85),
        "sprite": sprite,
        "lightning_timer": random.uniform(LIGHTNING_MIN_INTERVAL, LIGHTNING_MAX_INTERVAL),
        "lightning_duration": 0.0,
        "lightning_points": [],
    }


def build_lightning_points(storm_cloud):
    sprite = storm_cloud["sprite"]
    start_x = storm_cloud["x"] + sprite.get_width() * random.uniform(0.35, 0.65)
    start_y = storm_cloud["y"] + sprite.get_height()
    segment_count = 5
    segment_length = sprite.get_height() / segment_count
    points = [(start_x, start_y)]
    current_x = start_x
    current_y = start_y

    for _ in range(segment_count):
        current_x += random.uniform(-10, 10)
        current_y += segment_length
        points.append((current_x, current_y))

    return points


def update_storm_cloud(storm_cloud, dt):
    storm_cloud["x"] += storm_cloud["speed"] * dt
    if storm_cloud["x"] > WIDTH + 120:
        reset_cloud = create_storm_cloud(force_visible=False)
        storm_cloud.update(reset_cloud)
        return

    if storm_cloud["lightning_duration"] > 0.0:
        storm_cloud["lightning_duration"] = max(0.0, storm_cloud["lightning_duration"] - dt)
        if storm_cloud["lightning_duration"] == 0.0:
            storm_cloud["lightning_points"] = []
    else:
        storm_cloud["lightning_timer"] -= dt
        if storm_cloud["lightning_timer"] <= 0.0:
            storm_cloud["lightning_points"] = build_lightning_points(storm_cloud)
            storm_cloud["lightning_duration"] = LIGHTNING_FLASH_DURATION
            storm_cloud["lightning_timer"] = random.uniform(LIGHTNING_MIN_INTERVAL, LIGHTNING_MAX_INTERVAL)


def draw_storm_cloud(surface, storm_cloud, fade_progress=1.0):
    fade_progress = max(0.0, min(1.0, fade_progress))
    if fade_progress <= 0.0:
        return

    sprite = storm_cloud["sprite"].copy()
    sprite.set_alpha(int(255 * fade_progress))
    surface.blit(sprite, (int(storm_cloud["x"]), int(storm_cloud["y"])))

    if not storm_cloud["lightning_points"]:
        return

    if fade_progress < 0.35:
        return

    glow_points = [(int(x), int(y)) for x, y in storm_cloud["lightning_points"]]
    glow_surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    glow_alpha = int(255 * fade_progress)
    pygame.draw.lines(glow_surface, (255, 255, 210, glow_alpha), False, glow_points, 8)
    pygame.draw.lines(glow_surface, (255, 248, 170, glow_alpha), False, glow_points, 4)
    surface.blit(glow_surface, (0, 0))


def create_building():
    ground_top = HEIGHT - GROUND_HEIGHT
    rect = pygame.Rect(
        WIDTH // 2 - BUILDING_WIDTH // 2,
        ground_top - BUILDING_HEIGHT + 15,
        BUILDING_WIDTH,
        BUILDING_HEIGHT,
    )
    return {"rect": rect}


def draw_building(surface, building):
    rect = building["rect"]
    body_rect = pygame.Rect(rect.x + 8, rect.y + 22, rect.width - 16, rect.height - 22)
    roof_points = [
        (body_rect.left - 12, body_rect.top + 8),
        (rect.centerx, rect.y - 30),
        (body_rect.right + 12, body_rect.top + 8),
    ]

    chimney_rect = pygame.Rect(body_rect.right - 28, rect.y - 22, 12, 24)
    draw_rect_compat(surface, (140, 92, 76), chimney_rect, border_radius=2)
    draw_rect_compat(surface, (94, 58, 44), chimney_rect, width=2, border_radius=2)

    pygame.draw.polygon(surface, (126, 66, 56), roof_points)
    pygame.draw.polygon(surface, (92, 48, 40), roof_points, 4)
    draw_rect_compat(surface, (230, 214, 185), body_rect, border_radius=6)
    draw_rect_compat(surface, (154, 118, 84), body_rect, width=4, border_radius=6)

    attic_rect = pygame.Rect(rect.centerx - 15, body_rect.top - 2, 30, 22)
    pygame.draw.ellipse(surface, (249, 230, 151), attic_rect)
    pygame.draw.ellipse(surface, (132, 100, 58), attic_rect, 2)

    window_width = 24
    window_height = 24
    left_window = pygame.Rect(body_rect.left + 18, body_rect.top + 16, window_width, window_height)
    right_window = pygame.Rect(body_rect.right - 18 - window_width, body_rect.top + 16, window_width, window_height)

    for window_rect in (left_window, right_window):
        draw_rect_compat(surface, (244, 225, 140), window_rect, border_radius=3)
        draw_rect_compat(surface, (125, 92, 54), window_rect, width=2, border_radius=3)
        pygame.draw.line(surface, (125, 92, 54), (window_rect.centerx, window_rect.top + 3), (window_rect.centerx, window_rect.bottom - 3), 2)
        pygame.draw.line(surface, (125, 92, 54), (window_rect.left + 3, window_rect.centery), (window_rect.right - 3, window_rect.centery), 2)

    door_rect = pygame.Rect(rect.centerx - 18, body_rect.bottom - 40, 36, 40)
    draw_rect_compat(surface, (124, 82, 54), door_rect, border_radius=4)
    draw_rect_compat(surface, (88, 56, 36), door_rect, width=3, border_radius=4)
    pygame.draw.circle(surface, (214, 184, 92), (door_rect.right - 8, door_rect.centery), 3)

    step_rect = pygame.Rect(door_rect.x - 8, door_rect.bottom - 2, door_rect.width + 16, 8)
    draw_rect_compat(surface, (144, 144, 144), step_rect, border_radius=3)


def create_wind_gust():
    width = random.randint(WIND_GUST_MIN_WIDTH, WIND_GUST_MAX_WIDTH)
    height = random.randint(WIND_GUST_MIN_HEIGHT, WIND_GUST_MAX_HEIGHT)
    x = random.randint(40, max(40, WIDTH - width - 40))
    max_top = HEIGHT - GROUND_HEIGHT - height - 30
    y = random.randint(30, max(30, max_top))

    angle = random.uniform(-0.95, 0.95)
    if random.random() < 0.5:
        angle += math.pi

    strength = random.uniform(WIND_GUST_MIN_SPEED, WIND_GUST_MAX_SPEED)
    return {
        "rect": pygame.Rect(x, y, width, height),
        "vx": math.cos(angle) * strength,
        "vy": math.sin(angle) * strength,
        "strength": strength,
        "time_left": random.uniform(WIND_GUST_MIN_DURATION, WIND_GUST_MAX_DURATION),
    }


def update_wind_gust(gust, dt, spawn_timer):
    if gust is not None:
        gust["time_left"] -= dt
        if gust["time_left"] <= 0.0:
            gust = None
            spawn_timer = random.uniform(WIND_GUST_MIN_INTERVAL, WIND_GUST_MAX_INTERVAL)
    else:
        spawn_timer -= dt
        if spawn_timer <= 0.0:
            gust = create_wind_gust()
            spawn_timer = random.uniform(WIND_GUST_MIN_INTERVAL, WIND_GUST_MAX_INTERVAL)

    return gust, spawn_timer


def draw_wind_arrow(surface, start, vector, color, width=3):
    end = (start[0] + vector[0], start[1] + vector[1])
    pygame.draw.line(surface, color, start, end, width)

    length = math.hypot(vector[0], vector[1])
    if length < 1e-5:
        return

    ux = vector[0] / length
    uy = vector[1] / length
    head_length = min(16, max(10, length * 0.28))
    left = (
        end[0] - ux * head_length - uy * head_length * 0.45,
        end[1] - uy * head_length + ux * head_length * 0.45,
    )
    right = (
        end[0] - ux * head_length + uy * head_length * 0.45,
        end[1] - uy * head_length - ux * head_length * 0.45,
    )
    pygame.draw.polygon(surface, color, [end, left, right])


def get_curve_points(points, segments=24):
    if len(points) == 3:
        result = []
        for index in range(segments + 1):
            t = index / segments
            mt = 1.0 - t
            x = mt * mt * points[0][0] + 2.0 * mt * t * points[1][0] + t * t * points[2][0]
            y = mt * mt * points[0][1] + 2.0 * mt * t * points[1][1] + t * t * points[2][1]
            result.append((x, y))
        return result

    if len(points) == 4:
        result = []
        for index in range(segments + 1):
            t = index / segments
            mt = 1.0 - t
            x = (
                mt * mt * mt * points[0][0]
                + 3.0 * mt * mt * t * points[1][0]
                + 3.0 * mt * t * t * points[2][0]
                + t * t * t * points[3][0]
            )
            y = (
                mt * mt * mt * points[0][1]
                + 3.0 * mt * mt * t * points[1][1]
                + 3.0 * mt * t * t * points[2][1]
                + t * t * t * points[3][1]
            )
            result.append((x, y))
        return result

    return points


def draw_curve(surface, color, points, width=2, segments=24):
    curve_points = get_curve_points(points, segments)
    pygame.draw.lines(surface, color, False, curve_points, width)


def draw_cartoon_gust_streak(surface, center, vector, strength_ratio, tint):
    length = math.hypot(vector[0], vector[1])
    if length < 1e-5:
        return

    ux = vector[0] / length
    uy = vector[1] / length
    px = -uy
    py = ux
    swirl = 8 + 10 * strength_ratio
    tail = 16 + 18 * strength_ratio

    points = [
        (center[0] - ux * tail - px * swirl * 0.5, center[1] - uy * tail - py * swirl * 0.5),
        (center[0] - ux * tail * 0.25 + px * swirl, center[1] - uy * tail * 0.25 + py * swirl),
        (center[0] + ux * tail * 0.15 - px * swirl * 0.8, center[1] + uy * tail * 0.15 - py * swirl * 0.8),
        (center[0] + ux * tail + px * swirl * 0.35, center[1] + uy * tail + py * swirl * 0.35),
    ]

    pygame.draw.lines(surface, tint, False, points, max(3, int(4 + strength_ratio * 3)))
    curl_center = (
        int(center[0] - ux * (10 + strength_ratio * 8) + px * (3 + strength_ratio * 4)),
        int(center[1] - uy * (10 + strength_ratio * 8) + py * (3 + strength_ratio * 4)),
    )
    curl_radius = int(4 + strength_ratio * 5)
    pygame.draw.circle(surface, tint, curl_center, curl_radius, 2)


def draw_wind_leaf(surface, center, size, line_color, tilt, stem_curve=0.0):
    leaf = pygame.Surface((size * 3, size * 2), pygame.SRCALPHA)
    mid_y = size
    left_tip = (int(size * 0.25), mid_y)
    right_tip = (int(size * 2.7), mid_y)
    upper_curve = [
        left_tip,
        (int(size * 0.95), int(size * 0.05)),
        (int(size * 2.05), int(size * 0.18)),
        right_tip,
    ]
    lower_curve = [
        left_tip,
        (int(size * 0.9), int(size * 1.78)),
        (int(size * 2.0), int(size * 1.48)),
        right_tip,
    ]
    inner_vein = [
        (int(size * 0.58), int(size * 1.02)),
        (int(size * 1.15), int(size * 0.9)),
        (int(size * 1.86), int(size * 1.0)),
        (int(size * 2.3), int(size * 0.92)),
    ]
    stem = [
        (int(size * 0.1), int(size * (1.0 + stem_curve * 0.18))),
        (int(size * 0.22), int(size * (1.0 + stem_curve * 0.45))),
        (int(size * 0.28), int(size * (0.88 + stem_curve * 0.3))),
        left_tip,
    ]

    draw_curve(leaf, line_color, upper_curve, 2, segments=18)
    draw_curve(leaf, line_color, lower_curve, 2, segments=18)
    draw_curve(leaf, line_color, inner_vein, 2, segments=12)
    draw_curve(leaf, line_color, stem, 2, segments=12)

    rotated = pygame.transform.rotate(leaf, tilt)
    rect = rotated.get_rect(center=(int(center[0]), int(center[1])))
    surface.blit(rotated, rect)


def get_wind_strength_ratio(strength):
    speed_range = WIND_GUST_MAX_SPEED - WIND_GUST_MIN_SPEED
    if abs(speed_range) < 1e-6:
        return 1.0
    strength_ratio = (strength - WIND_GUST_MIN_SPEED) / speed_range
    return max(0.0, min(1.0, strength_ratio))


def draw_sketch_wind(surface, center, vector, strength_ratio):
    icon_width = int(360 + strength_ratio * 90)
    icon_height = int(210 + strength_ratio * 42)
    icon = pygame.Surface((icon_width, icon_height), pygame.SRCALPHA)

    ink = (18, 18, 20, 112)
    accent = (18, 18, 20, 68)

    main_sweep = [
        (24, 120),
        (88, 88),
        (158, 56),
        (244, 58),
        (318, 104),
        (icon_width - 54, 160),
    ]
    lower_sweep = [
        (90, 166),
        (156, 124),
        (236, 120),
        (326, 150),
        (icon_width - 86, 176),
    ]
    upper_streaks = [
        [(46, 82), (98, 60), (156, 58), (208, 72)],
        [(174, 44), (218, 24), (266, 26), (308, 48)],
        [(246, 84), (298, 72), (344, 82), (386, 108)],
    ]

    draw_curve(icon, ink, main_sweep, 3, segments=28)
    draw_curve(icon, ink, lower_sweep, 3, segments=28)
    for streak in upper_streaks:
        draw_curve(icon, accent, streak, 2, segments=16)

    pygame.draw.arc(icon, ink, pygame.Rect(icon_width - 150, 40, 132, 118), math.radians(176), math.radians(18), 3)
    pygame.draw.arc(icon, ink, pygame.Rect(icon_width - 110, 78, 74, 70), math.radians(178), math.radians(18), 3)
    pygame.draw.arc(icon, ink, pygame.Rect(icon_width - 176, 16, 86, 54), math.radians(178), math.radians(42), 2)

    center_swirl = [
        (int(icon_width * 0.34), 92),
        (int(icon_width * 0.46), 120),
        (int(icon_width * 0.54), 106),
        (int(icon_width * 0.58), 84),
    ]
    draw_curve(icon, ink, center_swirl, 3, segments=18)
    pygame.draw.arc(icon, ink, pygame.Rect(int(icon_width * 0.48), 70, 84, 62), math.radians(160), math.radians(386), 3)

    angle = math.degrees(math.atan2(vector[1], vector[0])) if math.hypot(vector[0], vector[1]) > 1e-5 else 0.0
    rotated_icon = pygame.transform.rotate(icon, -angle)
    rotated_icon.set_alpha(int(112 + strength_ratio * 48))
    icon_rect = rotated_icon.get_rect(center=(int(center[0]), int(center[1])))
    surface.blit(rotated_icon, icon_rect)


def draw_wind_gust(surface, gust):
    if gust is None:
        return

    rect = gust["rect"]
    strength_ratio = get_wind_strength_ratio(gust["strength"])

    arrow_length = max(36, min(70, gust["strength"] * 0.28))
    direction_length = math.hypot(gust["vx"], gust["vy"])
    arrow_vector = (arrow_length, 0.0)
    if direction_length > 1e-5:
        arrow_vector = (
            gust["vx"] / direction_length * arrow_length,
            gust["vy"] / direction_length * arrow_length,
        )

    draw_sketch_wind(surface, rect.center, arrow_vector, strength_ratio)


def point_to_segment_distance(px, py, ax, ay, bx, by):
    abx = bx - ax
    aby = by - ay
    ab_len_sq = abx * abx + aby * aby
    if ab_len_sq == 0:
        return math.hypot(px - ax, py - ay)

    t = ((px - ax) * abx + (py - ay) * aby) / ab_len_sq
    t = max(0.0, min(1.0, t))
    closest_x = ax + t * abx
    closest_y = ay + t * aby
    return math.hypot(px - closest_x, py - closest_y)


def lightning_hits_plane(storm_cloud, plane):
    points = storm_cloud["lightning_points"]
    if len(points) < 2:
        return False

    plane_radius = PLANE_LENGTH * 0.45
    for index in range(len(points) - 1):
        ax, ay = points[index]
        bx, by = points[index + 1]
        if point_to_segment_distance(plane.x, plane.y, ax, ay, bx, by) <= plane_radius + 2:
            return True
    return False


# ---------------------------------------------------------
# Plane Class
# ---------------------------------------------------------
class Plane:
    def __init__(self, x, y, angle, sprite, bullet_color):
        self.start_x = x
        self.start_y = y
        self.start_angle = angle
        self.base_sprite = sprite
        self.bullet_color = bullet_color

        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.angle = angle
        self.thrust_level = 0.0
        self.wind_vx = 0.0
        self.wind_vy = 0.0

        self.bullets = []  # [(x, y, vx, vy, age), ...]

    def reset(self):
        self.x = self.start_x
        self.y = self.start_y
        self.vx = 0.0
        self.vy = 0.0
        self.angle = self.start_angle
        self.thrust_level = 0.0
        self.wind_vx = 0.0
        self.wind_vy = 0.0
        self.bullets = []

    def crash(self):
        self.reset()

    @property
    def speed(self):
        air_vx, air_vy = self.air_velocity
        return math.hypot(air_vx, air_vy)

    @property
    def forward_vector(self):
        return math.cos(self.angle), math.sin(self.angle)

    @property
    def velocity_direction(self):
        air_vx, air_vy = self.air_velocity
        airspeed = math.hypot(air_vx, air_vy)
        if airspeed < 1e-5:
            return 1.0, 0.0
        return air_vx / airspeed, air_vy / airspeed

    @property
    def air_velocity(self):
        return self.vx - self.wind_vx, self.vy - self.wind_vy

    @property
    def forward_speed(self):
        fx, fy = self.forward_vector
        air_vx, air_vy = self.air_velocity
        return air_vx * fx + air_vy * fy

    @property
    def angle_of_attack(self):
        fx_s, fy_s = self.forward_vector
        vx_s, vy_s = self.velocity_direction

        fx, fy = fx_s, -fy_s
        vx, vy = vx_s, -vy_s

        dot = vx * fx + vy * fy
        cross = vx * fy - vy * fx

        aoa = math.atan2(cross, dot)

        if self.vx < 0:
            aoa = -aoa

        return aoa

    # ---------------------------------------------------------
    # Bullet firing
    # ---------------------------------------------------------
    def fire(self):
        if len(self.bullets) >= MAX_ACTIVE_BULLETS:
            return

        fx, fy = self.forward_vector
        bullet_speed = BULLET_MUZZLE_SPEED
        muzzle_x = self.x + fx * (PLANE_LENGTH * 0.55)
        muzzle_y = self.y + fy * (PLANE_LENGTH * 0.55)

        self.bullets.append([
            muzzle_x,
            muzzle_y,
            self.vx + fx * bullet_speed,
            self.vy + fy * bullet_speed,
            0.0  # age
        ])

    def update_bullets(self, dt, gust=None):
        active_bullets = []
        ground_y = HEIGHT - GROUND_HEIGHT

        for bx, by, bvx, bvy, age in self.bullets:
            wind_vx, wind_vy = wind_at_position(gust, bx, by)
            bvx += wind_vx * dt
            bvy += (GRAVITY + wind_vy) * dt
            bx += bvx * dt
            by += bvy * dt
            age += dt

            if bx < 0:
                bx += WIDTH
            elif bx > WIDTH:
                bx -= WIDTH

            if by <= ground_y:
                active_bullets.append([bx, by, bvx, bvy, age])

        self.bullets = active_bullets

    # ---------------------------------------------------------
    # Physics update
    # ---------------------------------------------------------
    def update(self, dt, wind=(0.0, 0.0), gust=None):
        ax, ay = 0.0, 0.0
        crashed = False
        ground_y = HEIGHT - GROUND_HEIGHT
        was_airborne = self.y < ground_y - 1
        self.wind_vx, self.wind_vy = wind

        ay += GRAVITY

        fx, fy = self.forward_vector
        thrust_accel = self.thrust_level * MAX_THRUST_ACCEL

        altitude_factor = self.y / (HEIGHT - GROUND_HEIGHT)
        altitude_factor = max(0.1, altitude_factor)
        thrust_accel *= (altitude_factor * 1.5)

        ax += fx * thrust_accel
        ay += fy * thrust_accel

        air_vx, air_vy = self.air_velocity

        vx_m, vy_m = air_vx, -air_vy
        climb_angle = math.atan2(vy_m, vx_m)
        forward_gravity = GRAVITY * math.sin(climb_angle)

        ax += -fx * forward_gravity
        ay += -fy * forward_gravity

        if self.speed > 1e-3:
            drag_dir_x = -air_vx / self.speed
            drag_dir_y = -air_vy / self.speed
            aoa = abs(self.angle_of_attack)
            drag_mag = DRAG_COEFF * (self.speed ** 2) * (1.0 + AOA_DRAG_FACTOR * aoa)
            ax += drag_dir_x * drag_mag
            ay += drag_dir_y * drag_mag

        if self.forward_speed > STALL_SPEED:
            aoa = self.angle_of_attack
            lift_factor = 1.0 + 0.8 * aoa
            lift_factor = max(0.2, min(1.8, lift_factor))

            altitude_ratio = self.y / (HEIGHT - GROUND_HEIGHT)
            altitude_lift_factor = 1.0 - 0.6 * altitude_ratio
            altitude_lift_factor = max(0.2, altitude_lift_factor)

            ay -= GRAVITY * lift_factor * altitude_lift_factor

        self.vx += ax * dt
        self.vy += ay * dt

        next_x = self.x + self.vx * dt
        next_y = self.y + self.vy * dt

        self.x = next_x
        if self.x < 0:
            self.x += WIDTH
        elif self.x > WIDTH:
            self.x -= WIDTH

        if next_y < 0:
            self.y = 0
            self.vy = 0
        elif next_y > ground_y:
            ground_speed = abs(self.vx)
            descent_rate = max(0.0, self.vy)
            if was_airborne and (ground_speed > LANDING_MAX_SPEED or descent_rate > LANDING_MAX_DESCENT):
                self.crash()
                crashed = True
            else:
                self.y = ground_y
                self.vy = 0.0
                if self.vx > 0:
                    self.vx = max(0.0, self.vx - GROUND_FRICTION * dt)
                elif self.vx < 0:
                    self.vx = min(0.0, self.vx + GROUND_FRICTION * dt)
        else:
            self.y = next_y

        if self.y > ground_y:
            self.y = ground_y
            self.vy = 0.0

        self.update_bullets(dt, gust)
        return crashed

    # ---------------------------------------------------------
    # Drawing
    # ---------------------------------------------------------
    def draw(self, surface):
        rotated_sprite = pygame.transform.rotate(self.base_sprite, -math.degrees(self.angle))
        sprite_rect = rotated_sprite.get_rect(center=(int(self.x), int(self.y)))
        surface.blit(rotated_sprite, sprite_rect)

        for bx, by, *_ in self.bullets:
            pygame.draw.circle(surface, self.bullet_color, (int(bx), int(by)), 4)


# ---------------------------------------------------------
# HUD
# ---------------------------------------------------------
def draw_hud_left(surface, plane):
    texts = [
        f"Speed: {plane.forward_speed:6.1f}",
        f"Thrust: {plane.thrust_level*100:5.1f}%",
        f"AoA: {math.degrees(plane.angle_of_attack):6.1f}"
    ]
    for i, t in enumerate(texts):
        img = font.render(t, True, (255, 255, 255))
        surface.blit(img, (10, 10 + i * 22))


def draw_hud_right(surface, plane):
    texts = [
        f"Speed: {plane.forward_speed:6.1f}",
        f"Thrust: {plane.thrust_level*100:5.1f}%",
        f"AoA: {math.degrees(plane.angle_of_attack):6.1f}"
    ]
    for i, t in enumerate(texts):
        img = font.render(t, True, (255, 255, 255))
        surface.blit(img, (WIDTH - 220, 10 + i * 22))


# ---------------------------------------------------------
# Collision helpers
# ---------------------------------------------------------
def plane_on_ground(plane):
    return plane.y >= HEIGHT - GROUND_HEIGHT - 1


def get_hit_bullet_index(bullets, plane):
    for index, bullet in enumerate(bullets):
        bx, by, *_ = bullet
        if math.hypot(bx - plane.x, by - plane.y) < PLANE_LENGTH * 0.45:
            return index
    return None


def planes_collide(p1, p2):
    return math.hypot(p1.x - p2.x, p1.y - p2.y) < PLANE_LENGTH * 0.9


def circle_rect_collision(cx, cy, radius, rect):
    closest_x = max(rect.left, min(cx, rect.right))
    closest_y = max(rect.top, min(cy, rect.bottom))
    return math.hypot(cx - closest_x, cy - closest_y) <= radius


def plane_hits_building(plane, building):
    return circle_rect_collision(plane.x, plane.y, PLANE_LENGTH * 0.4, building["rect"])


def wind_at_position(gust, x, y):
    if gust is None:
        return 0.0, 0.0

    rect = gust["rect"]
    if not rect.collidepoint(x, y):
        return 0.0, 0.0

    center_x = rect.centerx
    center_y = rect.centery
    half_width = max(1.0, rect.width / 2)
    half_height = max(1.0, rect.height / 2)
    nx = (x - center_x) / half_width
    ny = (y - center_y) / half_height
    falloff = max(0.25, 1.0 - 0.55 * (nx * nx + ny * ny))
    return gust["vx"] * falloff, gust["vy"] * falloff


def wind_at_plane(gust, plane):
    return wind_at_position(gust, plane.x, plane.y)


# ---------------------------------------------------------
# Main
# ---------------------------------------------------------
async def main():
    player_stats = await load_player_stats()
    player_names = await prompt_for_player_names(player_stats)
    if player_names is None:
        pygame.quit()
        return

    await register_players_for_match(player_stats, player_names)
    player1_key = ensure_player_profile(player_stats, player_names[0])
    player2_key = ensure_player_profile(player_stats, player_names[1])
    if not IS_WEB:
        save_player_stats(player_stats)

    # Plane 1 (WASD) — left side
    spawn_margin = 180
    plane1_sprite = build_biplane_sprite((210, 70, 55), (245, 215, 120))
    plane2_sprite = build_biplane_sprite((60, 90, 190), (225, 235, 245))
    plane1 = Plane(spawn_margin, HEIGHT - GROUND_HEIGHT, math.radians(-30), plane1_sprite, (255, 245, 80))

    # Plane 2 (Arrow Keys) — right side
    plane2 = Plane(WIDTH - spawn_margin, HEIGHT - GROUND_HEIGHT, math.radians(-150), plane2_sprite, (255, 245, 80))

    score1 = 0
    score2 = 0
    plane1_fire_was_down = False
    plane2_fire_was_down = False
    building = create_building()
    weather_state = reset_weather_state()
    weather_stage = get_weather_stage(weather_state["round_timer"])
    previous_ticks = pygame.time.get_ticks()
    accumulator = 0.0

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        frame_time, previous_ticks = await get_frame_time(previous_ticks)
        accumulator += frame_time * SIMULATION_SPEED
        keys = pygame.key.get_pressed()

        while accumulator >= DT and running:
            dt = DT

            # Plane 1 controls (WASD + F to fire)
            if keys[pygame.K_w]:
                plane1.angle -= 2.5 * dt
            if keys[pygame.K_s]:
                plane1.angle += 2.5 * dt
            if keys[pygame.K_d]:
                plane1.thrust_level = min(1.0, plane1.thrust_level + THROTTLE_RAMP_RATE * dt)
            if keys[pygame.K_a]:
                plane1.thrust_level = max(0.0, plane1.thrust_level - THROTTLE_RAMP_RATE * dt)
            if keys[pygame.K_f] and not plane1_fire_was_down:
                plane1.fire()

            # Plane 2 controls (Arrows + Ctrl or / to fire)
            if keys[pygame.K_UP]:
                plane2.angle -= 2.5 * dt
            if keys[pygame.K_DOWN]:
                plane2.angle += 2.5 * dt
            if keys[pygame.K_RIGHT]:
                plane2.thrust_level = min(1.0, plane2.thrust_level + THROTTLE_RAMP_RATE * dt)
            if keys[pygame.K_LEFT]:
                plane2.thrust_level = max(0.0, plane2.thrust_level - THROTTLE_RAMP_RATE * dt)
            if plane2_fire_pressed(keys) and not plane2_fire_was_down:
                plane2.fire()

            plane1_fire_was_down = keys[pygame.K_f]
            plane2_fire_was_down = plane2_fire_pressed(keys)

            weather_stage = update_weather(weather_state, dt)
            active_wind_gust = get_active_wind(weather_state, weather_stage)

            plane1_wind = wind_at_plane(active_wind_gust, plane1)
            plane2_wind = wind_at_plane(active_wind_gust, plane2)

            plane1_crashed = plane1.update(dt, plane1_wind, active_wind_gust)
            plane2_crashed = plane2.update(dt, plane2_wind, active_wind_gust)
            round_point_1 = 0
            round_point_2 = 0

            if not plane1_crashed and plane_hits_building(plane1, building):
                plane1.crash()
                plane1_crashed = True

            if not plane2_crashed and plane_hits_building(plane2, building):
                plane2.crash()
                plane2_crashed = True

            if plane1_crashed:
                round_point_2 += 1
            if plane2_crashed:
                round_point_1 += 1

            if weather_stage in ("storm", "wind"):
                if any(lightning_hits_plane(storm_cloud, plane1) for storm_cloud in weather_state["storm_clouds"]):
                    if not plane1_crashed:
                        round_point_2 += 1
                    plane1.crash()
                    plane1_crashed = True

                if any(lightning_hits_plane(storm_cloud, plane2) for storm_cloud in weather_state["storm_clouds"]):
                    if not plane2_crashed:
                        round_point_1 += 1
                    plane2.crash()
                    plane2_crashed = True

            # --- Bullet hits (ignore grounded planes) ---
            hit_index = None
            if not plane_on_ground(plane2):
                hit_index = get_hit_bullet_index(plane1.bullets, plane2)
            if hit_index is not None:
                round_point_1 += 1
                del plane1.bullets[hit_index]
                plane2.reset()

            hit_index = None
            if not plane_on_ground(plane1):
                hit_index = get_hit_bullet_index(plane1.bullets, plane1)
            if hit_index is not None:
                round_point_2 += 1
                del plane1.bullets[hit_index]
                plane1.reset()

            hit_index = None
            if not plane_on_ground(plane1):
                hit_index = get_hit_bullet_index(plane2.bullets, plane1)
            if hit_index is not None:
                round_point_2 += 1
                del plane2.bullets[hit_index]
                plane1.reset()

            hit_index = None
            if not plane_on_ground(plane2):
                hit_index = get_hit_bullet_index(plane2.bullets, plane2)
            if hit_index is not None:
                round_point_1 += 1
                del plane2.bullets[hit_index]
                plane2.reset()

            # --- Plane-plane collisions (ignore grounded planes) ---
            if planes_collide(plane1, plane2):
                if not plane_on_ground(plane1) and not plane_on_ground(plane2):
                    if plane1.forward_speed < plane2.forward_speed:
                        plane1.reset()
                        round_point_2 += 1
                    else:
                        plane2.reset()
                        round_point_1 += 1

            if round_point_1 or round_point_2:
                score1 += round_point_1
                score2 += round_point_2

            if score1 >= MATCH_WIN_SCORE or score2 >= MATCH_WIN_SCORE:
                winner_key = player1_key if score1 >= MATCH_WIN_SCORE else player2_key
                loser_key = player2_key if winner_key == player1_key else player1_key
                winner_name = player_stats[winner_key]["name"]
                await record_match_result(player_stats, winner_key, loser_key)
                winner_name = player_stats[winner_key]["name"]

                if not await show_top_scores_screen(player_stats, winner_name):
                    running = False
                    continue

                score1 = 0
                score2 = 0
                plane1_fire_was_down = False
                plane2_fire_was_down = False
                weather_state = reset_round_state(plane1, plane2)
                weather_stage = get_weather_stage(weather_state["round_timer"])

            accumulator -= DT

        # --- Drawing ---
        screen.fill((80, 150, 255))

        pygame.draw.rect(screen, (40, 120, 40),
                         pygame.Rect(0, HEIGHT - GROUND_HEIGHT, WIDTH, GROUND_HEIGHT))

        draw_building(screen, building)

        plane1.draw(screen)
        plane2.draw(screen)
        draw_weather(screen, weather_state, weather_stage)

        draw_hud_left(screen, plane1)
        draw_hud_right(screen, plane2)

        left_name = font.render(player_stats[player1_key]["name"], True, (255, 255, 255))
        right_name = font.render(player_stats[player2_key]["name"], True, (255, 255, 255))

        score_text = font.render(f"{score1}   SCORE   {score2}", True, (255, 255, 255))
        score_rect = score_text.get_rect(midtop=(WIDTH // 2, 10))
        left_name_rect = left_name.get_rect(midright=(score_rect.left - 20, score_rect.top))
        right_name_rect = right_name.get_rect(midleft=(score_rect.right + 20, score_rect.top))
        screen.blit(left_name, left_name_rect)
        screen.blit(score_text, score_rect)
        screen.blit(right_name, right_name_rect)
        target_text = small_font.render(f"First to {MATCH_WIN_SCORE}", True, (255, 255, 255))
        stage_text = small_font.render(f"Weather: {weather_stage.title()}", True, (255, 255, 255))
        screen.blit(target_text, (WIDTH // 2 - target_text.get_width() // 2, 38))
        screen.blit(stage_text, (WIDTH // 2 - stage_text.get_width() // 2, 60))

        pygame.display.flip()

    pygame.quit()


async def run_game():
    try:
        await main()
    except Exception as error:
        await show_fatal_error_screen(error)


if __name__ == "__main__":
    asyncio.run(run_game())
