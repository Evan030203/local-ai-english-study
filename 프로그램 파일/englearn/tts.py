"""Natural English voice that runs on this computer (Kokoro TTS, ONNX, CPU).

Windows often has no English voice installed, so questions and example sentences are
spoken with Kokoro (82M parameters, int8). Model files (≈120 MB) are downloaded once
into 프로그램 파일/모델/kokoro/.

Kokoro uses espeak-ng for phonemes, and espeak-ng calls exit() when it cannot read its
data folder. To keep that from ever closing the app, synthesis runs in a separate worker
process (englearn/tts_worker.py); the data folder is given to espeak-ng through an
ASCII-only path because the tool folder contains Korean letters.
"""
import hashlib
import importlib.util
import json
import logging
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from pathlib import Path

from . import paths

log = logging.getLogger("englearn")
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {"model": ("kokoro-v1.0.int8.onnx", 92361271), "voices": ("voices-v1.0.bin", 28214398)}
VOICES = [
    ("af_heart", "미국 여성 (Heart)"), ("af_bella", "미국 여성 (Bella)"), ("am_michael", "미국 남성 (Michael)"),
    ("am_fenrir", "미국 남성 (Fenrir)"), ("bf_emma", "영국 여성 (Emma)"), ("bm_george", "영국 남성 (George)"),
]
PACKAGE = "kokoro-onnx==0.4.7"
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

_lock = threading.Lock()
_worker = None
_last_error = ""


class Cancelled(Exception):
    pass


def model_dir():
    return paths.MODELS_DIR / "kokoro"


def package_ok():
    try:
        return importlib.util.find_spec("kokoro_onnx") is not None
    except (ImportError, ValueError):
        return False


def files_ok():
    d = model_dir()
    return all((d / name).is_file() and (d / name).stat().st_size == size for name, size in FILES.values())


def ready():
    return package_ok() and files_ok()


def status():
    return {"ready": ready(), "package": package_ok(), "files": files_ok(), "error": _last_error,
            "voices": [{"id": v, "name": n} for v, n in VOICES], "mb": 120}


# ---------------------------------------------------------------- install
def _download(url, dest, size, on_progress, base_done, total, cancel):
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"User-Agent": "englearn-local/1.0"}
    if have:
        headers["Range"] = f"bytes={have}-"
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60)
    except urllib.error.HTTPError as e:
        if e.code == 416 and have == size:
            os.replace(part, dest)
            return
        raise RuntimeError(f"음성 파일 내려받기 실패: HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"인터넷 연결을 확인해 주세요. ({e.reason})") from e
    with resp:
        if have and resp.status != 206:
            have = 0
        with open(part, "ab" if have else "wb") as f:
            done, last = have, 0.0
            while True:
                if cancel and cancel():
                    raise Cancelled()
                chunk = resp.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if on_progress and time.time() - last > 0.3:
                    on_progress(base_done + done, total)
                    last = time.time()
    if part.stat().st_size != size:
        raise RuntimeError("음성 파일이 덜 받아졌어요. 다시 시도해 주세요.")
    os.replace(part, dest)


def install(on_progress=None, on_msg=None, cancel=None):
    """pip-install the package if missing, fetch the model files, then test once."""
    global _last_error
    _last_error = ""
    if not package_ok():
        if on_msg:
            on_msg("영어 음성 부품 설치 중… (pip)")
        p = subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", PACKAGE],
                           capture_output=True, creationflags=CREATE_NO_WINDOW)
        importlib.invalidate_caches()
        if p.returncode != 0 or not package_ok():
            tail = p.stderr.decode("utf-8", errors="replace").strip().splitlines()[-3:]
            raise RuntimeError("영어 음성 부품을 설치하지 못했어요: " + " ".join(tail))
    d = model_dir()
    d.mkdir(parents=True, exist_ok=True)
    total = sum(s for _, s in FILES.values())
    base = 0
    for name, size in FILES.values():
        dest = d / name
        if not (dest.is_file() and dest.stat().st_size == size):
            if on_msg:
                on_msg("영어 음성 모델 내려받는 중…")
            _download(BASE + name, dest, size, on_progress, base, total, cancel)
        base += size
    if on_progress:
        on_progress(total, total)
    if on_msg:
        on_msg("영어 음성 시험하는 중…")
    synth("Hello.", "af_heart", 1.0)


