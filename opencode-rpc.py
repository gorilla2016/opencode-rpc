#!/usr/bin/env python3
"""
opencode-rpc - Discord Rich Presence for opencode.

Reads opencode's local SQLite store and pushes a "Watching opencode" card:
  Working in <session title / override>
  Using <tool> . <model> . <N> output tokens
Zero runtime dependencies. Requires Discord Desktop running.

Config: %USERPROFILE%\\.opencode-rpc\\config.json (auto-created).
"""
import json
import os
import sqlite3
import struct
import sys
import time
import uuid

HOME = os.path.expanduser("~")
CONFIG_DIR = os.path.join(HOME, ".opencode-rpc")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
DB_PATH = os.path.join(HOME, ".local", "share", "opencode", "opencode.db")

# Little terminal-creature mascot, animated per state (hosted, public HTTPS).
ASSETS = {
    "idle": "https://files.catbox.moe/j19ygt.gif",
    "working": "https://files.catbox.moe/1yqb7h.gif",
    "thinking": "https://files.catbox.moe/kg236f.gif",
    "error": "https://files.catbox.moe/qzr1kq.gif",
    "done": "https://files.catbox.moe/hg2x2f.gif",
}

DEFAULTS = {
    "client_id": "1565535814308470814",
    "activity_name": "opencode",
    "title_override": "IDA decompiling",
    "large_image": "",
    "large_text": "opencode",
    "assets": dict(ASSETS),
    "update_interval": 15,
    "resend_interval": 30,
    "active_window": 900,
    "show_tokens": True,
    "privacy": "public",
    "detail_level": "minimal",  # minimal | normal | full (full leaks commands)
    "db_path": DB_PATH,
}


def load_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    cfg = dict(DEFAULTS)
    cfg["assets"] = dict(ASSETS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                disk = json.load(f)
            if isinstance(disk.get("assets"), dict):
                merged = dict(ASSETS)
                merged.update(disk["assets"])
                disk["assets"] = merged
            cfg.update(disk)
        except Exception as e:
            print(f"[config] failed to read {CONFIG_PATH}: {e}")
    else:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(DEFAULTS, f, indent=2)
        print(f"[config] created {CONFIG_PATH}")
    return cfg


def fmt_tokens(n):
    try:
        n = int(n)
    except Exception:
        return "0"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def parse_json(s):
    try:
        return json.loads(s) if s else None
    except Exception:
        return None


def model_name(session_model):
    m = parse_json(session_model)
    if isinstance(m, dict):
        return m.get("id") or m.get("modelID") or m.get("model") or "unknown"
    if isinstance(m, str):
        return m
    return "unknown"


class Store:
    def __init__(self, db_path):
        self.db_path = db_path
        self._warned = False

    def _connect(self):
        return sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=3)

    def snapshot(self):
        if not os.path.exists(self.db_path):
            if not self._warned:
                print(f"[db] not found: {self.db_path}")
                self._warned = True
            return None
        try:
            con = self._connect()
        except Exception as e:
            if not self._warned:
                print(f"[db] open failed: {e}")
                self._warned = True
            return None
        con.row_factory = sqlite3.Row
        try:
            cur = con.cursor()
            row = cur.execute(
                "SELECT id,title,directory,path,model,agent,tokens_output,"
                "cost,time_created,time_updated FROM session "
                "WHERE time_archived IS NULL OR time_archived = 0 "
                "ORDER BY time_updated DESC LIMIT 1"
            ).fetchone()
            if not row:
                return None
            sid = row["id"]

            last_user_ms = None
            for m in cur.execute(
                "SELECT data,time_created FROM message WHERE session_id=? "
                "ORDER BY time_created DESC LIMIT 40", (sid,)
            ):
                d = parse_json(m["data"])
                if isinstance(d, dict) and d.get("role") == "user":
                    last_user_ms = m["time_created"]
                    break

            last_part = None
            last_tool = None
            for p in cur.execute(
                "SELECT data,time_created FROM part WHERE session_id=? "
                "ORDER BY time_created DESC LIMIT 40", (sid,)
            ):
                d = parse_json(p["data"])
                if not isinstance(d, dict):
                    continue
                if last_part is None:
                    last_part = d
                if d.get("type") == "tool" and last_tool is None:
                    last_tool = d
                    break
            return {
                "id": sid,
                "title": row["title"],
                "directory": row["directory"],
                "model": model_name(row["model"]),
                "tokens_output": row["tokens_output"] or 0,
                "time_created": row["time_created"],
                "time_updated": row["time_updated"],
                "last_user_ms": last_user_ms,
                "last_part": last_part,
                "last_tool": last_tool,
            }
        except Exception as e:
            if not self._warned:
                print(f"[db] query failed: {e}")
                self._warned = True
            return None
        finally:
            con.close()


def project_label(snap, cfg):
    if cfg.get("title_override"):
        return cfg["title_override"]
    if cfg["privacy"] == "private":
        return "a project"
    title = (snap.get("title") or "").strip()
    if title:
        return title
    d = snap.get("directory") or ""
    base = os.path.basename(d.replace("\\", "/").rstrip("/"))
    return base or "a project"


