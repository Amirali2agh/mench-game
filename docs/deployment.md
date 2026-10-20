# Deployment guide

This is the supported production topology for the backend. It is written for a
single Linux host running the API behind a TLS-terminating reverse proxy, with a
local Redis instance. Host names and paths are examples; keep the real values in
your private infrastructure notes, never in this repository.

## Topology

```
client ── TLS ──► reverse proxy (Caddy/nginx)
                        │
                        ├── /api/*, /ws/*  ──► uvicorn app.main:app  127.0.0.1:8002
                        │
                        └── /*             ──► front/dist (static SPA)
                                                  │
                                          Redis 127.0.0.1:6379
```

The application port used by the examples is **8002**; the Docker Compose file
and the development server use 8000. Pick one and keep the proxy in sync.

## 1. Redis

* Bind Redis to `127.0.0.1` (or the compose network) and never publish it.
* Use a password or a unix socket if other local users exist.
* Game state is a TTL blob (`room:{id}:state`, two hours). A Redis restart in the
  middle of a match loses that match; see `ARCHITECTURE.md` for the TTL table.

## 2. Backend service

```bash
python -m venv /srv/mench/.venv
/srv/mench/.venv/bin/pip install -r /srv/mench/requirements.txt
```

`/etc/mench.env` (mode `0640`, owned by the service user):

```ini
DEBUG=false
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
DISCONNECT_TIMEOUT=60
MATCHMAKING_TIMEOUT=30
PORTEGHAL_API_URL=https://<porteghal-host>
PORTEGHAL_API_KEY=<secret>
# Signs the short-lived player tokens. Generate with: openssl rand -hex 32
GAME_TOKEN_SECRET=<secret>
ALLOWED_CORS_ORIGINS=https://<your-game-host>
```

`/etc/systemd/system/mench.service`:

```ini
[Unit]
Description=Mensch multiplayer backend
After=network-online.target redis-server.service
Wants=network-online.target

[Service]
Type=simple
User=mench
WorkingDirectory=/srv/mench
EnvironmentFile=/etc/mench.env
ExecStart=/srv/mench/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now mench
curl -fsS http://127.0.0.1:8002/health
```

## 2.1 Player tokens

Every socket needs a signed token; the `playerId` query parameter is only read
with `DEBUG=true`. Porteghal (or whatever backend opens the WebView) has two
options, both using the shared secret:

1. Call `POST /api/rooms` with the `X-API-Key` header. The response contains
   `player_tokens`, one token per seated player; open the WebView at
   `https://<game-host>/?roomId=<id>&token=<player token>`.
2. Before matchmaking, call `POST /api/auth/token` with
   `{"player_id": "…"}` and the same header, then open the WebView with the
   returned `token`.

Porteghal can also mint the token itself: `base64url(payload).base64url(HMAC-
SHA256(secret, payload))` where `payload` is compact JSON with `sub`, optional
`room` and `exp` (unix seconds). Tokens expire after an hour, so the host must
hand out a fresh one when it opens a match.

The game rejects a tokenless or foreign connection with
`{"type": "error", "message": "Authentication failed: …"}` and close code
`1008`; the client shows a Persian message asking the player to enter through
the host app.

## 3. Frontend

```bash
cd front
npm ci
npx vite build          # emits front/dist
```

Serve `front/dist` from the reverse proxy. With no build-time configuration the
client is same-origin: REST calls go to `/api/...` and sockets to
`ws(s)://<page-host>/ws/...`, which the proxy section below routes to the
backend. That is the recommended production setup; the client bundle does not
need to know the backend port.

The origins are resolved from `VITE_API_BASE_URL` and `VITE_WS_BASE_URL` at
build time (`front/.env.example`). Only set them when the API lives on another
origin, e.g. a CDN-hosted client:

```bash
cd front
npm ci
VITE_API_BASE_URL=https://api.example.com \
VITE_WS_BASE_URL=wss://api.example.com \
npx vite build
```

`npm run dev` ignores the proxy and connects to port 8000 of the page host, so
the local backend must listen there.

## 4. Reverse proxy (Caddy)

```
<game-host> {
    encode gzip

    handle /api/* {
        reverse_proxy 127.0.0.1:8002
    }

    handle /ws/* {
        reverse_proxy 127.0.0.1:8002
    }

    handle {
        root * /srv/mench/front/dist
        try_files {path} /index.html
        file_server
    }
}
```

WebSocket upgrades need no extra configuration in Caddy; nginx needs
`proxy_http_version 1.1` plus `Upgrade`/`Connection` headers.

## 5. Checklist before going live

- [ ] `DEBUG=false` (the `/api/dev` cheat endpoints must answer 404).
- [ ] `PORTEGHAL_API_KEY` is set in the environment; the service logs an error
      and skips payouts when it is missing.
- [ ] `GAME_TOKEN_SECRET` is set (or `PORTEGHAL_API_KEY` is reused); without
      it every socket is rejected, because no token can be verified.
- [ ] The host backend creates rooms with `X-API-Key` and opens the WebView
      with `?token=…` from `player_tokens` (or calls `POST /api/auth/token`
      before matchmaking). A URL without a token is refused with close code
      `1008`.
- [ ] `ALLOWED_CORS_ORIGINS` is empty (same-origin proxy) or lists the real
      frontend origin; `*` is refused unless `DEBUG=true`.
- [ ] The frontend was built with the intended `VITE_API_BASE_URL` and
      `VITE_WS_BASE_URL` (both empty when the proxy serves `/api` and `/ws`),
      and `VITE_ALLOWED_HOSTS` is only used for development.
- [ ] TLS is terminated by the proxy; the client uses `wss://`.
- [ ] `/health` is monitored and the Redis dependency is part of the alert.
- [ ] Logs are collected (structured logging, no player secrets).
- [ ] A Redis backup or an accepted "in-flight matches are lost" policy exists.
- [ ] The license terms in `LICENSE` are respected (paid license, attribution).

## 6. Upgrades

```bash
git fetch --tags
git checkout <tag-or-commit>
/srv/mench/.venv/bin/pip install -r requirements.txt
cd front && npm ci && npx vite build
systemctl restart mench
```

Run the test suite (`python -m pytest -q` and the three frontend gates) on the
exact commit before restarting.
