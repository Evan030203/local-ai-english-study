"""Local web server (127.0.0.1 only) + app window."""
import http.server
import json
import logging
import mimetypes
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

from . import (APP_ID, VERSION, analysis, burnsubs, config, media, ollama, paths, pipeline, project, review,
               roleplay, speech_rules, stt, subtitles, textutil, trash, tts)
from .jobs import jobs
from .speech_rules import CATEGORIES
from .storage import read_json

log = logging.getLogger("englearn")
ROUTES = []
MAX_UPLOAD = 60 * 1024 * 1024
MIME = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".html": "text/html; charset=utf-8", ".woff2": "font/woff2", ".svg": "image/svg+xml",
        ".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".m4a": "audio/mp4",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".mkv": "video/x-matroska",
        ".mov": "video/quicktime", ".json": "application/json; charset=utf-8", ".png": "image/png",
        ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8"}


class App:
    port = 8765
    last_ping = time.time()
    bye_at = None
    hevc_ok = False
    server = None
    stopping = False


class HTTPError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code
        self.msg = msg


def route(method, pattern):
    def deco(fn):
        ROUTES.append((method, re.compile("^" + pattern + "$"), fn))
        return fn
    return deco


# =====================================================================  handler
class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "englearn/" + VERSION

    def log_message(self, fmt, *args):
        log.debug("%s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    # ---------------------------------------------------------------- plumbing
    def _dispatch(self, method):
        self._read = None
        try:
            self._route(method)
        finally:
            self._drain()

    def _drain(self):
        """Read a request body the handler did not use, so it cannot spill into the next keep-alive request."""
        if self._read is not None:
            return
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return
        if n > MAX_UPLOAD:
            self.close_connection = True
            return
        try:
            self.rfile.read(n)
        except OSError:
            self.close_connection = True

    def _route(self, method):
        try:
            host = self.headers.get("Host", "")
            if not re.match(r"^(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", host):
                raise HTTPError(403, "허용되지 않은 주소예요.")
            url = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(url.path)
            self.query = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
            if method == "POST" and path.startswith("/api/") and self.headers.get("X-EngLearn") != "1":
                raise HTTPError(403, "잘못된 요청이에요.")
            want = "GET" if method == "HEAD" else method
            for m, rx, fn in ROUTES:
                if m == want:
                    mt = rx.match(path)
                    if mt:
                        fn(self, *mt.groups())
                        return
            if want == "GET":
                self._static(path)
                return
            raise HTTPError(404, "없는 기능이에요.")
        except HTTPError as e:
            self._json({"error": e.msg}, e.code)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except ollama.OllamaError as e:
            self._json({"error": str(e), "kind": "ollama"}, 503)
        except (KeyError, FileNotFoundError) as e:
            log.info("not found: %s", e)
            self._json({"error": "찾을 수 없어요: " + str(e).strip("'")}, 404)
        except Exception as e:  # noqa: BLE001
            log.exception("request failed: %s", self.path)
            try:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            except Exception:
                pass

    def _send(self, code, body: bytes, ctype, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def ok(self, obj=None, **kw):
        d = dict(obj or {})
        d.update(kw)
        self._json(d)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            self.close_connection = True
            raise HTTPError(413, "보낸 내용이 너무 커요.")
        if self._read is None:
            self._read = self.rfile.read(n) if n else b""
        raw = self._read
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise HTTPError(400, "요청 형식이 잘못됐어요.")

    def raw_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            self.close_connection = True
            raise HTTPError(413, "녹음이 너무 길어요.")
        if self._read is None:
            self._read = self.rfile.read(n) if n else b""
        return self._read

    def _static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        f = (paths.WEB_DIR / path.lstrip("/")).resolve()
        if paths.WEB_DIR.resolve() not in f.parents or not f.is_file():
            raise HTTPError(404, "없는 파일이에요.")
        data = f.read_bytes()
        cache = {"Cache-Control": "max-age=604800"} if f.suffix == ".woff2" else None
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(f.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", (cache or {}).get("Cache-Control", "no-cache"))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_file(self, fpath, ctype=None):
        fpath = str(fpath)
        size = os.path.getsize(fpath)
        ctype = ctype or MIME.get(Path(fpath).suffix.lower(), "application/octet-stream")
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        code = 200
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                s, e = m.groups()
                if s == "" and e:
                    start = max(0, size - int(e))
                else:
                    start = int(s or 0)
                    end = min(size - 1, int(e)) if e else size - 1
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                code = 206
        length = end - start + 1
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-cache")
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with open(fpath, "rb") as fh:
                fh.seek(start)
                left = length
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            self.close_connection = True


# =====================================================================  helpers
def _pid(raw):
    pid = urllib.parse.unquote(raw)
    project.folder(pid)  # raises KeyError
    return pid


def project_summary(p):
    pid = p["id"]
    pr = {}
    try:
        pr = project.progress(pid)
    except KeyError:
        pass
    lp = pr.get("lines", {})
    studied = sum(1 for v in lp.values() if v.get("d") or v.get("s"))
    today = project.today()
    td = (pr.get("days") or {}).get(today, {})
    return {
        "id": pid, "title": p.get("title"), "movie": p.get("movie"), "duration": p.get("duration"),
        "movie_exists": os.path.exists(p.get("movie") or ""), "lines_ready": p.get("lines_ready"),
        "line_count": p.get("line_count"), "en": p.get("en"), "ko": p.get("ko"), "offset": p.get("offset", 0.0),
        "media": p.get("media"), "analysis": p.get("analysis"), "prep": p.get("prep"), "mask": p.get("mask") or {},
        "updated": p.get("updated"), "studied": studied, "today": td,
        "streak": _streak(pr.get("days") or {}),
    }


def _streak(days):
    import datetime as dt
    d = dt.date.today()
    n = 0
    if d.isoformat() not in days:
        d -= dt.timedelta(days=1)
    while d.isoformat() in days:
        n += 1
        d -= dt.timedelta(days=1)
    return n


def clip_bounds(line, off):
    w = line.get("words")
    if w:
        cs, ce = w[0][1] - 0.15, w[-1][2] + 0.25
    else:
        cs, ce = line["start"] - 0.12, line["end"] + 0.15
    return round(max(0.0, cs + off), 3), round(ce + off, 3)


def compact(line, off, lp, starred):
    ai = line.get("ai") or None
    cs, ce = clip_bounds(line, off)
    d = lp.get(str(line["id"])) or {}
    return {
        "id": line["id"], "s": round(line["start"] + off, 3), "e": round(line["end"] + off, 3), "cs": cs, "ce": ce,
        "t": line["text"], "ko": line.get("ko", ""), "kos": line.get("ko_src", ""), "lv": line.get("level", 2),
        "wps": line.get("wps"), "n": line.get("n_words"), "tags": line.get("tags", []),
        "key": bool(line.get("key")), "pk": bool(line.get("pre_key")),
        "ai": ({"u": ai.get("useful"), "x": ai.get("expr"), "xk": ai.get("expr_ko"), "c": ai.get("cat")}
               if ai and not ai.get("failed") else None),
        "bd": max((x[1] for x in d.get("d", [])), default=None),
        "bs": max((x[1] for x in d.get("s", [])), default=None),
        "st": starred,
    }


def line_card_key(pid, lid):
    return f"{pid}|line|{lid}"


def expr_card_key(pid, eid):
    return f"{pid}|expr|{eid}"


def _stt_model():
    name = config.get("stt_model") or "small.en"
    if name not in stt.REPOS:
        name = "small.en"
    return name


def _need_stt():
    if not stt.available():
        raise HTTPError(503, "음성 인식 프로그램이 설치되지 않았어요. 실행 파일을 다시 실행하면 설치를 다시 시도해요. (" + stt.import_error() + ")")
    name = _stt_model()
    if not stt.is_ready(name):
        if not jobs.running("download", name):
            pipeline.job_download(name)
        raise HTTPError(409, "음성 인식 모델을 내려받는 중이에요. 잠시 뒤 다시 해 주세요.")
    return name


def _save_upload(h, folder, stem):
    data = h.raw_body()
    if len(data) < 200:
        raise HTTPError(400, "녹음된 소리가 없어요. 마이크를 확인해 주세요.")
    ctype = (h.headers.get("Content-Type") or "").lower()
    ext = ".webm" if "webm" in ctype else ".ogg" if "ogg" in ctype else ".wav" if "wav" in ctype else ".mp4" if "mp4" in ctype else ".webm"
    folder.mkdir(parents=True, exist_ok=True)
    f = folder / f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}{ext}"
    f.write_bytes(data)
    return f


# =====================================================================  routes: app
@route("GET", r"/api/ping")
def r_ping(h):
    App.last_ping = time.time()
    App.bye_at = None
    h.ok(app=APP_ID, version=VERSION)


@route("POST", r"/api/bye")
def r_bye(h):  # sent with fetch(keepalive) when the window closes
    App.bye_at = time.time()
    h.ok()


@route("POST", r"/api/client")
def r_client(h):
    b = h.body()
    App.hevc_ok = bool(b.get("hevc"))
    h.ok()


@route("POST", r"/api/restart")
def r_restart(h):
    """Start a fresh copy of the program (after an update) and stop this one."""
    h.ok(restarting=True)

    def go():
        time.sleep(0.5)
        # the new copy waits for this one to let go of the port ("--takeover")
        args = [sys.executable, str(paths.ENGINE_DIR / "app.py"), "--no-window", "--takeover"]
        flags = 0x00000010 if os.name == "nt" else 0  # CREATE_NEW_CONSOLE: keeps a visible window
        subprocess.Popen(args, cwd=str(paths.ENGINE_DIR), creationflags=flags)
        App.stopping = True
        tts.shutdown()
        App.server.shutdown()
        App.server.server_close()
        os._exit(0)

    threading.Thread(target=go, daemon=True).start()


@route("GET", r"/api/state")
def r_state(h):
    sample = _sample_movie()
    h.ok(
        app=APP_ID, version=VERSION, settings=config.load(),
        projects=[project_summary(p) for p in project.list_all()],
        jobs=jobs.list(),
        stt={"available": stt.available(), "error": stt.import_error() if not stt.available() else "",
             "models": stt.status(), "model": _stt_model()},
        ffmpeg=bool(media.ffmpeg_exe()), review=review.counts(), tts=tts.status(),
        sample={"exists": bool(sample), "path": str(sample) if sample else ""},
        scenarios=roleplay.scenario_list(), categories=CATEGORIES,
        data_dir=str(paths.DATA_DIR),
    )


@route("GET", r"/api/ollama")
def r_ollama(h):
    st = ollama.status()
    if st.get("ok"):
        st["capabilities"] = {m: ollama.capabilities(m) for m in st["models"][:12]}
    st["need_model"] = bool(st.get("ok")) and not any(ollama._usable(m) for m in st.get("models") or [])
    st["installed"] = bool(st.get("ok")) or bool(ollama.find_exe())
    st["recommended"], st["gb"] = ollama.RECOMMENDED, ollama.RECOMMENDED_GB
    st["pull"] = dict(Pull.state)
    h.ok(st)


class Pull:
    """One model download at a time, started from the screen (POST) and watched by polling (GET)."""
    lock = threading.Lock()
    state = {"running": False, "model": "", "frac": None, "status": "", "done": 0, "total": 0,
             "error": "", "finished": False}


def _pull_worker(model):
    def prog(frac, status, done, total):
        Pull.state.update(frac=frac, status=status, done=done, total=total)
    try:
        ollama.pull(model, on_progress=prog)
        Pull.state.update(finished=True, frac=1.0, status="success")
        log.info("model pulled: %s", model)
    except Exception as e:  # noqa: BLE001
        Pull.state.update(error=str(e))
        log.warning("model pull failed: %s", e)
    finally:
        Pull.state["running"] = False


@route("POST", r"/api/ollama/start")
def r_ollama_start(h):
    exe = ollama.find_exe()
    if not exe:
        raise HTTPError(404, "이 컴퓨터에서 Ollama를 찾지 못했어요. ollama.com/download 에서 설치해 주세요.")
    if not ollama.start(exe):
        raise HTTPError(503, "Ollama가 켜지지 않았어요. 시작 메뉴에서 Ollama를 직접 켜 주세요.")
    h.ok(started=True)


@route("GET", r"/api/ollama/pull")
def r_pull_state(h):
    h.ok(pull=dict(Pull.state), recommended=ollama.RECOMMENDED, gb=ollama.RECOMMENDED_GB)


@route("POST", r"/api/ollama/pull")
def r_pull_start(h):
    model = (h.body().get("model") or ollama.RECOMMENDED).strip()
    with Pull.lock:
        if Pull.state["running"]:
            return h.ok(pull=dict(Pull.state))
        if not ollama.is_running():
            raise ollama.OllamaError("Ollama에 연결할 수 없어요. Ollama를 켠 뒤 다시 해 주세요.")
        Pull.state = {"running": True, "model": model, "frac": None, "status": "시작하는 중", "done": 0,
                      "total": 0, "error": "", "finished": False}
        threading.Thread(target=_pull_worker, args=(model,), daemon=True, name="pull").start()
    h.ok(pull=dict(Pull.state))


@route("POST", r"/api/settings")
def r_settings(h):
    b = h.body()
    h.ok(settings=config.update(b.get("changes") or {}))


@route("GET", r"/api/jobs")
def r_jobs(h):
    h.ok(jobs=jobs.list())


@route("POST", r"/api/jobs/([\w]+)/cancel")
def r_job_cancel(h, jid):
    j = jobs.cancel(jid)
    h.ok(ok=bool(j))


@route("GET", r"/api/tts")
def r_tts(h):
    q = h.query
    if not tts.ready():
        raise HTTPError(404, "영어 음성이 아직 준비되지 않았어요.")
    try:
        data = tts.synth(q.get("t", ""), q.get("v") or config.get("tts_voice_k") or "af_heart",
                         float(q.get("s") or config.get("tts_rate") or 1.0))
    except ValueError as e:
        raise HTTPError(400, str(e))
    h._send(200, data, "audio/wav")


@route("POST", r"/api/tts/install")
def r_tts_install(h):
    j = pipeline.job_tts_install()
    h.ok(job=j.to_dict())


@route("POST", r"/api/stt/download")
def r_stt_download(h):
    name = h.body().get("name") or _stt_model()
    if name not in stt.REPOS:
        raise HTTPError(400, "모르는 모델이에요.")
    j = pipeline.job_download(name)
    h.ok(job=j.to_dict())


PICK_SCRIPT = r'''
import sys, os
import tkinter as tk
from tkinter import filedialog
kind = sys.argv[1]
init = sys.argv[2] if len(sys.argv) > 2 else ""
root = tk.Tk()
root.withdraw()
try:
    root.attributes("-topmost", True)
except Exception:
    pass
root.update()
if kind == "movie":
    types = [("영상·소리 파일", "*.mp4 *.mkv *.avi *.mov *.m4v *.webm *.wmv *.ts *.m2ts *.mpg *.mpeg *.flv *.mp3 *.m4a *.wav *.flac *.aac *.ogg"), ("모든 파일", "*.*")]
    title = "공부할 영화 파일을 고르세요"
else:
    types = [("자막 파일", "*.srt *.smi *.sami *.vtt *.ass *.ssa"), ("모든 파일", "*.*")]
    title = "자막 파일을 고르세요"
p = filedialog.askopenfilename(parent=root, title=title, filetypes=types, initialdir=(init if init and os.path.isdir(init) else None))
root.destroy()
sys.stdout.buffer.write((p or "").encode("utf-8"))
'''


@route("POST", r"/api/pick")
def r_pick(h):
    b = h.body()
    kind = b.get("kind") or "movie"
    init = b.get("dir") or ""
    if not init:
        vids = Path.home() / "Videos"
        init = str(vids if vids.exists() else Path.home())
    try:
        p = subprocess.run([sys.executable, "-c", PICK_SCRIPT, kind, init], capture_output=True, timeout=900,
                           creationflags=media.CREATE_NO_WINDOW)
    except Exception as e:  # noqa: BLE001
        raise HTTPError(500, f"파일 고르는 창을 열지 못했어요 ({e}). 아래 칸에 파일 위치를 붙여 넣어 주세요.")
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", errors="replace")[-300:]
        raise HTTPError(500, "파일 고르는 창을 열지 못했어요. 아래 칸에 파일 위치를 붙여 넣어 주세요. " + err)
    path = p.stdout.decode("utf-8", errors="replace").strip()
    h.ok(path=os.path.normpath(path) if path else "", cancelled=not path)


@route("POST", r"/api/open")
def r_open(h):
    b = h.body()
    what = b.get("what")
    if what == "project":
        target = project.folder(_pid(b.get("pid", "")))
    elif what == "sample":
        target = paths.SAMPLE_DIR
    elif what == "movie":
        target = Path(project.load(_pid(b.get("pid", "")))["movie"]).parent
    else:
        target = paths.DATA_DIR
    if os.name == "nt":
        os.startfile(str(target))  # noqa: S606
    h.ok(path=str(target))


# =====================================================================  routes: projects
def _sample_movie():
    if not paths.SAMPLE_DIR.exists():
        return None
    for f in sorted(paths.SAMPLE_DIR.iterdir()):
        if f.suffix.lower() in (".mp4", ".mkv", ".webm") and f.is_file():
            return f
    return None


@route("POST", r"/api/projects")
def r_project_new(h):
    b = h.body()
    path = (b.get("path") or "").strip().strip('"')
    if b.get("sample"):
        s = _sample_movie()
        if not s:
            raise HTTPError(404, "예제 영상이 없어요.")
        path = str(s)
    if not path:
        raise HTTPError(400, "영화 파일을 골라 주세요.")
    path = os.path.normpath(os.path.expanduser(path))
    if not os.path.isfile(path):
        raise HTTPError(400, f"파일을 찾을 수 없어요: {path}")
    existing = project.find_by_movie(path)
    p = existing or project.create(path, title=("예제 - 면접과 회의" if b.get("sample") else None))
    h.ok(project=project_summary(p), existing=bool(existing))


@route("GET", r"/api/projects/([^/]+)")
def r_project(h, raw):
    pid = _pid(raw)
    h.ok(project=project_summary(project.load(pid)))


@route("GET", r"/api/projects/([^/]+)/sources")
def r_sources(h, raw):
    pid = _pid(raw)
    h.ok(pipeline.scan(pid))


@route("POST", r"/api/projects/([^/]+)/sources/file")
def r_sources_file(h, raw):
    _pid(raw)
    path = os.path.normpath((h.body().get("path") or "").strip().strip('"'))
    if not os.path.isfile(path):
        raise HTTPError(400, "자막 파일을 찾을 수 없어요.")
    opts = pipeline.scan_file(path)
    if not opts:
        raise HTTPError(400, "이 파일에서 자막을 읽지 못했어요.")
    h.ok(options=opts)


@route("POST", r"/api/projects/([^/]+)/prepare")
def r_prepare(h, raw):
    pid = _pid(raw)
    b = h.body()
    en = b.get("en") or ""
    if not en:
        raise HTTPError(400, "영어 대사를 어디서 가져올지 골라 주세요.")
    j = pipeline.job_prepare(pid, en, b.get("ko") or "", b.get("model") or None)
    p = project.load(pid)
    if (p.get("media") or {}).get("state") in (None, "none", "error") and not jobs.running("media", pid):
        pipeline.job_media(pid, App.hevc_ok)
    if b.get("analyze", True):
        _chain_analysis(pid, j, b.get("depth") or config.get("analysis_depth"))
    h.ok(job=j.to_dict())


def _chain_analysis(pid, prep_job, depth):
    def wait():
        while prep_job.state == "running":
            time.sleep(1.0)
        if prep_job.state == "done":
            try:
                pipeline.job_analyze(pid, depth)
            except Exception as e:  # noqa: BLE001
                log.warning("analysis chain failed: %s", e)
    threading.Thread(target=wait, daemon=True).start()


@route("POST", r"/api/projects/([^/]+)/media")
def r_media_job(h, raw):
    pid = _pid(raw)
    b = h.body()
    if "hevc" in b:
        App.hevc_ok = bool(b["hevc"])
    force = b.get("plan") if b.get("plan") in ("remux", "transcode", "audio") else None
    if force:
        project.update(pid, media={"state": "none"})
    j = pipeline.job_media(pid, App.hevc_ok, force)
    h.ok(job=j.to_dict())


@route("POST", r"/api/projects/([^/]+)/analyze")
def r_analyze(h, raw):
    pid = _pid(raw)
    b = h.body()
    depth = b.get("depth") or config.get("analysis_depth")
    if depth not in analysis.DEPTH:
        depth = "normal"
    j = pipeline.job_analyze(pid, depth, bool(b.get("redo")))
    h.ok(job=j.to_dict())


@route("POST", r"/api/projects/([^/]+)/examples")
def r_examples_job(h, raw):
    pid = _pid(raw)
    j = pipeline.job_examples(pid)
    h.ok(job=j.to_dict())


@route("POST", r"/api/projects/([^/]+)/delete")
def r_delete(h, raw):
    pid = _pid(raw)
    b = h.body()
    running = jobs.running(pid=pid)
    for j in running:
        jobs.cancel(j.id)
    if b.get("media_only"):
        md = project.folder(pid) / "media"
        removed = 0
        for f in list(md.glob("learn*")) + list(md.glob("audio16k.wav")):
            try:
                removed += f.stat().st_size
                f.unlink()
            except OSError:
                pass
        p = project.load(pid)
        if (p.get("media") or {}).get("plan") != "direct":
            project.update(pid, media={"plan": "", "file": "", "state": "none", "audio_only": False})
        h.ok(freed=removed)
        return
    # work on this movie (subtitles, speech recognition, video copy) may still hold its files: let it stop
    end = time.time() + 15
    while time.time() < end and any(j.state == "running" for j in running):
        time.sleep(0.2)
    p = project.load(pid)
    files = _movie_files(p) if b.get("trash_movie") else []
    cards = review.drop_project(pid)
    clean = project.delete(pid)
    trashed, failed = [], []
    for f in files:
        try:
            trash.send(f)
            trashed.append(f.name)
        except OSError as e:
            failed.append(f"{f.name}: {e}")
    log.info("deleted movie %s (cards %d, clean %s, trashed %s, failed %s)", pid, cards, clean, trashed, failed)
    h.ok(title=p.get("title", ""), cards=cards, clean=clean, trashed=trashed, trash_failed=failed)


def _inside(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def _movie_files(p):
    """The movie file and its same-name subtitle files (Movie.srt, Movie.en.srt), when they may go to the
    Recycle Bin. Files of the tool itself (the sample scene) are never offered."""
    m = Path(p.get("movie") or "")
    if not p.get("movie") or not m.is_file() or _inside(m, paths.TOOL_DIR):
        return []
    stem = m.stem.lower()
    out = [m]
    try:
        out += sorted((f for f in m.parent.iterdir()
                       if f.is_file() and f != m and f.suffix.lower() in subtitles.SUB_EXTS
                       and (f.stem.lower() == stem or f.stem.lower().startswith(stem + "."))),
                      key=lambda f: f.name.lower())
    except OSError:
        pass
    return out


@route("GET", r"/api/projects/([^/]+)/delete-info")
def r_delete_info(h, raw):
    pid = _pid(raw)
    p = project.load(pid)
    files = _movie_files(p)
    recs = project.folder(pid) / "녹음"
    copies = [f for f in (project.folder(pid) / "media").glob("learn*") if f.is_file()]
    h.ok(title=p.get("title", ""), study_bytes=project.size(pid), cards=review.count_project(pid),
         playback_bytes=sum(f.stat().st_size for f in copies),
         recordings=sum(1 for f in recs.iterdir() if f.is_file()) if recs.is_dir() else 0,
         studied=len((project.progress(pid) or {}).get("lines", {}) or {}),
         jobs=len(jobs.running(pid=pid)),
         movie=str(files[0]) if files else "", movie_bytes=files[0].stat().st_size if files else 0,
         subs=[f.name for f in files[1:]], sample=_inside(p.get("movie") or "", paths.TOOL_DIR))


# ---------------------------------------------------------------- subtitles burned into the picture
def _mask_clean(m):
    out = {}
    if "on" in m:
        out["on"] = bool(m["on"])
    if "style" in m and m["style"] in ("solid", "blur"):
        out["style"] = m["style"]
    try:
        if "height" in m:
            out["height"] = round(min(0.6, max(0.02, float(m["height"]))), 4)
        if "top" in m:
            out["top"] = round(min(0.98, max(0.0, float(m["top"]))), 4)
    except (TypeError, ValueError):
        raise HTTPError(400, "가림막 위치가 올바르지 않아요.")
    if "top" in out and "height" in out and out["top"] + out["height"] > 1:
        out["top"] = round(1 - out["height"], 4)
    return out


@route("POST", r"/api/projects/([^/]+)/mask")
def r_mask(h, raw):
    pid = _pid(raw)
    project.update(pid, mask=_mask_clean(h.body().get("mask") or {}))
    h.ok(mask=project.load(pid).get("mask") or {})


def _picture_file(p):
    """The file to look at for burned-in subtitles: the light playback copy if there is one, else the movie."""
    m = p.get("media") or {}
    if m.get("audio_only"):
        return None
    for f in (m.get("file") if m.get("state") == "ready" else None, p.get("movie")):
        if f and os.path.isfile(f):
            return f
    return None


@route("POST", r"/api/projects/([^/]+)/mask/detect")
def r_mask_detect(h, raw):
    pid = _pid(raw)
    p = project.load(pid)
    src = _picture_file(p)
    if not src:
        raise HTTPError(409, "화면이 있는 영상 파일을 찾을 수 없어요.")
    if not media.ffmpeg_exe():
        raise HTTPError(409, "영상 도구(ffmpeg)를 찾을 수 없어요.")
    t0 = time.time()
    r = burnsubs.detect(src, project.lines(pid), float(p.get("offset") or 0.0), p.get("duration"))
    log.info("burned-in subtitles: %s (%.1fs)", r, time.time() - t0)
    if r.get("found"):
        project.update(pid, mask={"on": True, "top": r["top"], "height": r["height"], "auto": True})
    h.ok(found=bool(r.get("found")), reason=r.get("reason", ""), mask=project.load(pid).get("mask") or {},
         suggest={"top": r["top"], "height": r["height"]})


@route("POST", r"/api/projects/([^/]+)/offset")
def r_offset(h, raw):
    pid = _pid(raw)
    off = float(h.body().get("offset") or 0.0)
    off = max(-30.0, min(30.0, off))
    project.update(pid, offset=round(off, 3))
    h.ok(offset=off)


@route("GET", r"/api/projects/([^/]+)/lines")
def r_lines(h, raw):
    pid = _pid(raw)
    p = project.load(pid)
    off = float(p.get("offset") or 0.0)
    lines = project.lines(pid)
    lp = project.progress(pid).get("lines", {})
    stars = {k for k in review.keys() if k.startswith(pid + "|line|")}
    out = [compact(l, off, lp, line_card_key(pid, l["id"]) in stars) for l in lines]
    h.ok(lines=out, offset=off, project=project_summary(p))


def _line(pid, lid):
    lines = project.lines(pid)
    lid = int(lid)
    if not 0 <= lid < len(lines):
        raise KeyError(f"line {lid}")
    return lines, lines[lid]


@route("GET", r"/api/projects/([^/]+)/lines/(\d+)")
def r_line(h, raw, lid):
    pid = _pid(raw)
    _, line = _line(pid, lid)
    ex = project.cache(pid, "설명").get(str(line["id"]))
    exm = None
    ai = line.get("ai") or {}
    if ai.get("expr"):
        exm = project.cache(pid, "예문").get(f"e{line['id']}")
    h.ok(notes=speech_rules.speech_notes(line["text"], limit=6), explain=ex, example=exm,
         tags_ko=[CATEGORIES.get(t, t) for t in line.get("tags", [])])


@route("POST", r"/api/projects/([^/]+)/lines/(\d+)/explain")
def r_line_explain(h, raw, lid):
    pid = _pid(raw)
    _, line = _line(pid, lid)
    if not h.body().get("refresh"):
        cached = project.cache(pid, "설명").get(str(line["id"]))
        if cached:
            h.ok(explain=cached)
            return
    ex = analysis.explain_line(line)
    project.update_cache(pid, "설명", lambda d: d.__setitem__(str(line["id"]), ex))
    h.ok(explain=ex)


@route("POST", r"/api/projects/([^/]+)/lines/(\d+)/dictation")
def r_dictation(h, raw, lid):
    pid = _pid(raw)
    _, line = _line(pid, lid)
    typed = (h.body().get("text") or "").strip()
    if not typed:
        raise HTTPError(400, "들은 문장을 적어 주세요.")
    res = textutil.align(line["text"], typed)
    notes = speech_rules.speech_notes(line["text"], limit=6)
    missed = [(w["a"], w["b"]) for w in res["ref"] if w["s"] != "hit"]
    missed_words = {w["w"].lower() for w in res["ref"] if w["s"] != "hit"}
    for n in notes:
        if n["a"] >= 0:
            n["hit"] = any(not (b <= n["a"] or a >= n["b"]) for a, b in missed)
        else:
            n["hit"] = any(w in missed_words for w in n["say"].split(", "))
    _record(pid, line, "d", [time.time(), res["score"]])
    if res["score"] < 0.8:
        review.add(line_card_key(pid, line["id"]), "line", line["text"], line.get("ko", ""), pid, line["id"],
                   note="받아쓰기")
    project.log_activity(pid, "dict")
    h.ok(result=res, notes=notes)


def _record(pid, line, key, entry):
    def fn(pr):
        d = pr.setdefault("lines", {}).setdefault(str(line["id"]), {})
        d.setdefault(key, []).append(entry)
        d[key] = d[key][-20:]
    project.update_progress(pid, fn)


@route("POST", r"/api/projects/([^/]+)/lines/(\d+)/speak")
def r_speak(h, raw, lid):
    pid = _pid(raw)
    _, line = _line(pid, lid)
    name = _need_stt()
    f = _save_upload(h, project.rec_dir(pid), f"{line['id']:04d}")
    r = stt.transcribe_clip(f, name)
    url = "/rec/" + urllib.parse.quote(pid) + "/" + urllib.parse.quote(f.name)
    if r["no_speech"]:
        h.ok(no_speech=True, rec=url)
        return
    al = textutil.align(line["text"], r["text"])
    w = line.get("words")
    ref_dur = (w[-1][2] - w[0][1]) if w else max(0.5, (line["end"] - line["start"]) * 0.85)
    ww = r["words"]
    my_dur = (ww[-1][2] - ww[0][1]) if ww else r["duration"]
    speed = round(my_dur / max(0.3, ref_dur), 2)
    unclear = [x[0] for x in ww if x[3] < 0.5][:6]
    _record(pid, line, "s", [time.time(), al["score"], speed])
    if al["score"] < 0.75:
        review.add(line_card_key(pid, line["id"]), "line", line["text"], line.get("ko", ""), pid, line["id"],
                   note="따라 말하기")
    project.log_activity(pid, "speak")
    h.ok(text=r["text"], align=al, speed=speed, unclear=unclear, rec=url, secs=r.get("secs"))


@route("POST", r"/api/projects/([^/]+)/lines/(\d+)/star")
def r_star(h, raw, lid):
    pid = _pid(raw)
    _, line = _line(pid, lid)
    on = bool(h.body().get("on"))
    key = line_card_key(pid, line["id"])
    if on:
        review.add(key, "line", line["text"], line.get("ko", ""), pid, line["id"], failed=False, note="내가 고른 문장")
    else:
        review.remove(key)
    h.ok(on=on)


@route("GET", r"/rec/([^/]+)/([^/]+)")
def r_rec(h, raw, name):
    pid = _pid(raw)
    f = project.rec_dir(pid) / name
    if "/" in name or "\\" in name or not f.is_file():
        raise HTTPError(404, "녹음이 없어요.")
    h.send_file(f)


@route("GET", r"/media/([^/]+)")
def r_media(h, raw):
    pid = _pid(raw)
    p = project.load(pid)
    m = p.get("media") or {}
    f = m.get("file")
    if not f or not os.path.isfile(f):
        raise HTTPError(404, "재생할 파일이 아직 없어요.")
    h.send_file(f)


# ---------------------------------------------------------------- expressions
def _exprs(pid):
    lines = project.lines(pid)
    return lines, analysis.expressions(lines)


@route("GET", r"/api/projects/([^/]+)/expressions")
def r_expressions(h, raw):
    pid = _pid(raw)
    p = project.load(pid)
    off = float(p.get("offset") or 0.0)
    lines, items = _exprs(pid)
    exs = project.cache(pid, "예문")
    keys = review.keys()
    tries = project.progress(pid).get("exprs", {})
    out = []
    for e in items:
        ln = lines[e["line"]]
        cs, ce = clip_bounds(ln, off)
        out.append({**e, "line_text": ln["text"], "line_ko": ln.get("ko", ""), "cs": cs, "ce": ce,
                    "example": exs.get(e["id"]), "st": expr_card_key(pid, e["id"]) in keys,
                    "tries": len(tries.get(e["id"], []))})
    h.ok(items=out, categories=CATEGORIES, analysis=p.get("analysis"))


def _expr(pid, eid):
    lines, items = _exprs(pid)
    for e in items:
        if e["id"] == eid:
            return lines, e
    raise KeyError(eid)


@route("POST", r"/api/projects/([^/]+)/expressions/(e\d+)/example")
def r_expr_example(h, raw, eid):
    pid = _pid(raw)
    lines, e = _expr(pid, eid)
    ex = analysis.make_example(e["text"], lines[e["line"]]["text"])
    project.update_cache(pid, "예문", lambda d: d.__setitem__(eid, ex))
    h.ok(example=ex)


def _check_expr(pid, eid, said):
    lines, e = _expr(pid, eid)
    res = analysis.check_sentence(e["text"], e.get("ko", ""), said)

    def fn(pr):
        lst = pr.setdefault("exprs", {}).setdefault(eid, [])
        lst.append([time.time(), bool(res["natural"] and res["used_expr"])])
        pr["exprs"][eid] = lst[-20:]
    project.update_progress(pid, fn)
    project.log_activity(pid, "expr")
    return res


@route("POST", r"/api/projects/([^/]+)/expressions/(e\d+)/check")
def r_expr_check(h, raw, eid):
    pid = _pid(raw)
    said = (h.body().get("text") or "").strip()
    if not said:
        raise HTTPError(400, "문장을 적거나 말해 주세요.")
    h.ok(check=_check_expr(pid, eid, said), text=said)


@route("POST", r"/api/projects/([^/]+)/expressions/(e\d+)/speak")
def r_expr_speak(h, raw, eid):
    pid = _pid(raw)
    name = _need_stt()
    f = _save_upload(h, project.rec_dir(pid), eid)
    r = stt.transcribe_clip(f, name)
    url = "/rec/" + urllib.parse.quote(pid) + "/" + urllib.parse.quote(f.name)
    if r["no_speech"]:
        h.ok(no_speech=True, rec=url)
        return
    h.ok(check=_check_expr(pid, eid, r["text"]), text=r["text"], rec=url)


@route("POST", r"/api/projects/([^/]+)/expressions/(e\d+)/star")
def r_expr_star(h, raw, eid):
    pid = _pid(raw)
    lines, e = _expr(pid, eid)
    on = bool(h.body().get("on"))
    key = expr_card_key(pid, eid)
    if on:
        ex = project.cache(pid, "예문").get(eid) or {}
        review.add(key, "expr", e["text"], e.get("ko", ""), pid, eid, failed=False,
                   note=ex.get("example_en", ""))
    else:
        review.remove(key)
    h.ok(on=on)


# ---------------------------------------------------------------- speech (generic)
@route("POST", r"/api/stt")
def r_stt(h):
    name = _need_stt()
    f = _save_upload(h, paths.ROLEPLAY_DIR / "녹음", re.sub(r"[^\w-]", "", h.query.get("purpose", "talk"))[:20] or "talk")
    try:
        r = stt.transcribe_clip(f, name)
    finally:
        try:
            f.unlink()  # nothing plays these back, so the recording is not kept
        except OSError:
            pass
    h.ok(r)


# ---------------------------------------------------------------- saved recordings (privacy)
AUDIO_EXT = {".webm", ".ogg", ".wav", ".mp4", ".m4a", ".mp3"}


def _recording_files():
    dirs = [project.folder(p["id"]) / "녹음" for p in project.list_all()] + [paths.ROLEPLAY_DIR / "녹음"]
    out = []
    for d in dirs:
        if d.is_dir():
            out += [f for f in d.iterdir() if f.is_file() and f.suffix.lower() in AUDIO_EXT]
    return out


@route("GET", r"/api/recordings")
def r_recordings(h):
    fs = _recording_files()
    h.ok(count=len(fs), bytes=sum(f.stat().st_size for f in fs))


@route("POST", r"/api/recordings/delete")
def r_recordings_delete(h):
    n = 0
    for f in _recording_files():
        try:
            f.unlink()
            n += 1
        except OSError:
            pass
    left = _recording_files()
    log.info("deleted %d recordings (%d left)", n, len(left))
    h.ok(deleted=n, count=len(left), bytes=sum(f.stat().st_size for f in left))


# ---------------------------------------------------------------- role-play
@route("GET", r"/api/roleplay")
def r_rp_history(h):
    h.ok(sessions=roleplay.history(), scenarios=roleplay.scenario_list())


@route("POST", r"/api/roleplay/start")
def r_rp_start(h):
    b = h.body()
    exprs = []
    pid = b.get("project") or None
    if pid:
        try:
            _, items = _exprs(_pid(pid))
            items.sort(key=lambda e: (-e.get("useful", 0), e["line"]))
            exprs = [e["text"] for e in items[:12]]
        except KeyError:
            pid = None
    prof = b.get("profile") or config.get("profile")
    if b.get("profile"):
        config.update({"profile": b["profile"]})
    if b.get("level"):
        config.update({"level": b["level"]})
    sess = roleplay.start(b.get("scenario") or "interview_basic", b.get("level") or "normal",
                          b.get("n") or 5, prof, pid, exprs, b.get("custom") or "")
    _prefetch_last(sess)
    h.ok(session=sess)


def _prefetch_last(sess):
    t = next((x for x in reversed(sess.get("turns", [])) if x["role"] == "ai"), None)
    if t and config.get("tts_engine") != "browser":
        tts.prefetch(t["text"], sess.get("voice") or "af_heart", sess.get("rate") or 0.95)


@route("GET", r"/api/roleplay/([\w\-]+)")
def r_rp_get(h, sid):
    s = roleplay.load(sid)
    if not s:
        raise KeyError(sid)
    h.ok(session=s)


@route("POST", r"/api/roleplay/([\w\-]+)/answer")
def r_rp_answer(h, sid):
    s = roleplay.load(sid)
    if not s:
        raise KeyError(sid)
    if s.get("done"):
        raise HTTPError(400, "이미 끝난 연습이에요.")
    text = (h.body().get("text") or "").strip()
    if not text:
        raise HTTPError(400, "답변을 말하거나 적어 주세요.")
    s = roleplay.answer(s, text)
    _prefetch_last(s)
    h.ok(session=s)


@route("POST", r"/api/roleplay/([\w\-]+)/delete")
def r_rp_delete(h, sid):
    if not roleplay.delete(sid):
        raise KeyError(sid)
    h.ok(sessions=roleplay.history())


@route("POST", r"/api/roleplay/([\w\-]+)/summary")
def r_rp_summary(h, sid):
    s = roleplay.load(sid)
    if not s:
        raise KeyError(sid)
    s = roleplay.summarize(s)
    h.ok(session=s)


# ---------------------------------------------------------------- review
@route("GET", r"/api/review")
def r_review(h):
    cards = review.due(int(h.query.get("limit") or 40))
    out = []
    cache_lines = {}
    for c in cards:
        c = dict(c)
        if c["type"] in ("line", "expr") and c.get("pid"):
            pid = c["pid"]
            try:
                if pid not in cache_lines:
                    p = project.load(pid)
                    cache_lines[pid] = (project.lines(pid), float(p.get("offset") or 0.0), p.get("title"),
                                        (p.get("media") or {}).get("state"))
                lines, off, title, mstate = cache_lines[pid]
                lid = c["ref"] if c["type"] == "line" else int(str(c["ref"])[1:])
                if 0 <= lid < len(lines):
                    c["cs"], c["ce"] = clip_bounds(lines[lid], off)
                    c["title"] = title
                    c["media_ok"] = mstate in ("ready", "audio")
                    if c["type"] == "expr":
                        c["line_text"] = lines[lid]["text"]
            except KeyError:
                pass
        out.append(c)
    h.ok(cards=out, counts=review.counts())


@route("POST", r"/api/review/grade")
def r_review_grade(h):
    b = h.body()
    c = review.grade(b.get("key"), b.get("grade") or "good")
    if c and c.get("pid"):
        try:
            project.log_activity(c["pid"], "review")
        except KeyError:
            pass
    h.ok(card=c, counts=review.counts())


@route("POST", r"/api/review/add")
def r_review_add(h):
    b = h.body()
    en = (b.get("en") or "").strip()
    if not en:
        raise HTTPError(400, "추가할 문장이 없어요.")
    key = b.get("key") or ("phrase|" + re.sub(r"[^a-z0-9]+", "-", en.lower())[:80])
    c = review.add(key, b.get("type") or "phrase", en, b.get("ko") or "", b.get("pid"), b.get("ref"),
                   failed=False, note=b.get("note") or "")
    h.ok(card=c, counts=review.counts())


@route("POST", r"/api/review/remove")
def r_review_remove(h):
    review.remove(h.body().get("key") or "")
    h.ok(counts=review.counts())


# ---------------------------------------------------------------- self check
@route("POST", r"/api/check")
def r_check(h):
    out = []

    def add(name, ok, detail):
        out.append({"name": name, "ok": ok, "detail": detail})

    exe = media.ffmpeg_exe()
    add("영상 도구 (ffmpeg)", bool(exe), exe or "없음")
    st = ollama.status()
    if st.get("ok"):
        add("Ollama 연결", True, f"버전 {st['version']}, 모델 {len(st['models'])}개")
        try:
            t0 = time.time()
            data = ollama.chat_json([{"role": "user", "content": 'Return JSON {"ok": true, "word": "hello"}'}],
                                    {"type": "object", "properties": {"ok": {"type": "boolean"}, "word": {"type": "string"}},
                                     "required": ["ok", "word"]}, temperature=0, num_predict=40)
            add("AI 모델 응답", bool(data.get("ok")), f"{st['model']} — {time.time() - t0:.1f}초")
        except Exception as e:  # noqa: BLE001
            add("AI 모델 응답", False, str(e))
    else:
        add("Ollama 연결", False, st.get("error", ""))
    if stt.available():
        name = _stt_model()
        if stt.is_ready(name):
            sample = Path(__file__).resolve().parent / "assets" / "check.wav"
            if sample.is_file():
                try:
                    r = stt.transcribe_clip(sample, name)
                    add("음성 인식", bool(r["text"]), f"{name}: \"{r['text'][:60]}\" ({r.get('secs')}초)")
                except Exception as e:  # noqa: BLE001
                    add("음성 인식", False, f"{type(e).__name__}: {e}")
            else:
                try:
                    stt.get_model(name, "speech")
                    add("음성 인식", True, f"{name} 모델 불러오기 성공")
                except Exception as e:  # noqa: BLE001
                    add("음성 인식", False, f"{type(e).__name__}: {e}")
        else:
            add("음성 인식", False, f"{name} 모델을 아직 내려받지 않았어요")
    else:
        add("음성 인식", False, stt.import_error())
    if tts.ready():
        try:
            t0 = time.time()
            tts.synth("Nice to meet you.", config.get("tts_voice_k") or "af_heart", 1.0)
            add("영어 음성 (Kokoro)", True, f"{time.time() - t0:.1f}초")
        except Exception as e:  # noqa: BLE001
            add("영어 음성 (Kokoro)", False, f"{type(e).__name__}: {e}")
    else:
        add("영어 음성 (Kokoro)", False, "아직 설치하지 않았어요" if not tts.status()["error"] else tts.status()["error"])
    h.ok(checks=out)


# =====================================================================  launch
def find_browser():
    cands = []
    if os.name == "nt":
        for env in ("ProgramFiles(x86)", "ProgramFiles", "LocalAppData"):
            base = os.environ.get(env)
            if base:
                cands.append(Path(base) / "Microsoft/Edge/Application/msedge.exe")
        for env in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData"):
            base = os.environ.get(env)
            if base:
                cands.append(Path(base) / "Google/Chrome/Application/chrome.exe")
    for c in cands:
        if c.is_file():
            return str(c)
    return None


def open_window(url):
    b = find_browser()
    if b:
        try:
            # The normal Edge profile is used on purpose: a separate fresh profile makes Edge show
            # sign-in / sync prompts over the app.
            proc = subprocess.Popen([b, f"--app={url}", "--no-first-run", "--no-default-browser-check",
                                     "--start-maximized"])
            return proc
        except OSError as e:
            log.warning("browser launch failed: %s", e)
    webbrowser.open(url)
    return None


def already_running(port):
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8")).get("app") == APP_ID
    except Exception:
        return False


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR would let two programs share the port, so only use it elsewhere.
    allow_reuse_address = os.name != "nt"


def watchdog(proc):
    """Stop when the app window was closed (it sends a goodbye) and no page pings again.

    The Edge process itself is not watched: with the normal profile it hands the window
    over to an already running Edge and exits at once."""
    while not App.stopping:
        time.sleep(1.0)
        t = App.bye_at
        if t and time.time() - t > 15 and App.last_ping < t:
            log.info("app window closed; stopping")
            App.stopping = True
            threading.Thread(target=App.server.shutdown, daemon=True).start()
            return


def serve(open_ui=True):
    paths.ensure_dirs()
    threading.Thread(target=project.sweep_deleted, daemon=True, name="sweep").start()
    port = int(config.get("port") or 8765)
    takeover = "--takeover" in sys.argv
    if not takeover and already_running(port):
        print("이미 실행 중이에요. 창을 다시 열게요.")
        open_window(f"http://127.0.0.1:{port}/")
        return 0
    if not takeover:
        # Ollama installed, running and with a model? Ask before installing anything.
        from . import prereq
        prereq.ensure_ollama()
    srv = None
    # Keep the same port when possible: the window remembers microphone permission per address.
    for attempt in range(40 if takeover else 12):
        try:
            srv = Server(("127.0.0.1", port), Handler)
            break
        except OSError:
            if not takeover and already_running(port):
                open_window(f"http://127.0.0.1:{port}/")
                return 0
            time.sleep(0.5)
    if srv is None:
        for p in range(port + 1, port + 15):
            try:
                srv = Server(("127.0.0.1", p), Handler)
                port = p
                break
            except OSError:
                continue
    if srv is None:
        print("프로그램 창에 쓸 포트를 열지 못했어요.")
        return 1
    App.server = srv
    App.port = port
    url = f"http://127.0.0.1:{port}/"
    print(f"\n  로컬 AI 영어학습도구 {VERSION}  —  {url}")
    print("  프로그램 창을 닫으면 자동으로 끝나요. (이 검은 창을 닫아도 끝나요)\n")
    proc = open_window(url) if open_ui else None
    threading.Thread(target=watchdog, args=(proc,), daemon=True).start()
    # first run: fetch the speech model and the English voice in the background
    if stt.available() and not stt.is_ready(_stt_model()):
        try:
            pipeline.job_download(_stt_model())
        except Exception as e:  # noqa: BLE001
            log.warning("auto download failed: %s", e)
    if config.get("tts_engine") == "kokoro" and not tts.ready():
        try:
            pipeline.job_tts_install()
        except Exception as e:  # noqa: BLE001
            log.warning("voice install failed: %s", e)
    elif config.get("tts_engine") == "kokoro":
        threading.Thread(target=tts.warm, daemon=True).start()
    # an earlier version opened the window with its own Edge profile; remove that copy
    if paths.EDGE_PROFILE_DIR.exists():
        import shutil
        shutil.rmtree(paths.EDGE_PROFILE_DIR, ignore_errors=True)
    try:
        srv.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        App.stopping = True
        tts.shutdown()
        srv.server_close()
    return 0
