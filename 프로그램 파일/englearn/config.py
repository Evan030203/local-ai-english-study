"""User settings (학습 기록/_설정.json)."""
import copy
import threading

from . import paths
from .storage import read_json, write_json

DEFAULTS = {
    "ollama_url": "http://127.0.0.1:11434",
    "model": "",                 # empty = choose automatically
    "stt_model": "small.en",     # my voice
    "movie_stt_model": "small.en",  # movie transcription when there are no subtitles
    "tts_voice": "",             # Windows (browser) voice name
    "tts_engine": "kokoro",      # kokoro (natural, local) | browser
    "tts_voice_k": "af_heart",   # Kokoro voice
    "tts_rate": 0.95,
    "allow_online_voices": False,
    "level": "normal",           # easy / normal / real
    "profile": {"job": "", "background": "", "company": ""},
    "port": 8765,
    "analysis_depth": "normal",  # quick / normal / deep
    "mic_keep": False,           # False: the microphone turns off right after each recording
}

_lock = threading.Lock()
_cache = None


def load():
    global _cache
    with _lock:
        if _cache is None:
            data = read_json(paths.SETTINGS_FILE, {}) or {}
            merged = copy.deepcopy(DEFAULTS)
            for k, v in data.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k].update(v)
                else:
                    merged[k] = v
            _cache = merged
        return copy.deepcopy(_cache)


def update(changes: dict):
    global _cache
    cur = load()
    for k, v in (changes or {}).items():
        if k not in DEFAULTS:
            continue
        if isinstance(v, dict) and isinstance(cur.get(k), dict):
            cur[k].update(v)
        else:
            cur[k] = v
    with _lock:
        _cache = cur
        write_json(paths.SETTINGS_FILE, cur)
    return copy.deepcopy(cur)


def get(key):
    return load().get(key, DEFAULTS.get(key))
