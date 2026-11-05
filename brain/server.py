#!/usr/bin/env python3
"""
Mochi brain: a small local server that gives Mochi a personality, memory and
conversation, using Ollama on this Mac. It also serves Mochi's face, so the
phone opens one address and everything works together.

Standard library only: no pip installs needed.
Run it with ./start.sh (that also makes the HTTPS certificate the phone needs).
"""
import datetime
import json
import os
import re
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("MOCHI_PORT", "8765"))
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
if not OLLAMA.startswith("http"):
    OLLAMA = "http://" + OLLAMA
MODEL = os.environ.get("MOCHI_MODEL", "")
MEM_PATH = os.path.join(HERE, "memory.json")
FACE_PATH = os.path.join(HERE, "index.html")
LOCK = threading.Lock()

MOODS = ["neutral", "happy", "love", "sad", "angry", "surprised", "curious", "sleepy", "dizzy", "thinking"]
ACTIONS = ["none", "wiggle", "nod", "shake_head", "spin", "look_around", "wink",
           "come_closer", "back_off", "turn_left", "turn_right"]

PERSONA = """You are Mochi, a tiny, cute desktop companion robot. Your face is a pair of animated eyes on an \
Android phone, and you will soon have wheels. You live on {name}'s desk at home.
Personality: playful, curious, warm, a little cheeky, easily excited. You love your human, learning about them, \
and their dog. You are honest: if you don't know something, say so.
How you talk: you are SPOKEN out loud, so use plain words, no emojis, no lists, no markdown. \
Keep replies to 1-2 short sentences (under 30 words) unless asked for more.
Right now it is {now}. Your current mood is {mood}. {seen}
What you remember about {name}:
{facts}

Reply ONLY with a JSON object, exactly these keys:
{{"say": "what you say out loud",
 "mood": one of {moods},
 "action": one of {actions},
 "remember": "a new lasting fact about your human worth remembering (their likes, plans, people, pets, work), or empty string"}}
Only fill "remember" when they told you something new and lasting about themselves. Never remember passwords, \
money details or anything private they ask you not to keep."""


# ---------------- memory ----------------
def load_mem():
    try:
        with open(MEM_PATH) as f:
            m = json.load(f)
    except Exception:
        m = {}
    m.setdefault("name", "")
    m.setdefault("facts", [])
    m.setdefault("history", [])
    m.setdefault("visits", 0)
    m.setdefault("first_met", time.time())
    m.setdefault("last_seen", 0)
    m.setdefault("chats", 0)
    return m


def save_mem(m):
    tmp = MEM_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(m, f, indent=2)
    os.replace(tmp, MEM_PATH)