def _short(s, n=56):
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _base(p):
    if not p:
        return ""
    return os.path.basename(p.replace("\\", "/").rstrip("/"))


def describe_tool(part, cfg):
    """Turn the newest tool part into a short, non-leaky line.

    detail_level:
      minimal (default) - action + tool name only, no args/paths/queries
      normal            - adds program name / file basename (no full command)
      full              - full command/pattern/url (opt-in)
    """
    if not isinstance(part, dict):
        return None
    level = str(cfg.get("detail_level") or "minimal").lower()
    private = cfg.get("privacy") == "private"
    tool = part.get("tool") or part.get("name") or "tool"
    st = part.get("state") or {}
    inp = st.get("input") or {}
    tl = str(tool).lower()

    def program(cmd):
        first = cmd.strip().split()[0] if cmd.strip() else ""
        first = first.strip("\"'")
        return os.path.basename(first.replace("\\", "/")) or first

    if tl in ("bash", "shell", "terminal", "cmd", "exec", "run"):
        cmd = (inp.get("command") or inp.get("cmd") or "").strip()
        if private or level == "minimal":
            return "Running a command"
        if level == "normal":
            return f"Running {program(cmd)}" if cmd else "Running a command"
        return f"Running: {_short(cmd)}"

    if tl in ("edit", "write", "patch", "multiedit", "apply_patch"):
        fp = inp.get("filePath") or inp.get("path") or ""
        if private or level == "minimal" or not fp:
            return "Editing a file"
        return f"Editing {_base(fp)}"

    if tl == "read":
        fp = inp.get("filePath") or inp.get("path") or ""
        if private or level == "minimal" or not fp:
            return "Reading a file"
        return f"Reading {_base(fp)}"

    if tl in ("grep", "glob", "search"):
        q = inp.get("pattern") or inp.get("query") or inp.get("include") or ""
        if level == "full" and q:
            return f"Searching: {_short(q, 32)}"
        return "Searching"

    if tl == "task":
        d = inp.get("description") or inp.get("prompt") or ""
        if level == "full" and d:
            return f"Delegating: {_short(d, 40)}"
        return "Delegating"

    if tl in ("webfetch", "websearch"):
        q = inp.get("url") or inp.get("query") or ""
        if level == "full" and q:
            return f"Fetching: {_short(q, 40)}"
        return "Fetching a page"

    if tl == "todowrite":
        return "Updating todos"
    if tl in ("list", "ls"):
        return "Listing files"
    return "Using a tool" if private else f"Using {tool}"


def visual_state(snap):
    lt = snap.get("last_tool")
    lp = snap.get("last_part") or {}
    if lt:
        st = (lt.get("state") or {}).get("status")
        if st == "running":
            return "working"
        if st == "error":
            return "error"
    if isinstance(lp, dict):
        t = lp.get("type")
        if t == "reasoning":
            return "thinking"
        if t == "text":
            return "working"
    return "idle"


def build_activity(snap, cfg, now):
    tokens = snap["tokens_output"]
    model = snap["model"]
    last_tool = snap.get("last_tool")
    last_part = snap.get("last_part") or {}
    visual = visual_state(snap)

    parts = []
    active = visual in ("working", "thinking")
    if last_tool:
        desc = describe_tool(last_tool, cfg)
        status = (last_tool.get("state") or {}).get("status")
        if status == "error":
            parts.append(f"Error in {last_tool.get('tool') or 'tool'}")
        else:
            parts.append(desc or "Working")
    elif isinstance(last_part, dict) and last_part.get("type") == "reasoning":
        parts.append("Thinking")
    elif isinstance(last_part, dict) and last_part.get("type") == "text":
        parts.append("Responding")

    if cfg.get("show_tokens", True):
        parts.append(model)
        parts.append(f"{fmt_tokens(tokens)} output tokens")
    else:
        parts.append(model)

    state = " · ".join([p for p in parts if p])[:128]
    details = f"Working in {project_label(snap, cfg)}"[:128]

    updated_s = (snap.get("time_updated") or 0) / 1000.0
    idle = (not active) and (now - updated_s) > cfg.get("active_window", 900)
    if idle:
        visual = "idle"

    activity = {
        "name": cfg["activity_name"],
        "type": 3,
        "details": "Idle" if idle else details,
        "state": state,
    }
    if not idle:
        start_ms = snap.get("last_user_ms") or snap.get("time_created") or snap.get("time_updated")
        if start_ms:
            activity["timestamps"] = {"start": int(start_ms / 1000)}

    image = cfg.get("large_image") or (cfg.get("assets") or {}).get(visual) or (cfg.get("assets") or {}).get("idle")
    if image:
        activity["assets"] = {"large_image": image, "large_text": cfg.get("large_text", "opencode")}
    return activity


