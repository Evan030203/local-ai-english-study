"""Review cards with simple spaced repetition (Leitner boxes)."""
import datetime as dt
import threading
import time

from . import paths
from .storage import read_json, write_json

INTERVALS = {1: 1, 2: 2, 3: 4, 4: 8, 5: 16, 6: 30}
_lock = threading.Lock()


def _today():
    return dt.date.today()


def _load():
    return read_json(paths.REVIEW_FILE, {"cards": {}}) or {"cards": {}}


def _save(data):
    write_json(paths.REVIEW_FILE, data)


def add(key, kind, en, ko="", pid=None, ref=None, failed=True, note=""):
    with _lock:
        data = _load()
        c = data["cards"].get(key)
        if c is None:
            c = {"key": key, "type": kind, "pid": pid, "ref": ref, "en": en, "ko": ko, "note": note,
                 "box": 1, "due": _today().isoformat(), "added": time.time(), "reviews": 0, "last": None}
            data["cards"][key] = c
        else:
            c["en"], c["ko"] = en or c["en"], ko or c.get("ko", "")
            if failed:
                c["box"] = 1
                c["due"] = min(c["due"], (_today() + dt.timedelta(days=1)).isoformat())
        _save(data)
        return c


def remove(key):
    with _lock:
        data = _load()
        data["cards"].pop(key, None)
        _save(data)


def has(key):
    return key in _load()["cards"]


def grade(key, g):
    """g: again | hard | good"""
    with _lock:
        data = _load()
        c = data["cards"].get(key)
        if not c:
            return None
        box = int(c.get("box", 1))
        if g == "again":
            box = 1
            days = 0
        elif g == "hard":
            days = max(1, INTERVALS.get(box, 1) // 2)
        else:
            box = min(6, box + 1)
            days = INTERVALS[box]
        c["box"] = box
        c["due"] = (_today() + dt.timedelta(days=days)).isoformat()
        c["reviews"] = c.get("reviews", 0) + 1
        c["last"] = time.time()
        _save(data)
        return c


def due(limit=40):
    today = _today().isoformat()
    cards = [c for c in _load()["cards"].values() if c.get("due", today) <= today]
    cards.sort(key=lambda c: (c["due"], c.get("box", 1), c.get("added", 0)))
    return cards[:limit]


def counts():
    today = _today().isoformat()
    cards = list(_load()["cards"].values())
    return {"total": len(cards), "due": sum(1 for c in cards if c.get("due", today) <= today),
            "learned": sum(1 for c in cards if c.get("box", 1) >= 4)}


def keys():
    return set(_load()["cards"].keys())


def count_project(pid):
    return sum(1 for c in _load()["cards"].values() if c.get("pid") == pid)


def drop_project(pid):
    with _lock:
        data = _load()
        before = len(data["cards"])
        data["cards"] = {k: v for k, v in data["cards"].items() if v.get("pid") != pid}
        if len(data["cards"]) != before:
            _save(data)
        return before - len(data["cards"])
