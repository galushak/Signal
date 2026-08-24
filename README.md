# Signal Signage

Self-hosted digital-signage platform for the internal VM. The UI remains the
staff-facing console; Docker Compose supplies the production services behind it.

## Services

| Service | Responsibility |
| --- | --- |
| `web` | React/Vinext management console on port 3000 |
| `api` | FastAPI API and device-facing HTTPS/WSS foundation |
| `worker` | Redis-backed media processing jobs (FFmpeg/PDF/image work) |
| `db` | PostgreSQL durable application data |
| `redis` | Queue and cache |
| `cloudflared` | Optional outbound-only Cloudflare Tunnel |

Media and backups are named Docker volumes. Mount or back up those volumes from
the VM according to the institution's backup policy.

## Start locally

```bash
cp .env.example .env
# Replace POSTGRES_PASSWORD in .env
docker compose up --build -d
docker compose ps
```

The console is available at `http://localhost:3000` and the API health check at
`http://localhost:8000/healthz` only from the Compose network by default.

To start the outbound tunnel after adding its token to `.env`:

```bash
docker compose --profile tunnel up -d
```

## Production notes

- Do not expose PostgreSQL or Redis ports publicly.
- Put the Cloudflare Tunnel in front of `web` and the API route; players always
  initiate their outbound connections.
- Add database migrations, authentication, media validation/FFmpeg jobs, and
  player-manifest endpoints as the next feature slices. The worker has a
  deliberately isolated placeholder task for that pipeline.
- Back up `postgres_data`, `media_data`, and `backup_data` on the VM.
