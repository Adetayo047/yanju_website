#!/usr/bin/env python3
"""Yanju Foundation site server: static files + /api/chat proxy to OpenAI.

The OpenAI key is read from the OPENAI_API_KEY environment variable or a
file named openai_key.txt next to this script. It never reaches the browser.
"""
import json
import os
import urllib.request
import urllib.error
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = 8742

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
        "/Users/philipadetunji/Downloads/my files/godliness/yanju-foundation-site/openai_key.txt",
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


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=HERE, **kwargs)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            messages = [
                {"role": m["role"], "content": str(m["content"])[:2000]}
                for m in body.get("messages", [])
                if m.get("role") in ("user", "assistant")
            ][-12:]
        except (ValueError, KeyError, TypeError):
            self.send_error(400, "bad request body")
            return
        reply = call_openai(messages)
        out = json.dumps({"reply": reply}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    print(f"Serving Yanju Foundation site from {HERE} on http://localhost:{PORT}")
    print("Chat API key configured:", "yes" if get_api_key() else "NO — chat will show setup instructions")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
