"""Per-movie study folders under 학습 기록/<영화 제목>/."""
import os
import re
import shutil
import time
from pathlib import Path

from . import paths
from .storage import file_lock, read_json, update_json, write_json

DELETING = ".지우는 중"  # marks a folder whose deletion has to be finished on the next start


def _safe(name):
    s = re.sub(r'[\\/:*?"<>|%#&\x00-\x1f]+', " ", name).strip().rstrip(". ")
    s = re.sub(r"\s+", " ", s)
    return (s[:60].strip() or "영화")


def valid_id(pid):
    return bool(pid) and "/" not in pid and "\\" not in pid and ".." not in pid and not pid.startswith("_")


def folder(pid) -> Path:
    if not valid_id(pid):
        raise KeyError(pid)
    d = paths.PROJECTS_DIR / pid
    if not (d / "project.json").exists():
        raise KeyError(pid)
    return d


def relocate(s):
    """A path saved before the tool folder was moved or renamed (e.g. its parent folder got a new name):
    the same place inside the current tool folder, if something is there. Other paths stay as they are."""
    if not s or os.path.exists(s):
        return s
    parts = [x for x in re.split(r"[\\/]+", s) if x]
    name = paths.TOOL_DIR.name
    if name not in parts:
        return s
    rest = parts[len(parts) - parts[::-1].index(name):]
    cand = paths.TOOL_DIR.joinpath(*rest) if rest else None
    return str(cand) if cand and cand.exists() else s


def _fix_paths(p):
    """Point saved paths at the moved tool folder. Returns the changes to save, or None."""
    ch = {}
    m = relocate(p.get("movie"))
    if m != p.get("movie"):
        ch["movie"] = m
    f = relocate((p.get("media") or {}).get("file"))
    if f != (p.get("media") or {}).get("file"):
        ch["media"] = {"file": f}
    prep = {}
    for k in ("en", "ko"):
        v = (p.get("prep") or {}).get(k)
        if isinstance(v, str) and v.startswith("file|"):
            path, _, ti = v[5:].rpartition("|")
            new = relocate(path)
            if new != path:
                prep[k] = f"file|{new}|{ti}"
    if prep:
        ch["prep"] = prep
    return ch or None


def _checked(p):
    ch = _fix_paths(p)
    if ch:
        try:
            p = update(p["id"], **ch)
        except KeyError:
            pass
    return p


def list_all():
    out = []
    if not paths.PROJECTS_DIR.exists():
        return out
    for d in paths.PROJECTS_DIR.iterdir():
        if d.is_dir() and not d.name.startswith("_") and (d / "project.json").exists():
            p = read_json(d / "project.json")
            if p:
                out.append(_checked(p))
    out.sort(key=lambda p: -(p.get("updated") or 0))
    return out


def find_by_movie(movie_path):
    mp = str(Path(movie_path))
    for p in list_all():
        if p.get("movie") == mp:
            return p
    return None


def create(movie_path, title=None):
    movie_path = Path(movie_path)
    title = title or movie_path.stem
    base = _safe(title)
    d = paths.PROJECTS_DIR / base
    k = 2
    while d.exists():
        d = paths.PROJECTS_DIR / f"{base} ({k})"
        k += 1
    d.mkdir(parents=True)
    proj = {
        "id": d.name, "title": title, "movie": str(movie_path), "created": time.time(), "updated": time.time(),
        "duration": 0.0, "probe": None, "audio_stream": None,
        "en": None, "ko": None, "offset": 0.0,
        "media": {"plan": "", "file": "", "state": "none", "audio_only": False},
        "lines_ready": False, "line_count": 0,
        "analysis": {"state": "none", "done": 0, "total": 0, "depth": ""},
    }
    save(proj)
    return proj


def load(pid):
    p = read_json(folder(pid) / "project.json")
    if not p:
        raise KeyError(pid)
    return _checked(p)


def save(proj):
    proj["updated"] = time.time()
    write_json(paths.PROJECTS_DIR / proj["id"] / "project.json", proj)


def update(pid, **changes):
    def fn(p):
        if not p:   # deleted meanwhile: never bring the folder back with half a project.json
            raise KeyError(pid)
        for k, v in changes.items():
            if isinstance(v, dict) and isinstance(p.get(k), dict):
                p[k].update(v)
            else:
                p[k] = v
        p["updated"] = time.time()
    return update_json(folder(pid) / "project.json", fn, {})


def delete(pid):
    """Remove a movie's study folder. project.json goes first, so the movie leaves the list at once;
    files that are still open (a video being sent to the window) are retried for a moment,
    and anything left is removed on the next start. Returns True when nothing is left."""
    d = folder(pid)
    try:
        (d / DELETING).write_text("", encoding="utf-8")
    except OSError:
        pass
    with file_lock(d / "project.json"):
        (d / "project.json").unlink(missing_ok=True)
    for _ in range(24):
        shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            return True
        time.sleep(0.25)
    return False


def sweep_deleted():
    """Finish deletions that could not complete because a file was in use."""
    if not paths.PROJECTS_DIR.exists():
        return
    for d in paths.PROJECTS_DIR.iterdir():
        if d.is_dir() and (d / DELETING).exists() and not (d / "project.json").exists():
            shutil.rmtree(d, ignore_errors=True)


def size(pid):
    total = 0
    for f in folder(pid).rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            pass
    return total


def lines(pid):
    return read_json(folder(pid) / "lines.json", []) or []


def save_lines(pid, data):
    write_json(folder(pid) / "lines.json", data)


def progress(pid):
    return read_json(folder(pid) / "progress.json", {"lines": {}, "exprs": {}, "days": {}}) or {"lines": {}, "exprs": {}, "days": {}}


def save_progress(pid, data):
    write_json(folder(pid) / "progress.json", data)


def update_progress(pid, fn):
    return update_json(folder(pid) / "progress.json", fn, {"lines": {}, "exprs": {}, "days": {}})


def cache(pid, name):
    return read_json(folder(pid) / f"{name}.json", {}) or {}


def update_cache(pid, name, fn):
    return update_json(folder(pid) / f"{name}.json", fn, {})


def media_dir(pid) -> Path:
    d = folder(pid) / "media"
    d.mkdir(exist_ok=True)
    return d


def rec_dir(pid) -> Path:
    d = folder(pid) / "녹음"
    d.mkdir(exist_ok=True)
    return d


def today():
    return time.strftime("%Y-%m-%d")


def log_activity(pid, kind):
    def fn(pr):
        day = pr.setdefault("days", {}).setdefault(today(), {})
        day[kind] = day.get(kind, 0) + 1
    update_progress(pid, fn)
