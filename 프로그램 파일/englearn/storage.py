"""Small JSON storage helpers (atomic writes, per-file locks)."""
import json
import os
import threading
import time
from pathlib import Path

_locks = {}
_locks_guard = threading.Lock()


def file_lock(path) -> threading.RLock:
    key = str(Path(path).resolve())
    with _locks_guard:
        lk = _locks.get(key)
        if lk is None:
            lk = _locks[key] = threading.RLock()
        return lk


def read_json(path, default=None):
    path = Path(path)
    with file_lock(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return default
        except (json.JSONDecodeError, OSError):
            # keep a copy of the broken file so nothing is silently lost
            try:
                bad = path.with_suffix(path.suffix + f".broken-{int(time.time())}")
                os.replace(path, bad)
            except OSError:
                pass
            return default


def update_json(path, fn, default=None):
    """Read-modify-write under one lock. fn(data) may modify in place or return new data."""
    path = Path(path)
    with file_lock(path):
        data = read_json(path, default)
        if data is None:
            data = default
        res = fn(data)
        if res is not None:
            data = res
        write_json(path, data)
        return data


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        tmp = path.with_name(path.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        for attempt in range(10):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                # Windows: another reader (antivirus, indexer) may hold the file briefly
                time.sleep(0.1 * (attempt + 1))
        else:
            os.replace(tmp, path)