# ---------------------------------------------------------------- worker process
class _Worker:
    def __init__(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8", ENGLEARN_MODELS=str(paths.MODELS_DIR))
        self.proc = subprocess.Popen([sys.executable, "-m", "englearn.tts_worker"], cwd=str(paths.ENGINE_DIR),
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                     env=env, creationflags=CREATE_NO_WINDOW)
        self.err = deque(maxlen=30)
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self):
        for raw in iter(self.proc.stderr.readline, b""):
            line = raw.decode("utf-8", errors="replace").rstrip()
            if line:
                self.err.append(line)
                log.info("tts worker: %s", line)

    def alive(self):
        return self.proc.poll() is None

    def ask(self, req, timeout=120):
        self.proc.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
        self.proc.stdin.flush()
        result = {}

        def read():
            result["line"] = self.proc.stdout.readline()

        t = threading.Thread(target=read, daemon=True)
        t.start()
        deadline = time.time() + timeout
        while True:
            t.join(max(0.1, deadline - time.time()))
            if t.is_alive():
                self.proc.kill()
                raise RuntimeError("영어 음성이 너무 오래 걸려서 멈췄어요.")
            line = result.get("line") or b""
            if not line:
                time.sleep(0.2)
                tail = " / ".join(list(self.err)[-3:])
                raise RuntimeError("영어 음성 엔진이 멈췄어요." + (f" ({tail})" if tail else ""))
            try:
                obj = json.loads(line.decode("utf-8", errors="replace"))
                if isinstance(obj, dict) and "ok" in obj:
                    return obj
            except ValueError:
                pass
            self.err.append(line.decode("utf-8", errors="replace").rstrip())  # stray library output
            result.clear()
            t = threading.Thread(target=read, daemon=True)
            t.start()

    def close(self):
        try:
            self.proc.kill()
        except Exception:  # noqa: BLE001
            pass


def _key(text, voice, speed):
    return hashlib.sha1(f"{voice}|{speed:.2f}|{text}".encode("utf-8")).hexdigest()[:20]


def _cache_dir():
    d = model_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _prune(d, keep=500):
    files = sorted(d.glob("*.wav"), key=lambda p: p.stat().st_mtime)
    for p in files[:-keep]:
        try:
            p.unlink()
        except OSError:
            pass


def synth(text, voice="af_heart", speed=1.0):
    """Return WAV bytes (mono, 24 kHz, 16-bit). Cached on disk."""
    global _worker, _last_error
    text = " ".join((text or "").split())[:600]
    if not text:
        raise ValueError("읽을 문장이 없어요.")
    voice = voice if voice in dict(VOICES) else "af_heart"
    speed = max(0.6, min(1.4, float(speed or 1.0)))
    out = _cache_dir() / f"{_key(text, voice, speed)}.wav"
    if out.is_file():
        return out.read_bytes()
    with _lock:
        if out.is_file():  # made by a request that held the lock before us
            return out.read_bytes()
        for attempt in range(2):
            if _worker is None or not _worker.alive():
                _worker = _Worker()
            try:
                resp = _worker.ask({"text": text, "voice": voice, "speed": speed, "out": str(out)})
                break
            except RuntimeError as e:
                _last_error = str(e)
                _worker.close()
                _worker = None
                if attempt == 1:
                    raise
        if not resp.get("ok"):
            _last_error = resp.get("error", "")
            raise RuntimeError(f"영어 음성을 만들지 못했어요: {resp.get('error')}")
        _last_error = ""
    _prune(out.parent)
    return out.read_bytes()


def warm():
    """Start the worker and load the model so the first sentence is quick."""
    global _worker
    if not ready():
        return
    with _lock:
        if _worker is None or not _worker.alive():
            _worker = _Worker()
        try:
            _worker.ask({"cmd": "load"}, timeout=180)
        except RuntimeError as e:
            log.warning("voice warm-up failed: %s", e)


def prefetch(text, voice, speed):
    """Make a sentence in the background (e.g. the next interview question)."""
    if not ready() or not text:
        return
    def run():
        try:
            synth(text, voice, speed)
        except Exception as e:  # noqa: BLE001
            log.info("prefetch failed: %s", e)
    threading.Thread(target=run, daemon=True).start()


def shutdown():
    global _worker
    if _worker is not None:
        _worker.close()
        _worker = None
