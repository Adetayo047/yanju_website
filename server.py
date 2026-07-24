#!/usr/bin/env python3
"""Yanju Foundation site server: static files + /api/chat proxy to OpenAI +
Supabase-backed forms (volunteer applications, newsletter) and admin panel.

Secrets are read from environment variables, optionally loaded from a
.env file (see .env.example) next to this script:
  OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY, ADMIN_PASSWORD,
  GMAIL_ADDRESS, GMAIL_APP_PASSWORD, NOTIFY_EMAIL
They never reach the browser.
"""
import base64
import hmac
import json
import os
import secrets
import smtplib
import time
import urllib.request
import urllib.error
import urllib.parse
from email.message import EmailMessage
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def load_dotenv(path):
    """Minimal .env loader (KEY=VALUE per line). Doesn't override vars
    already set in the real environment, so `PORT=8080 python3 server.py`
    still wins over a value in .env."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


load_dotenv(os.path.join(HERE, ".env"))

PORT = int(os.environ.get("PORT", 8742))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "") or GMAIL_ADDRESS

SESSION_COOKIE = "yj_admin"
SESSION_TTL = 8 * 3600
SESSIONS = {}  # token -> expiry epoch seconds

SYSTEM_PROMPT = """You are the Yanju Assistant, the friendly AI helper on the Yanju Foundation website.

About the foundation:
- Yanju Foundation is a Nigerian non-profit (registered with CAC) based in Lagos, empowering Nigerian youth to discover purpose through holistic education and heart-led mentorship.
- Mission: empower the next generation of Nigerian leaders through purposeful education and values-based mentorship.
- Impact so far: 2,500+ children supported, 850+ mentees reached, 45 communities served.
- Programs (see programs.html): Educational Support (tuition assistance, books, learning materials), Purpose Development (mentorship focusing on self-discovery, leadership, vocational clarity for teenagers), Community Outreach (health, nutrition and infrastructure in villages), plus STEM workshops and scholarships.
- Ways to help: donate (donate.html — from N5,000 which covers school supplies for a term), sponsor a child (sponsor.html — Basic, Essential and Full Impact tiers), volunteer or become a mentor (volunteer.html), corporate partnership.
- Contact: email yanjufoundation@gmail.com, phone +234 704 744 4628, Instagram @yanjufoundation. Location: Lagos, Nigeria.

Rules:
- Be warm, hopeful and concise (2-4 short sentences unless asked for detail).
- Point people to the right page of this website when relevant.
- If you don't know something (e.g. specific application deadlines), say so and share the email/phone above.
- Never invent bank details; direct donation questions to the Donate page or the email above.
"""


def get_api_key():
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if key:
        return key
    candidates = [
        os.path.join(HERE, "openai_key.txt"),
    ]
    for keyfile in candidates:
        try:
            if os.path.exists(keyfile):
                with open(keyfile) as f:
                    key = f.read().strip()
                if key:
                    return key
        except OSError:
            pass
    return ""


def call_openai(messages):
    key = get_api_key()
    if not key:
        return (
            "The assistant isn't connected yet: no OpenAI API key is configured. "
            "Site admin: put your key in openai_key.txt next to server.py, or set "
            "the OPENAI_API_KEY environment variable, then restart the server."
        )
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "max_tokens": 400,
        "temperature": 0.7,
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.load(resp)
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        print(f"OpenAI HTTP {e.code}: {detail}")
        if e.code in (401, 403):
            return "The assistant's API key was rejected. Site admin: please check the OpenAI key."
        if e.code == 429:
            return "I'm receiving a lot of questions right now — please try again in a moment."
        return "Sorry, I ran into a problem answering that. Please try again."
    except Exception as e:  # network errors, timeouts
        print(f"OpenAI request failed: {e}")
        return (
            "I couldn't reach the assistant service. Please try again, or email "
            "yanjufoundation@gmail.com / call +234 704 744 4628."
        )


def send_notification_email(subject, body):
    """Best-effort email notification via Gmail SMTP. Never raises — a
    submission that already succeeded (saved to Supabase) shouldn't fail
    just because the notification email couldn't be sent."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD or not NOTIFY_EMAIL:
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = NOTIFY_EMAIL
    msg.set_content(body)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            smtp.send_message(msg)
    except Exception as e:
        print(f"Notification email failed: {e}")


