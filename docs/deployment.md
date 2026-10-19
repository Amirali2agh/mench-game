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

## 3. Frontend

```bash
cd front
npm ci
npx vite build          # emits front/dist
```

Serve `front/dist` from the reverse proxy. The built client derives the backend
host from the page URL. Until an explicit backend origin is configured at build
time, it targets port 8000 of the page host, so the proxy must expose that port
or the client must be built with the production origin. The environment-based
configuration is tracked as the follow-up to the URL-hardening issue; when it
lands, `docs/deployment.md` and the proxy example below are the reference.

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
- [ ] `ALLOWED_CORS_ORIGINS` lists the real origin instead of `*`.
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
