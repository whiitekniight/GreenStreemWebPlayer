# NAS + Cloudflare Tunnel Deploy

This is the preferred home-hosted setup for `player.greenstreemlabs.com`.

The NAS runs two containers:

- `greenstreem-web-player`: the Python backend and web UI
- `greenstreem-cloudflared`: the private Cloudflare Tunnel connector

No router port forwarding is needed.

## Cloudflare Setup

In Cloudflare Zero Trust:

1. Create a tunnel named `greenstreem-web-player`.
2. Add a public hostname:

```text
player.greenstreemlabs.com
```

3. Point it to this private service:

```text
http://greenstreem-web-player:8097
```

4. Copy the tunnel token.

## NAS Files

Copy the whole `GreenStreemWebPlayer` folder to the NAS, then use:

```text
deploy/docker-compose.nas.yml
```

Create a `.env` file beside that compose file:

```text
CLOUDFLARE_TUNNEL_TOKEN=paste-the-token-here
```

Start the stack from the `deploy` folder:

```bash
docker compose -f docker-compose.nas.yml up -d --build
```

Then open:

```text
https://player.greenstreemlabs.com
```

## Synology Notes

In Synology Container Manager:

1. Create a project from the `deploy` folder.
2. Use `docker-compose.nas.yml`.
3. Add the `.env` file with the Cloudflare token.
4. Start the project.

If Container Manager does not allow building from `..`, build the image once on a
PC or NAS shell:

```bash
cd /volume1/docker/GreenStreemWebPlayer
docker build -t greenstreem-web-player .
cd deploy
docker compose -f docker-compose.nas.yml up -d
```

## Local NAS Test

Before testing the public tunnel, open the NAS IP directly:

```text
http://NAS-IP:8097
```

If that works, the tunnel should work after Cloudflare DNS is active.
