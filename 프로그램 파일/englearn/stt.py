"""Local speech recognition with faster-whisper.

- Models are downloaded once into 프로그램 파일/모델/whisper-<name>/ (byte progress, resumable).
- On Windows the tool folder path contains Korean letters; CTranslate2 opens model files
  with narrow (ANSI) paths there, so models and the VAD are loaded from memory instead.
"""
import functools
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import paths

REPOS = {
    "tiny.en": "Systran/faster-whisper-tiny.en",
    "base.en": "Systran/faster-whisper-base.en",
    "small.en": "Systran/faster-whisper-small.en",
    "medium.en": "Systran/faster-whisper-medium.en",
}
APPROX_MB = {"tiny.en": 75, "base.en": 145, "small.en": 484, "medium.en": 1530}
WANTED = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "vocabulary.json", "preprocessor_config.json")
UA = {"User-Agent": "englearn-local/1.0"}

_models = {}
_model_locks = {}
_guard = threading.Lock()
_vad_patched = False


class Cancelled(Exception):
    pass


def available():
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def import_error():
    try:
        import faster_whisper  # noqa: F401
        return ""
    except Exception as e:
        return f"{type(e).__name__}: {e}"


def model_dir(name):
    return paths.MODELS_DIR / f"whisper-{name}"


def is_ready(name):
    d = model_dir(name)
    return (d / "model.bin").is_file() and (d / "config.json").is_file() and (d / "tokenizer.json").is_file()


def status():
    return {n: {"ready": is_ready(n), "mb": APPROX_MB[n]} for n in REPOS}


# ---------------------------------------------------------------- download
def _open(url, headers=None, timeout=60):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def _file_list(repo):
    try:
        with _open(f"https://huggingface.co/api/models/{repo}?blobs=true", timeout=30) as r:
            meta = json.loads(r.read().decode("utf-8"))
        out = []
        for s in meta.get("siblings", []):
            fn = s.get("rfilename", "")
            if fn in WANTED:
                out.append((fn, int(s.get("size") or 0)))
        if any(fn == "model.bin" for fn, _ in out):
            return out
    except Exception:
        pass
    return [("config.json", 0), ("model.bin", 0), ("tokenizer.json", 0), ("vocabulary.txt", 0)]


def download(name, on_progress=None, cancel=None):
    """on_progress(done_bytes, total_bytes)"""
    repo = REPOS[name]
    d = model_dir(name)
    d.mkdir(parents=True, exist_ok=True)
    files = _file_list(repo)
    total = sum(sz for _, sz in files) or APPROX_MB[name] * 1024 * 1024
    done = 0
    for fn, size in files:
        dest = d / fn
        if dest.is_file() and (not size or dest.stat().st_size == size):
            done += dest.stat().st_size
            continue
        part = d / (fn + ".part")
        have = part.stat().st_size if part.exists() else 0
        url = f"https://huggingface.co/{repo}/resolve/main/{fn}"
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            resp = _open(url, headers=headers)
        except urllib.error.HTTPError as e:
            if e.code == 404 and fn != "model.bin":
                continue  # optional file
            if e.code == 416:  # already complete
                os.replace(part, dest)
                done += dest.stat().st_size
                continue
            raise RuntimeError(f"모델 내려받기 실패 ({fn}): HTTP {e.code}") from e
        except urllib.error.URLError as e:
            raise RuntimeError("인터넷 연결을 확인해 주세요. 음성 인식 모델은 처음 한 번만 내려받으면 돼요. "
                               f"({e.reason})") from e
        with resp:
            if have and resp.status != 206:
                have = 0  # server ignored Range
            mode = "ab" if have else "wb"
            done += have
            with open(part, mode) as f:
                last = 0.0
                while True:
                    if cancel and cancel():
                        raise Cancelled()
                    chunk = resp.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress and time.time() - last > 0.3:
                        on_progress(done, total)
                        last = time.time()
        if size and part.stat().st_size != size:
            raise RuntimeError(f"모델 파일이 덜 받아졌어요 ({fn}). 다시 시도해 주세요.")
        os.replace(part, dest)
    if on_progress:
        on_progress(total, total)
    if not is_ready(name):
        raise RuntimeError("모델 파일이 모두 받아지지 않았어요. 다시 시도해 주세요.")