class SupabaseError(Exception):
    pass


def supabase_request(method, path, body=None, query=None, extra_headers=None):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise SupabaseError("Database isn't configured (SUPABASE_URL / SUPABASE_SERVICE_KEY missing).")
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    if extra_headers:
        headers.update(extra_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        print(f"Supabase HTTP {e.code}: {detail}")
        raise SupabaseError(f"Database request failed ({e.code}).")
    except Exception as e:
        print(f"Supabase request failed: {e}")
        raise SupabaseError("Couldn't reach the database. Please try again.")


def supabase_storage_upload(bucket, filename, content_bytes, content_type):
    if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
        raise SupabaseError("Storage isn't configured (SUPABASE_URL / SUPABASE_SERVICE_KEY missing).")
    safe_name = urllib.parse.quote(filename)
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{safe_name}"
    req = urllib.request.Request(
        url,
        data=content_bytes,
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        print(f"Supabase storage HTTP {e.code}: {detail}")
        raise SupabaseError(f"Photo upload failed ({e.code}).")
    except Exception as e:
        print(f"Supabase storage upload failed: {e}")
        raise SupabaseError("Photo upload failed. Please try again.")
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{safe_name}"


def supabase_storage_delete(bucket, filename):
    safe_name = urllib.parse.quote(filename)
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{safe_name}"
    req = urllib.request.Request(
        url,
        headers={
            "apikey": SUPABASE_SERVICE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        },
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            resp.read()
    except Exception as e:
        print(f"Supabase storage delete failed (ignored): {e}")


def create_session():
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = time.time() + SESSION_TTL
    return token


def get_session_token(handler):
    raw = handler.headers.get("Cookie")
    if not raw:
        return None
    jar = cookies.SimpleCookie()
    jar.load(raw)
    morsel = jar.get(SESSION_COOKIE)
    return morsel.value if morsel else None


def require_admin(handler):
    token = get_session_token(handler)
    if not token:
        return False
    expiry = SESSIONS.get(token)
    if not expiry or expiry < time.time():
        SESSIONS.pop(token, None)
        return False
    return True


def set_session_cookie(handler, token):
    is_https = handler.headers.get("X-Forwarded-Proto") == "https"
    parts = [
        f"{SESSION_COOKIE}={token}",
        "Path=/",
        f"Max-Age={SESSION_TTL}",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if is_https:
        parts.append("Secure")
    handler.send_header("Set-Cookie", "; ".join(parts))


def clear_session_cookie(handler):
    handler.send_header(
        "Set-Cookie",
        f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
    )


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def end_headers(self):
        # Dev server: never let the browser cache pages/assets under separate
        # URLs (e.g. "/" vs "/index.html") while content is actively changing.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # ---------- helpers ----------
    def _send_json(self, status, payload, extra_header_fn=None):
        out = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        if extra_header_fn:
            extra_header_fn(self)
        self.end_headers()
        self.wfile.write(out)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b""
        return json.loads(raw or b"{}")

    def _require_admin_or_401(self):
        if not require_admin(self):
            self._send_json(401, {"error": "Not authenticated"})
            return False
        return True

    # ---------- GET ----------
    def do_GET(self):
        if self.path == "/api/gallery":
            return self._handle_get_gallery()
        if self.path == "/api/admin/volunteers":
            if not self._require_admin_or_401():
                return
            return self._handle_get_volunteers()
        if self.path == "/api/admin/newsletter":
            if not self._require_admin_or_401():
                return
            return self._handle_get_newsletter()
        if self.path == "/api/admin/pledges":
            if not self._require_admin_or_401():
                return
            return self._handle_get_pledges()
        return super().do_GET()

    def _handle_get_gallery(self):
        try:
            rows = supabase_request(
                "GET", "gallery_images", query={"select": "*", "order": "sort_order.asc,created_at.desc"}
            )
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        self._send_json(200, rows or [])

    def _handle_get_volunteers(self):
        try:
            rows = supabase_request(
                "GET", "volunteer_applications", query={"select": "*", "order": "created_at.desc"}
            )
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        self._send_json(200, rows or [])

    def _handle_get_pledges(self):
        try:
            rows = supabase_request(
                "GET", "donation_pledges", query={"select": "*", "order": "created_at.desc"}
            )
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        self._send_json(200, rows or [])

    def _handle_get_newsletter(self):
        try:
            rows = supabase_request(
                "GET", "newsletter_signups", query={"select": "*", "order": "created_at.desc"}
            )
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        self._send_json(200, rows or [])

    # ---------- POST ----------
    def do_POST(self):
        routes = {
            "/api/chat": self._handle_chat,
            "/api/volunteer": self._handle_volunteer,
            "/api/newsletter": self._handle_newsletter,
            "/api/donate-pledge": self._handle_donate_pledge,
            "/api/admin/login": self._handle_admin_login,
            "/api/admin/logout": self._handle_admin_logout,
            "/api/admin/gallery": self._handle_admin_gallery_upload,
        }
        handler = routes.get(self.path)
        if not handler:
            if self.path.startswith("/api/admin/gallery/"):
                return self._send_json(404, {"error": "Use DELETE to remove a photo"})
            self.send_error(404)
            return
        handler()

    def _handle_chat(self):
        try:
            body = self._read_json_body()
            messages = [
                {"role": m["role"], "content": str(m["content"])[:2000]}
                for m in body.get("messages", [])
                if m.get("role") in ("user", "assistant")
            ][-12:]
        except (ValueError, KeyError, TypeError):
            self.send_error(400, "bad request body")
            return
        reply = call_openai(messages)
        self._send_json(200, {"reply": reply})

    def _handle_volunteer(self):
        try:
            body = self._read_json_body()
        except ValueError:
            return self._send_json(400, {"error": "Bad request body"})
        full_name = str(body.get("full_name", "")).strip()[:200]
        email = str(body.get("email", "")).strip()[:200]
        if not full_name or not email or "@" not in email:
            return self._send_json(400, {"error": "Full name and a valid email are required."})
        row = {
            "full_name": full_name,
            "email": email,
            "phone": str(body.get("phone", "")).strip()[:50] or None,
            "area_of_interest": str(body.get("area_of_interest", "")).strip()[:100] or None,
            "availability": body.get("availability") if isinstance(body.get("availability"), list) else None,
            "experience": str(body.get("experience", "")).strip()[:4000] or None,
        }
        try:
            supabase_request("POST", "volunteer_applications", body=row)
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        send_notification_email(
            f"New volunteer application — {full_name}",
            f"Name: {full_name}\nEmail: {email}\nPhone: {row['phone'] or '—'}\n"
            f"Area of interest: {row['area_of_interest'] or '—'}\n"
            f"Availability: {', '.join(row['availability'] or [])}\n\n"
            f"Experience:\n{row['experience'] or '—'}",
        )
        self._send_json(200, {"ok": True})

    def _handle_newsletter(self):
        try:
            body = self._read_json_body()
        except ValueError:
            return self._send_json(400, {"error": "Bad request body"})
        email = str(body.get("email", "")).strip()[:200]
        if not email or "@" not in email:
            return self._send_json(400, {"error": "A valid email is required."})
        try:
            supabase_request(
                "POST",
                "newsletter_signups",
                body={"email": email},
                extra_headers={"Prefer": "return=representation,resolution=ignore-duplicates"},
            )
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        send_notification_email("New newsletter signup", f"Email: {email}")
        self._send_json(200, {"ok": True})

    def _handle_donate_pledge(self):
        try:
            body = self._read_json_body()
        except ValueError:
            return self._send_json(400, {"error": "Bad request body"})
        first_name = str(body.get("first_name", "")).strip()[:100]
        email = str(body.get("email", "")).strip()[:200]
        if not first_name or not email or "@" not in email:
            return self._send_json(400, {"error": "First name and a valid email are required."})
        row = {
            "first_name": first_name,
            "last_name": str(body.get("last_name", "")).strip()[:100] or None,
            "email": email,
            "phone": str(body.get("phone", "")).strip()[:50] or None,
            "amount": int(body.get("amount", 0) or 0),
            "frequency": str(body.get("frequency", "")).strip()[:20] or None,
            "method": str(body.get("method", "")).strip()[:20] or None,
        }
        try:
            supabase_request("POST", "donation_pledges", body=row)
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        send_notification_email(
            f"New donation pledge — ₦{row['amount']:,}",
            f"Name: {first_name} {row['last_name'] or ''}\nEmail: {email}\n"
            f"Phone: {row['phone'] or '—'}\nAmount: ₦{row['amount']:,}\n"
            f"Frequency: {row['frequency'] or '—'}\nMethod: {row['method'] or '—'}",
        )
        self._send_json(200, {"ok": True})

    def _handle_admin_login(self):
        try:
            body = self._read_json_body()
        except ValueError:
            return self._send_json(400, {"error": "Bad request body"})
        if not ADMIN_PASSWORD:
            return self._send_json(503, {"error": "Admin login isn't configured (ADMIN_PASSWORD missing)."})
        password = str(body.get("password", ""))
        if not hmac.compare_digest(password, ADMIN_PASSWORD):
            return self._send_json(401, {"error": "Incorrect password"})
        token = create_session()
        self._send_json(200, {"ok": True}, extra_header_fn=lambda h: set_session_cookie(h, token))

    def _handle_admin_logout(self):
        token = get_session_token(self)
        if token:
            SESSIONS.pop(token, None)
        self._send_json(200, {"ok": True}, extra_header_fn=clear_session_cookie)

    def _handle_admin_gallery_upload(self):
        if not self._require_admin_or_401():
            return
        try:
            body = self._read_json_body()
        except ValueError:
            return self._send_json(400, {"error": "Bad request body"})
        filename = str(body.get("filename", "")).strip()
        content_b64 = body.get("content_base64", "")
        if not filename or not content_b64:
            return self._send_json(400, {"error": "filename and content_base64 are required."})
        try:
            content_bytes = base64.b64decode(content_b64)
        except Exception:
            return self._send_json(400, {"error": "content_base64 is not valid base64."})
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
        content_type = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif",
        }.get(ext, "application/octet-stream")
        unique_name = f"{secrets.token_hex(8)}.{ext}"
        try:
            url = supabase_storage_upload("gallery", unique_name, content_bytes, content_type)
            row = supabase_request("POST", "gallery_images", body={
                "url": url,
                "title": str(body.get("title", "")).strip()[:200] or None,
                "category": str(body.get("category", "")).strip()[:50] or None,
                "alt_text": str(body.get("alt_text", "")).strip()[:300] or None,
                "sort_order": int(body.get("sort_order", 0) or 0),
            })
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        self._send_json(200, {"ok": True, "image": row[0] if row else None})

    # ---------- DELETE ----------
    def do_DELETE(self):
        if self.path.startswith("/api/admin/gallery/"):
            if not self._require_admin_or_401():
                return
            image_id = self.path.rsplit("/", 1)[-1]
            return self._handle_admin_gallery_delete(image_id)
        self.send_error(404)

    def _handle_admin_gallery_delete(self, image_id):
        try:
            rows = supabase_request("GET", "gallery_images", query={"id": f"eq.{image_id}", "select": "url"})
            supabase_request("DELETE", "gallery_images", query={"id": f"eq.{image_id}"})
        except SupabaseError as e:
            return self._send_json(503, {"error": str(e)})
        if rows:
            url = rows[0].get("url", "")
            filename = url.rsplit("/", 1)[-1]
            supabase_storage_delete("gallery", filename)
        self._send_json(200, {"ok": True})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"Serving Yanju Foundation site from {HERE} on http://localhost:{PORT}")
    print("Chat API key configured:", "yes" if get_api_key() else "NO — chat will show setup instructions")
    print("Supabase configured:", "yes" if (SUPABASE_URL and SUPABASE_SERVICE_KEY) else "NO — forms/gallery/admin will error")
    print("Admin password configured:", "yes" if ADMIN_PASSWORD else "NO — admin login disabled")
    print("Email notifications:", "yes" if (GMAIL_ADDRESS and GMAIL_APP_PASSWORD) else "NO — form notifications disabled")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