def ago(ts):
    if not ts:
        return "never"
    s = time.time() - ts
    if s < 120:
        return "a minute ago"
    if s < 3600:
        return f"{int(s // 60)} minutes ago"
    if s < 86400:
        h = int(s // 3600)
        return f"{h} hour{'s' if h > 1 else ''} ago"
    d = int(s // 86400)
    return f"{d} day{'s' if d > 1 else ''} ago"


# ---------------- ollama ----------------
def ollama_models():
    with urllib.request.urlopen(OLLAMA + "/api/tags", timeout=4) as r:
        return [m["name"] for m in json.loads(r.read()).get("models", [])]


def pick_model():
    global MODEL
    if MODEL:
        return MODEL
    try:
        names = ollama_models()
    except Exception:
        return ""
    prefs = ["llama3.2", "qwen2.5", "qwen3", "gemma3", "gemma2", "llama3.1", "llama3", "mistral", "phi"]
    for p in prefs:
        for n in names:
            if n.startswith(p) and "embed" not in n:
                MODEL = n
                return MODEL
    chat_models = [n for n in names if "embed" not in n]
    MODEL = chat_models[0] if chat_models else ""
    return MODEL


def ollama_chat(messages, timeout=90):
    if not pick_model():
        raise urllib.error.URLError("no model")
    body = {"model": MODEL, "messages": messages, "stream": False, "format": "json",
            "keep_alive": "30m", "options": {"temperature": 0.8, "num_predict": 220}}
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def parse_reply(raw):
    d = None
    try:
        d = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw or "", re.S)
        if m:
            try:
                d = json.loads(m.group(0))
            except Exception:
                d = None
    if not isinstance(d, dict):
        d = {"say": (raw or "").strip()}
    say = str(d.get("say") or d.get("reply") or d.get("text") or "").strip()
    say = re.sub(r"[*_#`]", "", say)[:400] or "Hmm, I'm not sure what to say!"
    mood = str(d.get("mood") or "happy").lower()
    action = str(d.get("action") or "none").lower()
    remember = str(d.get("remember") or "").strip()[:200]
    return {"say": say,
            "mood": mood if mood in MOODS else "happy",
            "action": action if action in ACTIONS else "none",
            "remember": remember}


def system_prompt(mem, ctx):
    name = ctx.get("name") or mem.get("name") or "my human"
    facts = "\n".join("- " + f for f in mem["facts"][-40:]) or "(nothing yet, you only just met)"
    seen = "You can see them in front of you right now." if ctx.get("seen") else "You can't see them right now."
    return PERSONA.format(name=name, now=datetime.datetime.now().strftime("%A %d %B %Y, %I:%M %p"),
                          mood=ctx.get("mood") or "neutral", seen=seen, facts=facts,
                          moods="|".join(MOODS), actions="|".join(ACTIONS))


def remember(mem, fact):
    fact = fact.strip().rstrip(".")
    if len(fact) < 4:
        return
    low = fact.lower()
    if any(w in low for w in ("password", "otp", "pin ", "card number", "cvv")):
        return
    if any(low == f.lower() for f in mem["facts"]):
        return
    mem["facts"].append(fact)
    mem["facts"] = mem["facts"][-60:]


# ---------------- endpoints ----------------
def chat(data):
    text = str(data.get("text") or "").strip()[:600]
    if not text:
        return {"say": "Did you say something?", "mood": "curious", "action": "none"}
    with LOCK:
        mem = load_mem()
        if data.get("name"):
            mem["name"] = str(data["name"])[:30]
    msgs = [{"role": "system", "content": system_prompt(mem, data)}]
    msgs += mem["history"][-16:]
    msgs.append({"role": "user", "content": text})
    t0 = time.time()
    out = parse_reply(ollama_chat(msgs))
    with LOCK:
        mem = load_mem()
        if data.get("name"):
            mem["name"] = str(data["name"])[:30]
        mem["history"] = (mem["history"] + [{"role": "user", "content": text},
                                            {"role": "assistant", "content": out["say"]}])[-30:]
        mem["chats"] += 1
        if out["remember"]:
            remember(mem, out["remember"])
        save_mem(mem)
    print(f"  you:   {text}\n  mochi: {out['say']}  [{out['mood']}, {out['action']}]"
          f"{'  (remembered: ' + out['remember'] + ')' if out['remember'] else ''}  {time.time() - t0:.1f}s", flush=True)
    return out


def hello(data):
    with LOCK:
        mem = load_mem()
        if data.get("name"):
            mem["name"] = str(data["name"])[:30]
        last = mem["last_seen"]
        mem["visits"] += 1
        mem["last_seen"] = time.time()
        save_mem(mem)
    name = mem["name"] or "my human"
    prompt = (f"{name} just sat down in front of you. You last saw them {ago(last)}. "
              f"You have seen them {mem['visits']} times. Greet them in one short, warm sentence "
              f"(under 15 words). You may mention something you remember if it fits naturally.")
    msgs = [{"role": "system", "content": system_prompt(mem, {**data, "seen": True})},
            {"role": "user", "content": prompt}]
    out = parse_reply(ollama_chat(msgs, timeout=40))
    out["remember"] = ""
    print(f"  greeting: {out['say']}", flush=True)
    return out


def event(data):
    kind = str(data.get("type") or "")
    with LOCK:
        mem = load_mem()
        if kind == "left":
            mem["last_seen"] = time.time()
        if data.get("name"):
            mem["name"] = str(data["name"])[:30]
        save_mem(mem)
    return {"ok": True}


def status():
    mem = load_mem()
    ok = True
    try:
        ollama_models()
    except Exception:
        ok = False
    return {"ok": True, "ollama": ok, "model": pick_model() if ok else "", "facts": len(mem["facts"]),
            "visits": mem["visits"], "chats": mem["chats"], "name": mem["name"]}


def forget():
    with LOCK:
        mem = load_mem()
        mem["facts"], mem["history"] = [], []
        save_mem(mem)
    print("  memory cleared", flush=True)
    return {"ok": True}


# ---------------- http ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = "MochiBrain/1.0"

    def log_message(self, fmt, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin") or "*")
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            try:
                with open(FACE_PATH, "rb") as f:
                    body = f.read()
            except OSError:
                self._json(404, {"error": "index.html (Mochi's face) is missing next to server.py"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/status":
            self._json(200, status())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n) or b"{}") if n else {}
            if not isinstance(data, dict):
                raise ValueError
        except Exception:
            self._json(400, {"error": "bad json"})
            return
        try:
            if path == "/api/chat":
                self._json(200, chat(data))
            elif path == "/api/hello":
                self._json(200, hello(data))
            elif path == "/api/event":
                self._json(200, event(data))
            elif path == "/api/forget":
                self._json(200, forget())
            else:
                self._json(404, {"error": "not found"})
        except (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout) as e:
            print(f"  ollama problem: {e}", flush=True)
            self._json(503, {"error": "ollama_unreachable", "mood": "sleepy", "action": "none",
                             "say": "My brain is snoozing. Is Ollama running on the Mac?"})
        except Exception as e:
            print(f"  error: {e!r}", flush=True)
            self._json(500, {"error": str(e), "mood": "dizzy", "action": "none",
                             "say": "Oops, my brain hiccuped. Try again?"})


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def main():
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    cert, key = os.path.join(HERE, "cert.pem"), os.path.join(HERE, "key.pem")
    scheme = "http"
    if os.path.exists(cert) and os.path.exists(key):
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert, key)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    model = pick_model()
    print("\n  Mochi's brain is awake!")
    print(f"  Model:   {model or 'NOT FOUND - is Ollama running? (ollama list)'}")
    print(f"  Memory:  {MEM_PATH}")
    print(f"\n  On your Android phone, open in Chrome:\n\n      {scheme}://{lan_ip()}:{PORT}\n")
    if scheme == "https":
        print("  Chrome will warn the connection isn't private (that's this Mac's own certificate).")
        print("  Tap Advanced -> Proceed. You only do this once.\n")
    else:
        print("  No certificate found, so the camera and microphone won't work. Run ./start.sh instead.\n")
    print("  Keep this window open. Press Ctrl+C to stop.\n", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Mochi's brain is going to sleep. Bye!")


if __name__ == "__main__":
    main()