# ---------------------------------------------------------------- loading
def _patch_vad():
    global _vad_patched
    if _vad_patched:
        return
    try:
        import faster_whisper.vad as vad
        from faster_whisper.utils import get_assets_path

        @functools.lru_cache
        def get_vad_model():
            path = os.path.join(get_assets_path(), "silero_vad_v6.onnx")
            if not os.path.exists(path):
                cands = [f for f in os.listdir(get_assets_path()) if f.endswith(".onnx")]
                path = os.path.join(get_assets_path(), cands[0])
            with open(path, "rb") as fh:
                data = fh.read()
            return vad.SileroVADModel(data)  # InferenceSession accepts bytes

        vad.get_vad_model = get_vad_model
    except Exception:
        pass
    _vad_patched = True


def default_threads(background=False):
    n = os.cpu_count() or 4
    return max(1, n - 2) if background else max(1, min(n, 8))


def get_model(name, slot="speech"):
    key = (name, slot)
    with _guard:
        m = _models.get(key)
        if m is not None:
            return m, _model_locks[key]
    if not is_ready(name):
        raise RuntimeError(f"음성 인식 모델({name})이 아직 없어요. 설정에서 내려받아 주세요.")
    from faster_whisper import WhisperModel
    _patch_vad()
    d = model_dir(name)
    threads = default_threads(background=(slot == "movie"))
    if os.name == "nt" and not str(d).isascii():
        files = {}
        for f in d.iterdir():
            if f.is_file() and not f.name.endswith((".part", ".tmp")):
                files[f.name] = f.read_bytes()
        m = WhisperModel(f"whisper-{name}", device="cpu", compute_type="int8", cpu_threads=threads, files=files)
        del files
    else:
        m = WhisperModel(str(d), device="cpu", compute_type="int8", cpu_threads=threads)
    with _guard:
        _models[key] = m
        _model_locks[key] = threading.Lock()
        return m, _model_locks[key]


def unload(slot=None):
    with _guard:
        for k in list(_models):
            if slot is None or k[1] == slot:
                _models.pop(k, None)


# ---------------------------------------------------------------- recognition
def _words(segs):
    out = []
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                out.append([t, round(w.start, 2), round(w.end, 2), round(w.probability, 3)])
    return out


