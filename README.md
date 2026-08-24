# Signal Signage

Self-hosted digital-signage platform for the internal VM. Signal is a Docker
Compose application; no hosted OpenAI or ChatGPT service is required.

## Services

| Service | Responsibility |
| --- | --- |
| `web` | React/Vinext management console on port 3000 |
| `api` | FastAPI API and device-facing HTTPS/WSS foundation |
| `worker` | Redis-backed media processing jobs (FFmpeg/PDF/image work) |
| `db` | PostgreSQL durable application data |
| `redis` | Queue and cache |
| `cloudflared` | Optional outbound-only Cloudflare Tunnel |

Media and backups are named Docker volumes. `postgres_data` stores PostgreSQL;
`media_data` contains originals, processed files, and thumbnails; `backup_data`
is reserved for backup exports. Include all three in the VM backup policy.

## Start locally

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD and JWT_SECRET in .env
docker compose up --build -d
docker compose ps
```

The console is available at `http://localhost:3000` and the API health check at
`http://localhost:8000/healthz` only from the Compose network by default.

To start the outbound tunnel after adding its token to `.env`:

```bash
docker compose --profile tunnel up -d
```

## First Super Admin

After the API finishes its automatic Alembic migration, create the first
administrator exactly once. Signal does not ship a default password.

```bash
docker compose exec api python -m app.bootstrap \
  --username admin \
  --display-name "Signal Administrator" \
  --password "use-a-long-unique-password"
```

Sign in at `http://localhost:3000` with those credentials. A Super Admin
bypasses scoped permissions; all other access is granted by capability at
District, Building, or Player scope and evaluated by the API.

## Migrations

The `api` service runs `alembic upgrade head` before it starts. To inspect or
run migrations manually:

```bash
docker compose exec api alembic current
docker compose exec api alembic upgrade head
```

## Tests and development

The API test suite covers authentication, protected routes, building/player
scope filtering, unauthorized writes, and permitted media upload metadata.

```bash
docker compose exec api pytest -q
```

For a local frontend-only development loop, run `pnpm run dev`. The browser
uses the API published on `http://localhost:8000`; start Compose first.

## Production notes

- Do not expose PostgreSQL or Redis ports publicly.
- Put the Cloudflare Tunnel in front of `web` and the API route; players always
  initiate their outbound connections.
- Uploaded media is written safely to `media_data`, marked **Processing**, and
  sent to the Redis/Celery worker. Images get thumbnails, PDFs render their
  first page, and videos are normalized to silent H.264 MP4 plus a thumbnail.
  Failures are retained and shown as **Failed** rather than discarded.
- Back up `postgres_data`, `media_data`, and `backup_data` on the VM.
