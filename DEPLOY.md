# Deploy — castelodecampo.com (static landing page)

Static HTML served by a tiny Caddy container, routed by the host Traefik.
Same pattern as mm3-rpg: Traefik (host network) discovers the container via the
Docker socket and reaches it on its own bridge network. mm3-rpg is NOT touched.

## Facts (confirmed on this VPS)

- Traefik: container `traefik-traefik-1`, `network_mode: host`, owns 80/443.
- mm3 app: `mm3-rpg-web-1` on its own `mm3_internal` bridge.
- This stack mirrors that: `castelo` container on its own `castelo_internal` bridge.
- No shared network with mm3, no `.env` needed.

## Files

- `docker-compose.yml` — Caddy static container + Traefik routing labels
- `site/index.html` — the landing page

## Host path

The Hermes container's `/opt/data` maps to the host at `/docker/hermes-agent-65kn/data`.
So on the HOST these files live at:

```
/docker/hermes-agent-65kn/data/castelo-de-campo
```

## 1. DNS (Hostinger) — DONE

| Type | Name | Value          |
|------|------|----------------|
| A    | @    | 72.62.161.23   |
| A    | www  | 72.62.161.23   |

Confirm it resolves before deploying (cert issuance needs it):

```sh
getent hosts castelodecampo.com
getent hosts www.castelodecampo.com
```

## 2. Deploy (on the HOST)

```sh
cd /docker/hermes-agent-65kn/data/castelo-de-campo
docker compose config        # sanity check
docker compose up -d
docker compose logs -f castelo
```

## 3. Verify

```sh
docker ps | grep castelo
curl -I http://castelodecampo.com          # 301/308 -> https
curl -I https://castelodecampo.com         # 200, valid cert
curl -I https://www.castelodecampo.com     # 200
```

First HTTPS hit may take a few seconds while Traefik fetches the Let's Encrypt cert.
If it fails: check DNS resolves, then `docker logs traefik-traefik-1 | grep -i acme`.

## Updating the page later

Replace `site/index.html` (served from the mounted volume, read per request):

```sh
docker compose restart castelo   # optional; clears any cache state
```

## Rollback / teardown

```sh
docker compose down              # removes container + castelo_internal; mm3 + Traefik untouched
```

## Notes

- Entrypoints (`web`,`websecure`) and certresolver (`letsencrypt`) copied from the
  working mm3-rpg labels, so they match the host Traefik config exactly.
- Router/service names unique (`castelo`, `castelo-www`) — no collision with mm3.
- `traefik.docker.network=castelo_internal` tells host-network Traefik which IP to use.
- Container mem capped at 64m; static file server, near-zero load.
- HTML is self-contained (inline CSS), no external assets.
