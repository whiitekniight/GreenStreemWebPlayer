# GreenStreem Web Player

Standalone GreenStreem web player for `player.greenstreemlabs.com`.

This project is intentionally separate from the Android TV app in `GreenStreem`.
The browser never receives provider usernames or passwords directly. Users log in
through the backend, and the backend keeps IPTV credentials in memory for a
short-lived session while proxying streams from the provider.

## Current Build

- GreenStreem branded Xtream/M3U login
- Live TV with category drawer, search, favorites, and small preview playback
- HLS.js plus backend playlist rewriting for browser-friendly `.m3u8` playback
- TS fallback/proxy path for providers that block HLS segments
- EPG loading/matching in the backend
- Account panel with provider status, expiry, active connections, and max connections
- Movies and Series library browsing
- Movie info modal, then fullscreen movie playback with fade-out controls
- In-memory sessions with automatic expiry and cleanup
- Basic production security headers

## Run Locally

```powershell
python server.py
```

Then open:

```text
http://127.0.0.1:8097
```

Optional environment settings:

```text
GREENSTREEM_HOST=127.0.0.1
GREENSTREEM_PORT=8097
GREENSTREEM_SESSION_TTL_SECONDS=43200
GREENSTREEM_DEFAULT_SERVER_URL=
```

## NAS + Cloudflare Tunnel Deploy

Preferred first public setup:

```text
https://player.greenstreemlabs.com
```

Run the player on your NAS and publish it through Cloudflare Tunnel. This keeps
your router closed while giving users a normal HTTPS web address.

Use:

```text
deploy/docker-compose.nas.yml
deploy/nas-cloudflare-tunnel.md
```

The tunnel should point `player.greenstreemlabs.com` to:

```text
http://greenstreem-web-player:8097
```

For the safest user portal flow, put your provider/server URL in the NAS `.env`
file:

```text
GREENSTREEM_DEFAULT_SERVER_URL=http://provider-server.example
```

When this is set, the public login page hides the Server URL field. Users enter
only their playlist username and password.

## VPS Deploy

The VPS route also works if you later want it fully off your home network.

```text
https://player.greenstreemlabs.com
```

Use a reverse proxy such as Caddy in front of the Python app. The sample config
is in `deploy/Caddyfile` and points the public HTTPS domain to the local backend
on port `8097`.

Basic VPS shape:

```bash
sudo useradd --system --home /opt/greenstreem-web-player --shell /usr/sbin/nologin greenstreem
sudo mkdir -p /opt/greenstreem-web-player
sudo chown -R greenstreem:greenstreem /opt/greenstreem-web-player
```

Copy this project into `/opt/greenstreem-web-player`, then install the service:

```bash
sudo cp deploy/greenstreem-web-player.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now greenstreem-web-player
```

Point DNS for `player.greenstreemlabs.com` at the VPS, install Caddy, use
`deploy/Caddyfile`, then reload Caddy.

## Docker

```bash
docker build -t greenstreem-web-player .
docker run --rm -p 8097:8097 greenstreem-web-player
```

## Security Notes

- Do not host this as a static-only site. The backend is required so credentials
  stay server-side and stream/proxy URLs stay same-origin.
- Use HTTPS in public. Browsers and IPTV providers are much happier when the
  player, API, and media URLs all come through one secure origin.
- Sessions are memory-only. Restarting the backend signs everyone out, which is
  fine for the first hosted build.
- The default session timeout is 12 hours and can be changed with
  `GREENSTREEM_SESSION_TTL_SECONDS`.
- Keep `GREENSTREEM_DEFAULT_SERVER_URL` in the backend `.env`, not in frontend
  JavaScript.
