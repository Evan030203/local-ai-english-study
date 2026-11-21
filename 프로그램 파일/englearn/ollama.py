"""Ollama client (local only, proxy bypassed) with a priority gate.

Interactive requests (role-play, explanations) pre-empt background batches:
a running background generation is stopped (stream closed) and retried later.
"""
import json
import re
import threading
import time
import urllib.error
import urllib.request

from . import config

NUM_CTX = 8192
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_caps_cache = {}


class OllamaError(Exception):
    pass


class Preempted(Exception):
    pass


class Gate:
    def __init__(self):
        self._lock = threading.Lock()
        self.pending = 0
        self.last_interactive = 0.0

    def interactive(self):
        gate = self

        class _Ctx:
            def __enter__(self):
                with gate._lock:
                    gate.pending += 1
                    gate.last_interactive = time.time()

            def __exit__(self, *a):
                with gate._lock:
                    gate.pending -= 1
                    gate.last_interactive = time.time()

        return _Ctx()

    def busy(self):
        return self.pending > 0

    def wait_turn(self, cancel=None, quiet=6.0):
        """Background work waits until no interactive call happened for `quiet` seconds."""
        while True:
            if cancel and cancel():
                return False
            if self.pending == 0 and time.time() - self.last_interactive >= quiet:
                return True
            time.sleep(0.4)


gate = Gate()


def base_url():
    return (config.get("ollama_url") or "http://127.0.0.1:11434").rstrip("/")