def load_audio_16k(path):
    """Decode any audio/video file to 16 kHz mono float32 with the bundled ffmpeg.

    (faster-whisper's own decoder depends on PyAV options that newer PyAV releases removed.)"""
    import subprocess
    import numpy as np
    from . import media
    exe = media.ffmpeg_exe()
    p = subprocess.run([exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-i", str(path),
                        "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True, timeout=300, creationflags=media.CREATE_NO_WINDOW)
    if p.returncode != 0 and not p.stdout:
        raise RuntimeError("녹음을 읽지 못했어요: " + p.stderr.decode("utf-8", errors="replace").strip()[-200:])
    return np.frombuffer(p.stdout, dtype=np.int16).astype("float32") / 32768.0


def transcribe_clip(path, name):
    """Recognise a short recording of the learner."""
    audio = load_audio_16k(path)
    dur = len(audio) / 16000.0
    if dur < 0.3:
        return {"text": "", "words": [], "duration": round(dur, 2), "no_speech": True}
    model, lock = get_model(name, "speech")
    t0 = time.time()
    with lock:
        segs, _info = model.transcribe(
            audio, language="en", beam_size=5, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 400, "speech_pad_ms": 250},
            word_timestamps=True, condition_on_previous_text=False, temperature=[0.0, 0.2, 0.4])
        segs = list(segs)
    words = _words(segs)
    text = " ".join(s.text.strip() for s in segs).strip()
    text = re.sub(r"\s+", " ", text)
    return {"text": text, "words": words, "duration": round(dur, 2), "no_speech": not text,
            "secs": round(time.time() - t0, 2)}


HALLU = re.compile(r"^(thank you\.?|thanks for watching!?|you|bye\.?|\.+|subtitles by.*|♪+)$", re.I)


def transcribe_movie(wav_path, name, state, on_progress=None, cancel=None, on_save=None, beam_size=5):
    """Chunked transcription of the movie's 16 kHz WAV.

    state = {"pos": seconds already done, "segments": [...]} is updated in place
    so an interrupted run can continue later.
    """
    from . import media
    total = media.wav_duration(wav_path)
    model, lock = get_model(name, "movie")
    CH, EXTRA = 480.0, 30.0
    pos = float(state.get("pos") or 0.0)
    segs_out = state.setdefault("segments", [])
    while pos < total - 0.5:
        if cancel and cancel():
            raise Cancelled()
        length = min(CH + EXTRA, total - pos)
        audio = media.read_wav(wav_path, pos, length)
        is_last = pos + length >= total - 0.5
        kept = []
        with lock:
            segs, _ = model.transcribe(
                audio, language="en", beam_size=beam_size, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
                word_timestamps=True, condition_on_previous_text=False,
                temperature=[0.0, 0.2, 0.4, 0.6], no_speech_threshold=0.6,
                hallucination_silence_threshold=2.0)
            for s in segs:
                if cancel and cancel():
                    raise Cancelled()
                if not is_last and s.start >= CH:
                    break
                if not is_last and s.end > length - 1.0:
                    break  # may be cut at the chunk edge: next chunk starts here
                kept.append(s)
                if on_progress:
                    on_progress(min(1.0, (pos + s.end) / total))
        for s in kept:
            text = s.text.strip()
            if not text or HALLU.match(text):
                continue
            words = [[w[0], round(w[1] + pos, 2), round(w[2] + pos, 2), w[3]] for w in _words([s])]
            segs_out.append({"start": round(s.start + pos, 2), "end": round(s.end + pos, 2), "text": text,
                             "words": words, "p": round(getattr(s, "avg_logprob", 0.0), 3)})
        if is_last:
            pos = total
        elif kept:
            pos = pos + max(kept[-1].end, 1.0)
        else:
            pos = pos + CH
        state["pos"] = round(pos, 2)
        if on_progress:
            on_progress(min(1.0, pos / total))
        if on_save:
            on_save(state)
    return segs_out


def segments_to_lines(segments, max_words=22, gap=0.8):
    """Split Whisper segments into sentence-sized study lines using word timings."""
    lines = []
    cur = []

    def flush():
        if not cur:
            return
        text = " ".join(w[0] for w in cur)
        text = re.sub(r"\s+([,.?!])", r"\1", text).strip()
        if re.search(r"[A-Za-z]", text):
            lines.append({"start": cur[0][1], "end": cur[-1][2], "text": text, "ko": "", "ko_src": "",
                          "words": [list(w) for w in cur]})
        cur.clear()

    for seg in segments:
        ws = seg.get("words") or []
        if not ws:
            flush()
            lines.append({"start": seg["start"], "end": seg["end"], "text": seg["text"], "ko": "", "ko_src": "",
                          "words": None})
            continue
        for w in ws:
            if cur and (w[1] - cur[-1][2] > gap):
                flush()
            cur.append(w)
            if re.search(r"[.?!]$", w[0]) and len(cur) >= 2:
                flush()
            elif len(cur) >= max_words:
                flush()
    flush()
    # drop runs of the same hallucinated line
    out = []
    for ln in lines:
        if len(out) >= 2 and out[-1]["text"] == ln["text"] == out[-2]["text"]:
            continue
        out.append(ln)
    for i, ln in enumerate(out):
        ln["id"] = i
    return out
