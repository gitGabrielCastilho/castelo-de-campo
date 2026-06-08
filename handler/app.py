#!/usr/bin/env python3
"""Minimal waitlist form handler for castelodecampo.com.

Stdlib only. Accepts POST /api/waitlist (form-encoded or JSON), validates,
appends to a local JSONL (data under our control — LGPD), and emails it.
Config via environment:

  MAIL_TO        destination address (required)
  MAIL_FROM      envelope/from address (default: MAIL_TO)
  SMTP_HOST      SMTP relay host (required to send mail)
  SMTP_PORT      default 587
  SMTP_USER      SMTP auth user (default: MAIL_FROM)
  SMTP_PASS      SMTP auth password / app password (required to send mail)
  SMTP_STARTTLS  "1" (default) to STARTTLS, "0" for plain
  DATA_FILE      JSONL path (default /data/submissions.jsonl)
  RATE_SECONDS   min seconds between submits per IP (default 20)
  PORT           listen port (default 80)
"""
import json
import os
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

REQUIRED = ["name", "email", "phone", "city", "language", "format", "reason", "consent"]
MAX_BODY = 64 * 1024
_last_seen: dict[str, float] = {}


def env(key, default=None):
    v = os.environ.get(key)
    return v if v not in (None, "") else default


def append_jsonl(record):
    path = env("DATA_FILE", "/data/submissions.jsonl")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except OSError as e:
        print(f"[warn] could not write {path}: {e}", flush=True)
        return False


def send_email(record):
    mail_to = env("MAIL_TO")
    smtp_host = env("SMTP_HOST")
    smtp_pass = env("SMTP_PASS")
    if not (mail_to and smtp_host and smtp_pass):
        print("[warn] mail not configured (MAIL_TO/SMTP_HOST/SMTP_PASS); skipping send", flush=True)
        return False
    mail_from = env("MAIL_FROM", mail_to)
    smtp_user = env("SMTP_USER", mail_from)
    smtp_port = int(env("SMTP_PORT", "587"))

    msg = EmailMessage()
    msg["Subject"] = f"Lista de espera — {record.get('name', '?')}"
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg["Reply-To"] = record.get("email", mail_from)
    body = "\n".join(f"{k}: {record.get(k, '')}" for k in REQUIRED + ["received_at", "ip"])
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as s:
            if env("SMTP_STARTTLS", "1") == "1":
                s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True
    except Exception as e:  # noqa: BLE001 - log and report failure to caller
        print(f"[error] smtp send failed: {e}", flush=True)
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "castelo-waitlist/1.0"

    def _json(self, code, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/api/health", "/api/waitlist"):
            return self._json(200, {"ok": True})
        return self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/api/waitlist":
            return self._json(404, {"ok": False, "error": "not found"})

        ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()
        rate = int(env("RATE_SECONDS", "20"))
        now = time.time()
        if now - _last_seen.get(ip, 0) < rate:
            return self._json(429, {"ok": False, "error": "too many requests"})

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._json(400, {"ok": False, "error": "invalid body"})
        raw = self.rfile.read(length)

        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip()
        try:
            if ctype == "application/json":
                fields = json.loads(raw.decode("utf-8"))
            else:
                parsed = parse_qs(raw.decode("utf-8"))
                fields = {k: v[0] for k, v in parsed.items()}
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"ok": False, "error": "could not parse body"})

        # honeypot: bots fill hidden "website" field
        if fields.get("website"):
            return self._json(200, {"ok": True})  # silently accept, drop

        missing = [k for k in REQUIRED if not str(fields.get(k, "")).strip()]
        if missing:
            return self._json(400, {"ok": False, "error": "missing fields", "fields": missing})
        if str(fields.get("consent")).lower() not in ("on", "true", "1", "yes"):
            return self._json(400, {"ok": False, "error": "consent required"})

        record = {k: str(fields.get(k, "")).strip() for k in REQUIRED}
        record["received_at"] = datetime.now(timezone.utc).isoformat()
        record["ip"] = ip

        _last_seen[ip] = now
        stored = append_jsonl(record)
        mailed = send_email(record)

        if not (stored or mailed):
            return self._json(502, {"ok": False, "error": "could not record submission"})
        return self._json(200, {"ok": True})

    def log_message(self, fmt, *args):  # quieter logs
        print(f"{self.address_string()} {fmt % args}", flush=True)


def main():
    port = int(env("PORT", "80"))
    srv = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"waitlist handler listening on :{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
