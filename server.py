#!/usr/bin/env python3
"""Backend for the GreenStreem Web Player.

This is intentionally dependency-free so it can run on this Windows machine
without Node/npm. It keeps IPTV credentials in memory only.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import StringIO
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


ROOT = Path(__file__).resolve().parent
MAX_PLAYLIST_BYTES = 25 * 1024 * 1024
MAX_EPG_BYTES = 120 * 1024 * 1024
DEFAULT_HOST = os.environ.get("GREENSTREEM_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("PORT") or os.environ.get("GREENSTREEM_PORT", "8097"))
DEFAULT_SERVER_URL_RAW = os.environ.get(
    "GREENSTREEM_DEFAULT_SERVER_URL",
    "https://kennye71.trustissues.life",
)
SESSION_TTL_SECONDS = int(os.environ.get("GREENSTREEM_SESSION_TTL_SECONDS", str(12 * 60 * 60)))
SESSION_CLEANUP_INTERVAL_SECONDS = 5 * 60
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


@dataclass
class Session:
    mode: str
    created_at: float
    last_seen: float = field(default_factory=time.time)
    credentials: dict[str, str] = field(default_factory=dict)
    channels: list[dict[str, Any]] = field(default_factory=list)
    account: dict[str, str] = field(default_factory=dict)
    cookie_jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)
    proxy_targets: dict[str, dict[str, str]] = field(default_factory=dict)
    epg_loading: bool = False
    epg_matched: int = 0
    epg_status: str = "Guide not loaded"


SESSIONS: dict[str, Session] = {}
DIAGNOSTICS: dict[str, list[dict[str, Any]]] = {}
LAST_SESSION_CLEANUP = 0.0


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    return raw.rstrip("/")


DEFAULT_SERVER_URL = normalize_url(DEFAULT_SERVER_URL_RAW)


def fetch_text(url: str, *, limit: int = MAX_PLAYLIST_BYTES) -> str:
    request = Request(url, headers=provider_headers(url))
    with urlopen(request, timeout=20) as response:
        content = response.read(limit + 1)
        if len(content) > limit:
            raise ValueError("Playlist is too large for this prototype build.")
        charset = response.headers.get_content_charset() or "utf-8"
        return content.decode(charset, errors="replace")


def fetch_json(url: str) -> Any:
    text = fetch_text(url)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        preview = re.sub(r"\s+", " ", text[:120]).strip()
        if not preview:
            raise ValueError("Provider returned an empty response. Check the server URL, scheme, and port.") from exc
        if preview.startswith("<"):
            raise ValueError("Provider returned an HTML page instead of Xtream JSON. Check the server URL, scheme, and port.") from exc
        raise ValueError(f"Provider returned non-JSON data: {preview}") from exc


def open_provider_url(url: str, headers: dict[str, str], session: Session | None = None):
    request = Request(url, headers=headers)
    if session:
        opener = build_opener(HTTPCookieProcessor(session.cookie_jar))
        return opener.open(request, timeout=20)
    return urlopen(request, timeout=20)


def provider_headers(
    url: str,
    extra: dict[str, str] | None = None,
    referer_url: str | None = None,
) -> dict[str, str]:
    parsed = urlparse(referer_url or url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    if origin:
        headers["Origin"] = origin
        headers["Referer"] = referer_url or origin + "/"
    if extra:
        headers.update(extra)
    return headers


def attr(line: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}="([^"]*)"', line)
    return match.group(1) if match else ""


def parse_m3u(text: str, session_id: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines()]
    channels: list[dict[str, Any]] = []

    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF"):
            continue

        stream_url = ""
        for possible in lines[index + 1 : index + 5]:
            if possible and not possible.startswith("#"):
                stream_url = possible
                break

        if not stream_url:
            continue

        name = line.rsplit(",", 1)[-1].strip() or "Untitled Channel"
        channel_index = len(channels)
        channels.append(
            {
                "name": name,
                "tvgId": attr(line, "tvg-id"),
                "tvgName": attr(line, "tvg-name"),
                "category": attr(line, "group-title") or "Uncategorized",
                "logo": attr(line, "tvg-logo"),
                "url": stream_url,
                "playUrl": f"/api/stream?session={quote(session_id)}&channel={channel_index}",
                "streamType": guess_stream_type(stream_url),
                "now": "EPG not connected yet",
                "next": "",
            }
        )

    return channels


def guess_stream_type(url: str) -> str:
    lower_path = urlparse(url).path.lower()
    if lower_path.endswith(".m3u8"):
        return "hls"
    if lower_path.endswith((".mp4", ".webm", ".ogg")):
        return "file"
    return "direct"


def public_channels(channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    safe_channels: list[dict[str, Any]] = []
    for channel in channels:
        safe_channels.append(
            {
                "name": channel.get("name") or "Untitled Channel",
                "category": channel.get("category") or "Uncategorized",
                "logo": channel.get("logo") or "",
                "playUrl": channel.get("playUrl") or "",
                "streamType": channel.get("streamType") or guess_stream_type(str(channel.get("url") or "")),
                "fallbackPlayUrl": channel.get("fallbackPlayUrl") or "",
                "fallbackStreamType": channel.get("fallbackStreamType") or "",
                "hasStream": bool(channel.get("url")),
                "now": channel.get("now") or "EPG not connected yet",
                "next": channel.get("next") or "",
            }
        )
    return safe_channels


def parse_xmltv_time(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None

    match = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", raw)
    if not match:
        return None

    stamp, offset = match.groups()
    parsed = datetime.strptime(stamp, "%Y%m%d%H%M%S")
    if offset:
        sign = 1 if offset[0] == "+" else -1
        hours = int(offset[1:3])
        minutes = int(offset[3:5])
        tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
        return parsed.replace(tzinfo=tz).astimezone(timezone.utc)
    return parsed.replace(tzinfo=timezone.utc)


def normalize_epg_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def text_from_child(element: ET.Element, name: str) -> str:
    child = element.find(name)
    return (child.text or "").strip() if child is not None and child.text else ""


def program_label(program: dict[str, Any]) -> str:
    title = str(program.get("title") or "No Information")
    start = program.get("start")
    stop = program.get("stop")
    if isinstance(start, datetime) and isinstance(stop, datetime):
        return f"{start.astimezone().strftime('%I:%M %p').lstrip('0')} - {stop.astimezone().strftime('%I:%M %p').lstrip('0')}  {title}"
    return title


def apply_epg(channels: list[dict[str, Any]], xmltv_text: str) -> int:
    if not xmltv_text.strip():
        return 0

    now = datetime.now(timezone.utc)
    wanted: dict[str, list[dict[str, Any]]] = {}
    for channel in channels:
        keys = {
            normalize_epg_key(str(channel.get("tvgId") or "")),
            normalize_epg_key(str(channel.get("tvgName") or "")),
            normalize_epg_key(str(channel.get("epgChannelId") or "")),
            normalize_epg_key(str(channel.get("name") or "")),
        }
        for key in keys:
            if key:
                wanted.setdefault(key, []).append(channel)

    if not wanted:
        return 0

    matched = 0
    programmes_by_channel: dict[str, list[dict[str, Any]]] = {}
    for _event, element in ET.iterparse(StringIO(xmltv_text), events=("end",)):
        if element.tag != "programme":
            continue

        channel_key = normalize_epg_key(element.attrib.get("channel", ""))
        if channel_key not in wanted:
            element.clear()
            continue

        start = parse_xmltv_time(element.attrib.get("start", ""))
        stop = parse_xmltv_time(element.attrib.get("stop", ""))
        if not start or not stop or stop <= now:
            element.clear()
            continue

        programmes_by_channel.setdefault(channel_key, []).append(
            {
                "start": start,
                "stop": stop,
                "title": text_from_child(element, "title"),
                "desc": text_from_child(element, "desc"),
            }
        )
        element.clear()

    for key, programmes in programmes_by_channel.items():
        programmes.sort(key=lambda item: item["start"])
        current = next((item for item in programmes if item["start"] <= now < item["stop"]), None)
        upcoming = next((item for item in programmes if item["start"] > now), None)
        if not current and programmes:
            current = programmes[0]
            upcoming = programmes[1] if len(programmes) > 1 else None

        if not current:
            continue

        for channel in wanted.get(key, []):
            channel["now"] = program_label(current)
            channel["next"] = f"Next: {program_label(upcoming)}" if upcoming else ""
            matched += 1

    return matched


def xmltv_url(base_url: str, username: str, password: str) -> str:
    query = urlencode({"username": username, "password": password})
    return f"{base_url}/xmltv.php?{query}"


def account_api_url(base_url: str, username: str, password: str) -> str:
    query = urlencode({"username": username, "password": password})
    return f"{base_url}/player_api.php?{query}"


def m3u_api_url(base_url: str, username: str, password: str) -> str:
    query = urlencode({"username": username, "password": password, "type": "m3u_plus", "output": "ts"})
    return f"{base_url}/get.php?{query}"


def alternate_scheme_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    scheme = "http" if parsed.scheme == "https" else "https"
    return parsed._replace(scheme=scheme).geturl().rstrip("/")


def format_unix_expiry(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value:
        return "Unknown"
    try:
        timestamp = int(value)
        if timestamp <= 0:
            return "Never"
        return datetime.fromtimestamp(timestamp).astimezone().strftime("%b %d, %Y")
    except ValueError:
        return value


def account_from_xtream_data(data: Any) -> dict[str, str]:
    user_info = data.get("user_info") if isinstance(data, dict) else {}
    server_info = data.get("server_info") if isinstance(data, dict) else {}
    if not isinstance(user_info, dict):
        return {}

    return {
        "status": str(user_info.get("status") or "Unknown"),
        "expires": format_unix_expiry(user_info.get("exp_date")),
        "activeConnections": str(user_info.get("active_cons") or "0"),
        "maxConnections": str(user_info.get("max_connections") or "Unknown"),
        "serverTimeZone": str(server_info.get("timezone") or "") if isinstance(server_info, dict) else "",
    }


def resolve_xtream_base_url(base_url: str, username: str, password: str) -> tuple[str, dict[str, str]]:
    candidates = [base_url]
    alternate = alternate_scheme_url(base_url)
    if alternate and alternate not in candidates:
        candidates.append(alternate)

    errors: list[str] = []
    for candidate in candidates:
        try:
            data = fetch_json(account_api_url(candidate, username, password))
            return candidate, account_from_xtream_data(data)
        except (HTTPError, URLError, ValueError) as exc:
            errors.append(f"{urlparse(candidate).scheme}: {exc}")

    raise ValueError("; ".join(errors) or "Could not connect to Xtream API.")


def resolve_m3u_base_url(base_url: str, username: str, password: str, session_id: str) -> tuple[str, list[dict[str, Any]]]:
    candidates = [base_url]
    alternate = alternate_scheme_url(base_url)
    if alternate and alternate not in candidates:
        candidates.append(alternate)

    errors: list[str] = []
    for candidate in candidates:
        try:
            channels = parse_m3u(fetch_text(m3u_api_url(candidate, username, password)), session_id)
            if channels:
                return candidate, channels
            errors.append(f"{urlparse(candidate).scheme}: M3U playlist was empty")
        except (HTTPError, URLError, ValueError) as exc:
            errors.append(f"{urlparse(candidate).scheme}: {exc}")

    raise ValueError("; ".join(errors) or "Could not load M3U playlist.")


def load_xtream_account(base_url: str, username: str, password: str) -> dict[str, str]:
    try:
        data = fetch_json(account_api_url(base_url, username, password))
    except (HTTPError, URLError, ValueError):
        return {}

    return account_from_xtream_data(data)


def guide_info(session: Session) -> dict[str, Any]:
    return {
        "loading": session.epg_loading,
        "matched": session.epg_matched,
        "status": session.epg_status,
    }


def start_epg_load(session_id: str, epg_url: str) -> None:
    session = get_session(session_id)
    if not session or not epg_url:
        return

    session.epg_loading = True
    session.epg_status = "Loading guide data..."

    def worker() -> None:
        current_session = get_session(session_id)
        if not current_session:
            return
        try:
            matched = apply_epg(current_session.channels, fetch_text(epg_url, limit=MAX_EPG_BYTES))
            current_session.epg_matched = matched
            current_session.epg_status = (
                f"Guide matched {matched} channels." if matched else "Guide loaded but did not match channels."
            )
            record_diagnostic(session_id, "epg-loaded", details=current_session.epg_status)
        except Exception as exc:
            current_session.epg_status = f"Guide failed: {exc}"
            record_diagnostic(session_id, "epg-error", details=str(exc))
        finally:
            current_session.epg_loading = False

    threading.Thread(target=worker, daemon=True).start()


def safe_url_info(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    path = parsed.path or ""
    suffix = Path(path).suffix.lower()
    return {
        "host": parsed.netloc,
        "type": suffix or "stream",
    }


def record_diagnostic(session_id: str, event: str, url: str = "", **details: Any) -> None:
    if not session_id:
        return

    entry: dict[str, Any] = {
        "time": time.strftime("%H:%M:%S"),
        "event": event,
    }
    if url:
        entry.update(safe_url_info(url))
    entry.update(details)

    items = DIAGNOSTICS.setdefault(session_id, [])
    items.append(entry)
    del items[:-12]


def cleanup_sessions() -> None:
    global LAST_SESSION_CLEANUP
    now = time.time()
    if now - LAST_SESSION_CLEANUP < SESSION_CLEANUP_INTERVAL_SECONDS:
        return

    LAST_SESSION_CLEANUP = now
    expired = [session_id for session_id, session in SESSIONS.items() if now - session.last_seen > SESSION_TTL_SECONDS]
    for session_id in expired:
        SESSIONS.pop(session_id, None)
        DIAGNOSTICS.pop(session_id, None)


def get_session(session_id: str) -> Session | None:
    cleanup_sessions()
    session = SESSIONS.get(session_id)
    if not session:
        return None
    if time.time() - session.last_seen > SESSION_TTL_SECONDS:
        SESSIONS.pop(session_id, None)
        DIAGNOSTICS.pop(session_id, None)
        return None
    session.last_seen = time.time()
    return session


def has_xtream_credentials(session: Session) -> bool:
    return bool(
        session.credentials.get("serverUrl")
        and session.credentials.get("username")
        and session.credentials.get("password")
    )


def xtream_api_url(
    base_url: str,
    username: str,
    password: str,
    action: str,
    extra: dict[str, str] | None = None,
) -> str:
    params = {"username": username, "password": password, "action": action}
    if extra:
        params.update(extra)
    query = urlencode(params)
    return f"{base_url}/player_api.php?{query}"


def load_xtream_channels(base_url: str, username: str, password: str, session_id: str) -> list[dict[str, Any]]:
    categories_by_id: dict[str, str] = {}

    try:
        category_data = fetch_json(xtream_api_url(base_url, username, password, "get_live_categories"))
        if isinstance(category_data, list):
            categories_by_id = {
                str(item.get("category_id")): str(item.get("category_name") or "Uncategorized")
                for item in category_data
                if isinstance(item, dict)
            }
    except Exception:
        categories_by_id = {}

    stream_data = fetch_json(xtream_api_url(base_url, username, password, "get_live_streams"))
    if not isinstance(stream_data, list):
        raise ValueError("Xtream server returned an unexpected channel list.")

    channels: list[dict[str, Any]] = []
    for item in stream_data:
        if not isinstance(item, dict):
            continue

        stream_id = str(item.get("stream_id") or "")
        if not stream_id:
            continue

        hls_url = f"{base_url}/live/{quote(username)}/{quote(password)}/{quote(stream_id)}.m3u8"
        ts_url = f"{base_url}/live/{quote(username)}/{quote(password)}/{quote(stream_id)}.ts"
        channel_index = len(channels)
        category_id = str(item.get("category_id") or "")
        channels.append(
            {
                "name": str(item.get("name") or f"Channel {stream_id}"),
                "epgChannelId": str(item.get("epg_channel_id") or ""),
                "category": categories_by_id.get(category_id, "Uncategorized"),
                "logo": str(item.get("stream_icon") or ""),
                "url": hls_url,
                "fallbackUrl": ts_url,
                "playUrl": f"/api/stream?session={quote(session_id)}&channel={channel_index}",
                "streamType": "hls",
                "fallbackPlayUrl": f"/api/stream?session={quote(session_id)}&channel={channel_index}&format=ts",
                "fallbackStreamType": "mpegts",
                "now": "EPG not connected yet",
            }
        )

    return channels


def load_xtream_library(session: Session, media_type: str, selected_category: str = "") -> dict[str, Any]:
    base_url = session.credentials.get("serverUrl", "")
    username = session.credentials.get("username", "")
    password = session.credentials.get("password", "")
    if not base_url or not username or not password:
        return {"categories": [], "items": []}

    if media_type == "movies":
        category_action = "get_vod_categories"
        item_action = "get_vod_streams"
        id_key = "stream_id"
    elif media_type == "series":
        category_action = "get_series_categories"
        item_action = "get_series"
        id_key = "series_id"
    else:
        raise ValueError("Unknown library type.")

    categories_by_id: dict[str, str] = {}
    category_id_by_name: dict[str, str] = {}
    raw_categories = fetch_json(xtream_api_url(base_url, username, password, category_action))
    if isinstance(raw_categories, list):
        categories_by_id = {
            str(item.get("category_id")): str(item.get("category_name") or "Uncategorized")
            for item in raw_categories
            if isinstance(item, dict)
        }
        category_id_by_name = {
            str(item.get("category_name") or "Uncategorized"): str(item.get("category_id"))
            for item in raw_categories
            if isinstance(item, dict)
        }

    category_names = sorted(set(categories_by_id.values()))
    effective_category = ""
    if not selected_category and category_names:
        effective_category = category_names[0]
    elif selected_category and selected_category != "All" and selected_category in category_id_by_name:
        effective_category = selected_category

    extra = {}
    if effective_category:
        extra["category_id"] = category_id_by_name[effective_category]

    raw_items = fetch_json(xtream_api_url(base_url, username, password, item_action, extra))
    if not isinstance(raw_items, list):
        raise ValueError("Provider returned an unexpected library list.")

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue

        item_id = str(item.get(id_key) or "")
        if not item_id:
            continue

        category_id = str(item.get("category_id") or "")
        title = str(item.get("name") or item.get("title") or "Untitled")
        items.append(
            {
                "id": item_id,
                "title": title,
                "category": categories_by_id.get(category_id, "Uncategorized"),
                "poster": str(item.get("stream_icon") or item.get("cover") or ""),
                "rating": str(item.get("rating") or ""),
                "year": str(item.get("year") or item.get("releaseDate") or item.get("release_date") or ""),
                "plot": str(item.get("plot") or item.get("description") or ""),
                "container": str(item.get("container_extension") or "mp4"),
                "type": media_type,
            }
        )

    return {
        "categories": ["All"] + category_names,
        "selectedCategory": effective_category or "All",
        "items": items,
    }


def load_xtream_movie_details(session: Session, item_id: str) -> dict[str, str]:
    base_url = session.credentials.get("serverUrl", "")
    username = session.credentials.get("username", "")
    password = session.credentials.get("password", "")
    if not base_url or not username or not password or not item_id:
        return {}

    query = urlencode({"username": username, "password": password, "action": "get_vod_info", "vod_id": item_id})
    data = fetch_json(f"{base_url}/player_api.php?{query}")
    info = data.get("info") if isinstance(data, dict) else {}
    movie_data = data.get("movie_data") if isinstance(data, dict) else {}
    if not isinstance(info, dict):
        info = {}
    if not isinstance(movie_data, dict):
        movie_data = {}

    def first_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text and text.lower() not in {"n/a", "null", "none"}:
                return text
        return ""

    plot = first_text(
        info.get("plot"),
        info.get("description"),
        info.get("overview"),
        info.get("movie_description"),
        info.get("backdrop_path"),
        movie_data.get("plot"),
        movie_data.get("description"),
        movie_data.get("overview"),
    )

    return {
        "plot": plot,
        "rating": first_text(info.get("rating"), movie_data.get("rating")),
        "year": first_text(info.get("releasedate"), info.get("releaseDate"), info.get("year"), movie_data.get("year")),
        "genre": first_text(info.get("genre"), movie_data.get("genre")),
        "director": first_text(info.get("director"), movie_data.get("director")),
        "cast": first_text(info.get("cast"), movie_data.get("cast")),
        "duration": first_text(info.get("duration"), info.get("duration_secs"), movie_data.get("duration")),
        "poster": first_text(info.get("movie_image"), info.get("cover_big"), info.get("cover"), movie_data.get("stream_icon")),
        "container": first_text(movie_data.get("container_extension")),
        "debugFields": ",".join(sorted(set(info.keys()) | {f"movie_data.{key}" for key in movie_data.keys()})),
    }


def load_xtream_series_details(session: Session, item_id: str) -> dict[str, Any]:
    base_url = session.credentials.get("serverUrl", "")
    username = session.credentials.get("username", "")
    password = session.credentials.get("password", "")
    if not base_url or not username or not password or not item_id:
        return {}

    query = urlencode({"username": username, "password": password, "action": "get_series_info", "series_id": item_id})
    data = fetch_json(f"{base_url}/player_api.php?{query}")
    info = data.get("info") if isinstance(data, dict) else {}
    episodes_by_season = data.get("episodes") if isinstance(data, dict) else {}
    if not isinstance(info, dict):
        info = {}
    if not isinstance(episodes_by_season, dict):
        episodes_by_season = {}

    def first_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text and text.lower() not in {"n/a", "null", "none"}:
                return text
        return ""

    def first_int(*values: Any) -> int | None:
        for value in values:
            if value is None:
                continue
            try:
                return int(str(value).strip())
            except (TypeError, ValueError):
                continue
        return None

    def looks_like_episode(value: dict[str, Any]) -> bool:
        return bool(first_text(value.get("id"), value.get("stream_id"), value.get("episode_id"), value.get("movie_id"))) and bool(
            first_text(value.get("title"), value.get("name"), value.get("episode_title"))
            or value.get("episode_num") is not None
            or value.get("episode") is not None
            or value.get("episode_number") is not None
        )

    grouped: dict[str, list[dict[str, str]]] = {}

    def add_episode(episode: dict[str, Any], fallback_season: str | None) -> None:
        episode_info = episode.get("info") if isinstance(episode.get("info"), dict) else {}
        episode_id = first_text(episode.get("id"), episode.get("stream_id"), episode.get("episode_id"), episode.get("movie_id"))
        if not episode_id:
            return
        episode_num = first_text(
            episode.get("episode_num"),
            episode.get("episode"),
            episode.get("episode_number"),
            episode.get("num"),
            episode_info.get("episode_num"),
            episode_info.get("episode"),
            episode_info.get("episode_number"),
        )
        season_number = first_int(
            episode.get("season"),
            episode.get("season_number"),
            episode_info.get("season"),
            episode_info.get("season_number"),
            fallback_season,
        )
        season_key = str(season_number) if season_number is not None else str(fallback_season or "1")
        episodes = grouped.setdefault(season_key, [])
        episodes.append(
            {
                "id": episode_id,
                "title": first_text(
                    episode.get("title"),
                    episode.get("name"),
                    episode.get("episode_title"),
                    episode_info.get("title"),
                    episode_info.get("name"),
                    episode_info.get("episode_title"),
                    f"Episode {len(episodes) + 1}",
                ),
                "episodeNum": episode_num or str(len(episodes) + 1),
                "season": season_key,
                "container": first_text(
                    episode.get("container_extension"),
                    episode.get("containerExtension"),
                    episode.get("extension"),
                    episode_info.get("container_extension"),
                    episode_info.get("containerExtension"),
                    episode_info.get("extension"),
                    "mp4",
                ),
                "plot": first_text(
                    episode.get("plot"),
                    episode.get("description"),
                    episode_info.get("plot"),
                    episode_info.get("description"),
                ),
            }
        )

    def collect_episodes(value: Any, fallback_season: str | None = None) -> None:
        if isinstance(value, list):
            for item in value:
                collect_episodes(item, fallback_season)
            return
        if not isinstance(value, dict):
            return
        if looks_like_episode(value):
            add_episode(value, fallback_season)
            return
        for key, nested in value.items():
            next_season = str(key) if str(key).isdigit() else fallback_season
            collect_episodes(nested, next_season)

    collect_episodes(episodes_by_season)

    has_real_season = any(key.isdigit() and int(key) > 0 for key in grouped.keys())
    seasons: list[dict[str, Any]] = []
    for season_key in sorted(grouped.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value)):
        if has_real_season and str(season_key) == "0":
            continue
        episodes = grouped[season_key]
        episodes.sort(key=lambda episode: int(episode["episodeNum"]) if str(episode.get("episodeNum", "")).isdigit() else str(episode.get("title", "")))
        seasons.append({"season": str(season_key), "label": "Episodes" if str(season_key) == "0" else f"Season {season_key}", "episodes": episodes})

    return {
        "plot": first_text(info.get("plot"), info.get("description"), info.get("overview")),
        "rating": first_text(info.get("rating")),
        "year": first_text(info.get("releaseDate"), info.get("releasedate"), info.get("year")),
        "genre": first_text(info.get("genre")),
        "duration": first_text(info.get("duration")),
        "poster": first_text(info.get("cover"), info.get("cover_big"), info.get("movie_image")),
        "seasons": seasons,
        "debugFields": ",".join(sorted(set(info.keys()))),
    }


class GreenStreemHandler(BaseHTTPRequestHandler):
    server_version = "GreenStreemWebPlayer/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", self.content_security_policy())
        super().end_headers()

    def content_security_policy(self) -> str:
        return (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self'; "
            "img-src 'self' data: http: https:; "
            "media-src 'self' blob: data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "frame-ancestors 'none'"
        )

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.write_json({"ok": True})
            return
        if parsed.path == "/api/config":
            self.write_json({"defaultServerConfigured": bool(DEFAULT_SERVER_URL)})
            return
        if parsed.path == "/api/stream":
            self.handle_stream(parsed.query)
            return
        if parsed.path == "/api/audio-fix":
            self.handle_audio_fix(parsed.query)
            return
        if parsed.path == "/api/proxy":
            self.handle_proxy(parsed.query)
            return
        if parsed.path == "/api/diagnostics":
            self.handle_diagnostics(parsed.query)
            return
        if parsed.path == "/api/session":
            self.handle_session(parsed.query)
            return
        if parsed.path == "/api/library":
            self.handle_library(parsed.query)
            return
        if parsed.path == "/api/item":
            self.handle_item(parsed.query)
            return
        if parsed.path == "/api/vod":
            self.handle_vod(parsed.query)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            self.handle_login()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def handle_login(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            mode = str(payload.get("mode") or "").lower()
            session_id = secrets.token_urlsafe(18)

            if mode == "m3u":
                m3u_url = normalize_url(str(payload.get("m3uUrl") or ""))
                epg_url = normalize_url(str(payload.get("epgUrl") or ""))
                if not m3u_url:
                    raise ValueError("Enter an M3U playlist URL.")
                session = Session(mode="m3u", created_at=time.time(), credentials={"m3uUrl": m3u_url})
                SESSIONS[session_id] = session
                session.channels = parse_m3u(fetch_text(m3u_url), session_id)
                if epg_url:
                    start_epg_load(session_id, epg_url)
            elif mode == "xtream":
                base_url = normalize_url(str(payload.get("serverUrl") or "")) or DEFAULT_SERVER_URL
                username = str(payload.get("username") or "").strip()
                password = str(payload.get("password") or "")
                if not base_url or not username or not password:
                    raise ValueError("Enter username and password.")
                try:
                    base_url, account = resolve_xtream_base_url(base_url, username, password)
                    session = Session(
                        mode="xtream",
                        created_at=time.time(),
                        credentials={"serverUrl": base_url, "username": username, "password": password},
                    )
                    SESSIONS[session_id] = session
                    session.account = account
                    session.channels = load_xtream_channels(base_url, username, password, session_id)
                    start_epg_load(session_id, xmltv_url(base_url, username, password))
                except ValueError as xtream_error:
                    base_url, channels = resolve_m3u_base_url(base_url, username, password, session_id)
                    session = Session(
                        mode="m3u",
                        created_at=time.time(),
                        credentials={"serverUrl": base_url, "username": username, "password": password},
                        account={"status": "M3U playlist", "expires": "Unknown", "activeConnections": "0", "maxConnections": "Unknown"},
                    )
                    SESSIONS[session_id] = session
                    session.channels = channels
                    start_epg_load(session_id, xmltv_url(base_url, username, password))
                    record_diagnostic(session_id, "xtream-fallback", details=str(xtream_error))
            else:
                raise ValueError("Choose Xtream or M3U login.")

            self.write_json(
                {
                    "sessionId": session_id,
                    "channels": public_channels(session.channels),
                    "account": session.account,
                    "guide": guide_info(session),
                }
            )
        except (HTTPError, URLError) as exc:
            self.write_json({"error": f"Provider request failed: {exc}"}, HTTPStatus.BAD_GATEWAY)
        except Exception as exc:
            self.write_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def handle_stream(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        channel_raw = params.get("channel", [""])[0]
        stream_format = params.get("format", ["hls"])[0]
        session = get_session(session_id)

        if not session:
            self.send_error(HTTPStatus.NOT_FOUND, "Session expired.")
            return

        try:
            channel = session.channels[int(channel_raw)]
            stream_url = str(channel.get("fallbackUrl") if stream_format == "ts" else channel.get("url") or "")
            if not stream_url:
                raise ValueError("Channel has no stream URL.")
            self.proxy_url(stream_url, session_id=session_id, session=session)
        except Exception as exc:
            record_diagnostic(session_id, "stream-error", details=str(exc))
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def handle_audio_fix(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        channel_raw = params.get("channel", [""])[0]
        source_url = params.get("url", [""])[0]
        session = get_session(session_id)

        if not session:
            self.send_error(HTTPStatus.NOT_FOUND, "Session expired.")
            return

        try:
            if source_url:
                stream_url = self.resolve_audio_fix_url(source_url, session_id, session)
            else:
                channel = session.channels[int(channel_raw)]
                stream_url = str(channel.get("fallbackUrl") or channel.get("url") or "")
            if not stream_url:
                raise ValueError("Channel has no stream URL.")
            self.transcode_audio_url(stream_url, session_id=session_id, session=session)
        except Exception as exc:
            record_diagnostic(session_id, "audio-fix-error", details=str(exc))
            self.send_error(HTTPStatus.BAD_GATEWAY, str(exc))

    def resolve_audio_fix_url(self, source_url: str, session_id: str, session: Session) -> str:
        parsed = urlparse(source_url)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return source_url

        params = parse_qs(parsed.query)
        if parsed.path == "/api/stream":
            channel_raw = params.get("channel", [""])[0]
            prefer_ts = params.get("format", [""])[0] == "ts"
            channel = session.channels[int(channel_raw)]
            return str((channel.get("fallbackUrl") if prefer_ts else None) or channel.get("url") or channel.get("fallbackUrl") or "")

        if parsed.path == "/api/vod":
            media_type = params.get("media", ["movies"])[0]
            item_id = params.get("id", [""])[0]
            extension = params.get("ext", ["mp4"])[0] or "mp4"
            base_url = session.credentials.get("serverUrl", "")
            username = session.credentials.get("username", "")
            password = session.credentials.get("password", "")
            if not base_url or not username or not password or not item_id:
                raise ValueError("Missing VOD details.")
            safe_ext = re.sub(r"[^A-Za-z0-9]", "", extension) or "mp4"
            stream_path = "series" if media_type == "series" else "movie"
            return f"{base_url}/{stream_path}/{quote(username)}/{quote(password)}/{quote(item_id)}.{safe_ext}"

        raise ValueError("Audio Fix cannot resolve this stream.")

    def transcode_audio_url(self, url: str, *, session_id: str, session: Session | None) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.send_error(HTTPStatus.NOT_IMPLEMENTED, "Audio Fix requires ffmpeg on the server.")
            return

        header_blob = "".join(f"{key}: {value}\r\n" for key, value in provider_headers(url).items())
        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-headers",
            header_blob,
            "-i",
            url,
            "-map",
            "0:v:0?",
            "-map",
            "0:a:0?",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-f",
            "mp4",
            "-movflags",
            "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1",
        ]

        record_diagnostic(session_id, "audio-fix", url)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        assert process.stdout is not None
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                chunk = process.stdout.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            if process.poll() is None:
                process.terminate()

    def proxy_url(
        self,
        url: str,
        *,
        session_id: str = "",
        session: Session | None = None,
        referer_url: str | None = None,
    ) -> None:
        extra_headers: dict[str, str] = {}
        range_header = self.headers.get("Range")
        if range_header:
            extra_headers["Range"] = range_header

        headers = provider_headers(url, extra_headers, referer_url=referer_url)
        record_diagnostic(session_id, "request", url)
        try:
            response = open_provider_url(url, headers, session)
        except HTTPError as exc:
            record_diagnostic(session_id, "http-error", url, status=exc.code, reason=exc.reason)
            raise
        except URLError as exc:
            record_diagnostic(session_id, "url-error", url, reason=str(exc.reason))
            raise

        with response:
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            status = getattr(response, "status", HTTPStatus.OK)
            record_diagnostic(session_id, "response", url, status=status, contentType=content_type)
            if self.is_hls_playlist(url, content_type):
                raw = response.read(MAX_PLAYLIST_BYTES + 1)
                if len(raw) > MAX_PLAYLIST_BYTES:
                    raise ValueError("HLS playlist is too large for this prototype build.")
                charset = response.headers.get_content_charset() or "utf-8"
                playlist = raw.decode(charset, errors="replace")
                rewritten = self.rewrite_hls_playlist(playlist, url, session_id, session)
                body = rewritten.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)
                return

            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            for header in ("Content-Length", "Content-Range", "Accept-Ranges"):
                value = response.headers.get(header)
                if value:
                    self.send_header(header, value)
            self.end_headers()
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def handle_proxy(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        session = get_session(session_id) if session_id else None
        token = params.get("token", [""])[0]
        target_info = session.proxy_targets.get(token) if session and token else None
        target = str(target_info.get("url") or "") if target_info else unquote(params.get("url", [""])[0])
        referer_url = str(target_info.get("referer") or "") if target_info else None
        if not target.startswith(("http://", "https://")):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid proxy URL.")
            return
        try:
            self.proxy_url(target, session_id=session_id, session=session, referer_url=referer_url)
        except Exception as exc:
            record_diagnostic(session_id, "proxy-error", target, details=str(exc))
            self.send_error(HTTPStatus.BAD_GATEWAY, str(exc))

    def handle_diagnostics(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        self.write_json({"events": DIAGNOSTICS.get(session_id, [])})

    def handle_session(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        session = get_session(session_id)
        if not session:
            self.write_json({"error": "Session expired."}, HTTPStatus.NOT_FOUND)
            return

        self.write_json(
            {
                "channels": public_channels(session.channels),
                "account": session.account,
                "guide": guide_info(session),
            }
        )

    def handle_library(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        media_type = params.get("type", [""])[0]
        selected_category = params.get("category", [""])[0]
        session = get_session(session_id)
        if not session:
            self.write_json({"error": "Session expired."}, HTTPStatus.NOT_FOUND)
            return
        print(
            f"Library request type={media_type} mode={session.mode} "
            f"has_xtream_credentials={has_xtream_credentials(session)}",
            flush=True,
        )
        if not has_xtream_credentials(session):
            self.write_json({"error": "Movies and Series require Xtream login in this build."}, HTTPStatus.BAD_REQUEST)
            return

        try:
            self.write_json(load_xtream_library(session, media_type, selected_category))
        except Exception as exc:
            self.write_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)

    def handle_item(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        media_type = params.get("type", [""])[0]
        item_id = params.get("id", [""])[0]
        session = get_session(session_id)
        if not session:
            self.write_json({"error": "Session expired."}, HTTPStatus.NOT_FOUND)
            return
        if not has_xtream_credentials(session):
            self.write_json({"error": "Detailed metadata requires Xtream login."}, HTTPStatus.BAD_REQUEST)
            return
        try:
            if media_type == "movies":
                details = load_xtream_movie_details(session, item_id)
            elif media_type == "series":
                details = load_xtream_series_details(session, item_id)
            else:
                details = {}
            self.write_json({"details": details})
        except Exception as exc:
            self.write_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)

    def handle_vod(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        media_type = params.get("media", ["movies"])[0]
        item_id = params.get("id", [""])[0]
        extension = params.get("ext", ["mp4"])[0] or "mp4"
        session = get_session(session_id)
        if not session:
            self.send_error(HTTPStatus.NOT_FOUND, "Session expired.")
            return
        if not has_xtream_credentials(session):
            self.send_error(HTTPStatus.BAD_REQUEST, "VOD requires Xtream login.")
            return

        base_url = session.credentials.get("serverUrl", "")
        username = session.credentials.get("username", "")
        password = session.credentials.get("password", "")
        if not base_url or not username or not password or not item_id:
            self.send_error(HTTPStatus.BAD_REQUEST, "Missing VOD details.")
            return

        safe_ext = re.sub(r"[^A-Za-z0-9]", "", extension) or "mp4"
        stream_path = "series" if media_type == "series" else "movie"
        stream_url = f"{base_url}/{stream_path}/{quote(username)}/{quote(password)}/{quote(item_id)}.{safe_ext}"
        try:
            self.proxy_url(stream_url, session_id=session_id, session=session)
        except Exception as exc:
            record_diagnostic(session_id, "vod-error", stream_url, details=str(exc))
            self.send_error(HTTPStatus.BAD_GATEWAY, str(exc))

    def is_hls_playlist(self, url: str, content_type: str) -> bool:
        lower_type = content_type.lower()
        lower_path = urlparse(url).path.lower()
        return (
            "mpegurl" in lower_type
            or "application/vnd.apple.mpegurl" in lower_type
            or lower_path.endswith(".m3u8")
        )

    def rewrite_hls_playlist(
        self,
        playlist: str,
        base_url: str,
        session_id: str,
        session: Session | None,
    ) -> str:
        output: list[str] = []
        for line in playlist.splitlines():
            stripped = line.strip()
            if not stripped:
                output.append(line)
                continue

            if stripped.startswith("#"):
                output.append(self.rewrite_hls_tag(line, base_url, session_id, session))
                continue

            output.append(self.proxy_link(urljoin(base_url, stripped), session_id, session, base_url))

        return "\n".join(output) + "\n"

    def rewrite_hls_tag(
        self,
        line: str,
        base_url: str,
        session_id: str,
        session: Session | None,
    ) -> str:
        def replace_uri(match: re.Match[str]) -> str:
            absolute = urljoin(base_url, match.group(1))
            return f'URI="{self.proxy_link(absolute, session_id, session, base_url)}"'

        return re.sub(r'URI="([^"]+)"', replace_uri, line)

    def proxy_link(
        self,
        url: str,
        session_id: str,
        session: Session | None,
        referer_url: str,
    ) -> str:
        if session and session_id:
            token = secrets.token_urlsafe(10)
            session.proxy_targets[token] = {"url": url, "referer": referer_url}
            return f"/api/proxy?session={quote(session_id)}&token={quote(token)}"

        return f"/api/proxy?url={quote(url, safe='')}"

    def serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        target = (ROOT / relative).resolve()
        if ROOT not in target.parents and target != ROOT:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if not target.is_file():
            target = ROOT / "index.html"

        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        if target.name == "index.html":
            self.send_header("Cache-Control", "no-store")
        else:
            self.send_header("Cache-Control", "public, max-age=300")
        self.end_headers()
        self.wfile.write(target.read_bytes())

    def write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GreenStreem Web Player backend.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), GreenStreemHandler)
    print(f"GreenStreem Web Player running at http://{args.host}:{args.port}")
    print(f"Session TTL: {SESSION_TTL_SECONDS // 60} minutes")
    server.serve_forever()


if __name__ == "__main__":
    main()
