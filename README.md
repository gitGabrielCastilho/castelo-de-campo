# castelodecampo.com

Static landing page (waitlist) for the Castelo de Campo clinic, served on the VPS
behind the host Traefik, plus a tiny self-hosted form handler.

## Layout

```
site/index.html      static landing page (self-contained, inline CSS, PT-BR/EN)
handler/app.py       waitlist form handler (Python stdlib, no deps)
handler/Dockerfile   handler image
docker-compose.yml   caddy static + waitlist handler, Traefik labels
.env.example         handler config template (copy to .env, never commit)
DEPLOY.md            full deploy + verify steps
```

## Architecture

- `castelodecampo.com` / `www` → host Traefik (80/443) → `castelo` (Caddy, static).
- `castelodecampo.com/api/*` → host Traefik → `waitlist` (form handler).
- Handler stores submissions to a Docker volume (`/data/submissions.jsonl`) and
  emails them via SMTP relay. Submission data stays on the VPS (LGPD).

## Local config

Copy `.env.example` → `.env`, fill `MAIL_TO` + SMTP credentials. `.env` and
submission data are gitignored.

See `DEPLOY.md` for deploy and verification commands.
