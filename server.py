#!/usr/bin/env python3
"""Small local backend for the GreenStreem Web Player prototype.

This is intentionally dependency-free so it can run on this Windows machine
without Node/npm. It keeps IPTV credentials in memory only.
"""

from __future__ import annotations

import argparse
import http.cookiejar
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
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


ROOT = Path(__file__).resolve().parent
MAX_PLAYLIST_BYTES = 25 * 1024 * 1024
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)


@dataclass
class Session:
    mode: str
    created_at: float
    credentials: dict[str, str] = field(default_factory=dict)
    channels: list[dict[str, Any]] = field(default_factory=list)
    cookie_jar: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)
    proxy_targets: dict[str, dict[str, str]] = field(default_factory=dict)


SESSIONS: dict[str, Session] = {}
DIAGNOSTICS: dict[str, list[dict[str, Any]]] = {}


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "http://" + raw
    return raw.rstrip("/")


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
    return json.loads(text)


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
                "category": attr(line, "group-title") or "Uncategorized",
                "logo": attr(line, "tvg-logo"),
                "url": stream_url,
                "playUrl": f"/api/stream?session={quote(session_id)}&channel={channel_index}",
                "streamType": guess_stream_type(stream_url),
                "now": "EPG not connected yet",
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
                "hasStream": bool(channel.get("url")),
                "now": channel.get("now") or "EPG not connected yet",
            }
        )
    return safe_channels


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

        stream_url = f"{base_url}/live/{quote(username)}/{quote(password)}/{quote(stream_id)}.m3u8"
        channel_index = len(channels)
        category_id = str(item.get("category_id") or "")
        channels.append(
            {
                "name": str(item.get("name") or f"Channel {stream_id}"),
                "category": categories_by_id.get(category_id, "Uncategorized"),
                "logo": str(item.get("stream_icon") or ""),
                "url": stream_url,
                "playUrl": f"/api/stream?session={quote(session_id)}&channel={channel_index}",
                "streamType": guess_stream_type(stream_url),
                "now": "EPG not connected yet",
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
        if parsed.path == "/api/proxy":
            self.handle_proxy(parsed.query)
            return
        if parsed.path == "/api/diagnostics":
            self.handle_diagnostics(parsed.query)
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

            self.write_json({"sessionId": session_id, "channels": public_channels(session.channels)})
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
            self.proxy_url(stream_url, session_id=session_id, session=session)
        except Exception as exc:
            record_diagnostic(session_id, "stream-error", details=str(exc))
            self.send_error(HTTPStatus.BAD_REQUEST, str(exc))

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
        session = SESSIONS.get(session_id) if session_id else None
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