class DiscordIPC:
    """Single-threaded Discord IPC. Reads are PeekNamedPipe-polled so a blocking
    read never holds the fd lock and stalls writes (the old bug)."""

    def __init__(self, client_id):
        self.client_id = str(client_id)
        self.f = None
        self.fd = None
        self.connected = False
        self.close_reason = None
        if os.name == "nt":
            import ctypes
            import msvcrt
            self._ctypes = ctypes
            self._msvcrt = msvcrt
            self._k32 = ctypes.windll.kernel32

    def _pipe_path(self, i):
        return rf"\\.\pipe\discord-ipc-{i}"

    def connect(self):
        self.close()
        f = None
        for i in range(10):
            try:
                f = open(self._pipe_path(i), "r+b", buffering=0)
                break
            except OSError:
                f = None
        if not f:
            raise ConnectionError("Discord IPC pipe not found (is Discord Desktop running?)")
        self.f = f
        self.fd = f.fileno()
        self.connected = True
        self.close_reason = None
        self._send(0, {"v": 1, "client_id": self.client_id})
        deadline = time.time() + 10
        while time.time() < deadline:
            for op, p in self._read_frames():
                if isinstance(p, dict) and p.get("evt") == "READY":
                    return
                if op == 2:
                    self._send(4, p)
            time.sleep(0.02)
        raise ConnectionError("handshake timeout")

    def _peek(self):
        if os.name != "nt":
            return 1
        try:
            h = self._msvcrt.get_osfhandle(self.fd)
            avail = self._ctypes.c_ulong(0)
            ok = self._k32.PeekNamedPipe(h, None, 0, None, self._ctypes.byref(avail), None)
            return avail.value if ok else 0
        except Exception:
            return 0

    def _read_exact(self, n):
        buf = b""
        while len(buf) < n:
            if self._peek() <= 0:
                if not self.connected:
                    raise ConnectionError("closed")
                time.sleep(0.02)
                continue
            chunk = os.read(self.fd, n - len(buf))
            if not chunk:
                raise EOFError("discord pipe closed")
            buf += chunk
        return buf

    def _read_frames(self):
        frames = []
        while self.connected and self._peek() > 0:
            try:
                header = self._read_exact(8)
                op, length = struct.unpack("<II", header)
                payload = self._read_exact(length)
                try:
                    payload = json.loads(payload.decode("utf-8"))
                except Exception:
                    pass
                frames.append((op, payload))
            except (EOFError, OSError):
                self.connected = False
                break
        return frames

    def poll(self):
        for op, payload in self._read_frames():
            if op == 2:
                try:
                    self._send(4, payload)
                except Exception:
                    self.connected = False
            elif op == 3:
                self.close_reason = payload
                self.connected = False
        return self.connected

    def _send(self, op, obj):
        if self.fd is None:
            raise ConnectionError("not connected")
        data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        os.write(self.fd, struct.pack("<II", op, len(data)) + data)

    def set_activity(self, activity):
        if not self.connected:
            raise ConnectionError("not connected")
        self._send(1, {
            "cmd": "SET_ACTIVITY",
            "args": {"pid": os.getpid(), "activity": activity},
            "nonce": str(uuid.uuid4()),
        })

    def close(self):
        self.connected = False
        try:
            if self.f:
                self.f.close()
        except Exception:
            pass
        self.f = None
        self.fd = None


def main():
    cfg = load_config()
    once = "--once" in sys.argv
    store = Store(cfg.get("db_path") or DB_PATH)
    ipc = DiscordIPC(cfg["client_id"])
    print(f"[opencode-rpc] db={store.db_path}")
    print(f"[opencode-rpc] client_id={cfg['client_id']} interval={cfg['update_interval']}s")
    last_sig = None
    last_sent = 0.0
    last_update = 0.0
    while True:
        try:
            if not ipc.connected:
                ipc.close()
                ipc.connect()
                print("[opencode-rpc] connected to Discord")
                last_sig = None
            ipc.poll()
            if not ipc.connected:
                raise ConnectionError(f"disconnected: {ipc.close_reason}")
            now = time.time()
            if now - last_update >= max(1, int(cfg.get("update_interval", 15))):
                last_update = now
                snap = store.snapshot()
                if snap:
                    act = build_activity(snap, cfg, now)
                else:
                    act = {
                        "name": cfg["activity_name"], "type": 3, "details": "Idle",
                        "assets": {"large_image": (cfg.get("assets") or {}).get("idle", ""),
                                   "large_text": "opencode"},
                    }
                sig = json.dumps(act, sort_keys=True)
                if sig != last_sig or (now - last_sent) >= cfg.get("resend_interval", 30):
                    ipc.set_activity(act)
                    last_sig = sig
                    last_sent = now
                    print(f"[opencode-rpc] {act.get('details')} | {act.get('state')}")
                if once:
                    ipc.close()
                    return
        except (ConnectionError, EOFError, OSError) as e:
            print(f"[opencode-rpc] ipc error: {e}; reconnecting")
            ipc.close()
            if once:
                return
            time.sleep(2)
            continue
        except Exception as e:
            print(f"[opencode-rpc] error: {e}")
            ipc.close()
            if once:
                return
            time.sleep(2)
            continue
        time.sleep(0.5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[opencode-rpc] stopped")