def _req(method, path, payload=None, timeout=30):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(base_url() + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        return _opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        msg = body
        try:
            msg = json.loads(body).get("error", body)
        except Exception:
            pass
        raise OllamaError(f"HTTP {e.code}: {msg}") from e
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise OllamaError("Ollama에 연결할 수 없어요. Ollama가 켜져 있는지 확인해 주세요. "
                          f"({getattr(e, 'reason', e)})") from e


def version():
    with _req("GET", "/api/version", timeout=5) as r:
        return json.loads(r.read().decode("utf-8")).get("version", "")


def list_models():
    with _req("GET", "/api/tags", timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [m.get("name") or m.get("model") for m in data.get("models", [])]


def capabilities(model):
    if model in _caps_cache:
        return _caps_cache[model]
    caps = []
    try:
        with _req("POST", "/api/show", {"model": model}, timeout=20) as r:
            info = json.loads(r.read().decode("utf-8"))
        caps = info.get("capabilities") or []
    except OllamaError:
        caps = []
    _caps_cache[model] = caps
    return caps


def _usable(name):
    n = name.lower()
    return not any(k in n for k in ("embed", "bge", "nomic", "minilm", "reasoning", "vision", "-ocr", "whisper", "tts"))


PREFER = ("qwen3", "exaone", "gemma3", "gemma", "llama3", "mistral", "phi4", "qwen2")


def pick_model(models=None):
    chosen = config.get("model")
    models = models if models is not None else list_models()
    if chosen and chosen in models:
        return chosen
    usable = [m for m in models if _usable(m)] or models
    for key in PREFER:
        for m in usable:
            if key in m.lower():
                return m
    return usable[0] if usable else ""


THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def chat(messages, schema=None, temperature=0.4, model=None, num_predict=900, timeout=900,
         should_stop=None, interactive=True):
    """Return the assistant text. schema: JSON schema dict (structured output) or "json"."""
    model = model or pick_model()
    if not model:
        raise OllamaError("Ollama에 설치된 언어 모델이 없어요. 예: 명령 프롬프트에서 'ollama pull qwen3.5:4b'")
    payload = {
        "model": model, "messages": messages, "stream": True, "keep_alive": "30m",
        "options": {"temperature": temperature, "num_ctx": NUM_CTX, "num_predict": num_predict},
    }
    if schema is not None:
        payload["format"] = schema
    if "thinking" in capabilities(model):
        payload["think"] = False

    def run(p):
        out = []
        with _req("POST", "/api/chat", p, timeout=timeout) as r:
            for raw in r:
                if should_stop and should_stop():
                    raise Preempted()
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line.decode("utf-8"))
                except ValueError:
                    continue
                if obj.get("error"):
                    raise OllamaError(obj["error"])
                msg = obj.get("message") or {}
                out.append(msg.get("content") or "")
                if obj.get("done"):
                    break
        return "".join(out)

    def go():
        try:
            return run(payload)
        except OllamaError as e:
            s = str(e)
            if "think" in s.lower() and "think" in payload:
                payload.pop("think", None)
                return run(payload)
            if isinstance(schema, dict) and ("format" in s.lower() or "schema" in s.lower() or "HTTP 400" in s):
                payload["format"] = "json"  # older Ollama: plain JSON mode
                return run(payload)
            raise

    if interactive:
        with gate.interactive():
            text = go()
    else:
        text = go()
    return THINK_RE.sub("", text).strip()


def parse_json(text):
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    try:
        return json.loads(t)
    except ValueError:
        pass
    a, b = t.find("{"), t.rfind("}")
    if a != -1 and b > a:
        frag = t[a:b + 1]
        for candidate in (frag, re.sub(r",\s*([}\]])", r"\1", frag)):
            try:
                return json.loads(candidate)
            except ValueError:
                continue
    raise OllamaError("AI 답을 해석하지 못했어요 (JSON 형식 아님).")


def chat_json(messages, schema, retries=1, **kw):
    last = None
    for attempt in range(retries + 1):
        text = chat(messages, schema=schema, **kw)
        try:
            return parse_json(text)
        except OllamaError as e:
            last = e
            kw["temperature"] = 0.2
    raise last


def status():
    try:
        v = version()
        models = list_models()
        return {"ok": True, "version": v, "models": models, "model": pick_model(models)}
    except OllamaError as e:
        return {"ok": False, "error": str(e), "models": [], "model": ""}


# ---------------------------------------------------------------- setup helpers
RECOMMENDED = "qwen3.5:4b"
RECOMMENDED_GB = 3.4


def is_running(timeout=2):
    try:
        with _req("GET", "/api/version", timeout=timeout) as r:
            r.read()
        return True
    except OllamaError:
        return False


def has_usable_model():
    try:
        models = list_models()
    except OllamaError:
        return False
    return any(_usable(m) for m in models)


def find_exe():
    """Where Ollama is installed on this computer, or "" (Windows installs per user)."""
    import os
    import shutil
    found = shutil.which("ollama")
    if found:
        return found
    candidates = []
    if os.environ.get("LOCALAPPDATA"):
        candidates.append(os.path.join(os.environ["LOCALAPPDATA"], "Programs", "Ollama", "ollama.exe"))
    if os.environ.get("ProgramFiles"):
        candidates.append(os.path.join(os.environ["ProgramFiles"], "Ollama", "ollama.exe"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return ""


def start(exe=None, wait=25):
    """Start Ollama in the background (its tray app when there is one) and wait until it answers."""
    import os
    import subprocess
    exe = exe or find_exe()
    if not exe:
        return False
    app = os.path.join(os.path.dirname(exe), "ollama app.exe")
    flags = 0
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) \
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        if os.path.isfile(app):
            subprocess.Popen([app], creationflags=flags, close_fds=True)
        else:
            subprocess.Popen([exe, "serve"], creationflags=flags, close_fds=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return False
    end = time.time() + wait
    while time.time() < end:
        if is_running(timeout=1):
            return True
        time.sleep(0.7)
    return is_running(timeout=2)


def pull(model=RECOMMENDED, on_progress=None, should_stop=None):
    """Download a model through Ollama. on_progress(fraction 0..1 or None, status text, done bytes, total bytes)."""
    layers = {}
    with _req("POST", "/api/pull", {"model": model, "name": model, "stream": True}, timeout=3600) as r:
        for raw in r:
            if should_stop and should_stop():
                raise Preempted()
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            if obj.get("error"):
                raise OllamaError(obj["error"])
            st = obj.get("status") or ""
            if obj.get("digest") and obj.get("total"):
                layers[obj["digest"]] = (int(obj.get("completed") or 0), int(obj["total"]))
            done = sum(c for c, _ in layers.values())
            total = sum(t for _, t in layers.values())
            frac = (done / total) if total else None
            if on_progress:
                on_progress(frac, st, done, total)
            if st == "success":
                return True
    if not has_usable_model():
        raise OllamaError("모델 받기가 끝나지 않았어요. 인터넷 연결을 확인하고 다시 해 주세요.")
    return True
