#!/usr/bin/env python3
"""Small local backend for the GreenStreem Web Player prototype.

This is intentionally dependency-free so it can run on this Windows machine
without Node/npm. It keeps IPTV credentials in memory only.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import re
import secrets
import sys
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
MAX_PLAYLIST_BYTES = 25 * 1024 * 1024
USER_AGENT = "GreenStreemWebPlayer/0.1"


@dataclass
class Session:
    mode: str
    created_at: float
    credentials: dict[str, str] = field(default_factory=dict)
    channels: list[dict[str, Any]] = field(default_factory=list)


SESSIONS: dict[str, Session] = {}


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    return raw.rstrip("/")


def fetch_text(url: str, *, limit: int = MAX_PLAYLIST_BYTES) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=20) as response:
        content = response.read(limit + 1)
        if len(content) > limit:
            raise ValueError("Playlist is too large for this prototype build.")
        charset = response.headers.get_content_charset() or "utf-8"
        return content.decode(charset, errors="replace")


def fetch_json(url: str) -> Any:
    text = fetch_text(url)
    return json.loads(text)


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
                "category": attr(line, "group-title") or "Uncategorized",
                "logo": attr(line, "tvg-logo"),
                "url": stream_url,
                "playUrl": f"/api/stream?session={quote(session_id)}&channel={channel_index}",
                "now": "Guide pending",
            }
        )

    return channels


def xtream_api_url(base_url: str, username: str, password: str, action: str) -> str:
    query = urlencode({"username": username, "password": password, "action": action})
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

        ext = str(item.get("container_extension") or "m3u8").lstrip(".")
        stream_url = f"{base_url}/live/{quote(username)}/{quote(password)}/{quote(stream_id)}.{ext}"
        channel_index = len(channels)
        category_id = str(item.get("category_id") or "")
        channels.append(
            {
                "name": str(item.get("name") or f"Channel {stream_id}"),
                "category": categories_by_id.get(category_id, "Uncategorized"),
                "logo": str(item.get("stream_icon") or ""),
                "url": stream_url,
                "playUrl": f"/api/stream?session={quote(session_id)}&channel={channel_index}",
                "now": "Guide pending",
            }
        )

    return channels


class GreenStreemHandler(BaseHTTPRequestHandler):
    server_version = "GreenStreemWebPlayer/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), format % args))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.write_json({"ok": True})
            return
        if parsed.path == "/api/stream":
            self.handle_stream(parsed.query)
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
                if not m3u_url:
                    raise ValueError("Enter an M3U playlist URL.")
                session = Session(mode="m3u", created_at=time.time(), credentials={"m3uUrl": m3u_url})
                SESSIONS[session_id] = session
                session.channels = parse_m3u(fetch_text(m3u_url), session_id)
            elif mode == "xtream":
                base_url = normalize_url(str(payload.get("serverUrl") or ""))
                username = str(payload.get("username") or "").strip()
                password = str(payload.get("password") or "")
                if not base_url or not username or not password:
                    raise ValueError("Enter server URL, username, and password.")
                session = Session(
                    mode="xtream",
                    created_at=time.time(),
                    credentials={"serverUrl": base_url, "username": username},
                )
                SESSIONS[session_id] = session
                session.channels = load_xtream_channels(base_url, username, password, session_id)
            else:
                raise ValueError("Choose Xtream or M3U login.")

            self.write_json({"sessionId": session_id, "channels": session.channels})
        except (HTTPError, URLError) as exc:
            self.write_json({"error": f"Provider request failed: {exc}"}, HTTPStatus.BAD_GATEWAY)
        except Exception as exc:
            self.write_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def handle_stream(self, query: str) -> None:
        params = parse_qs(query)
        session_id = params.get("session", [""])[0]
        channel_raw = params.get("channel", [""])[0]
        session = SESSIONS.get(session_id)

        if not session:
            self.send_error(HTTPStatus.NOT_FOUND, "Session expired.")
            return

        try:
            channel = session.channels[int(channel_raw)]
            stream_url = str(channel.get("url") or "")
            if not stream_url:
                raise ValueError("Channel has no stream URL.")
            self.proxy_url(stream_url)
        except Exception as exc:
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def proxy_url(self, url: str) -> None:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "application/octet-stream")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            while True:
                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)

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
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8097)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), GreenStreemHandler)
    print(f"GreenStreem Web Player running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
