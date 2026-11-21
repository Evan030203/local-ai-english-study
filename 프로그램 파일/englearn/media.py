"""ffmpeg helpers: probe a movie, pull out subtitles / audio, make a browser-playable copy."""
import os
import re
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "mov_text", "webvtt", "text", "tx3g", "sami", "microdvd"}
BROWSER_VIDEO = {"h264", "vp8", "vp9", "av1"}
BROWSER_AUDIO = {"aac", "mp3", "opus", "vorbis"}
DIRECT_EXTS = {".mp4", ".m4v", ".webm"}

_ffmpeg = None
_hw_encoder = None


class Cancelled(Exception):
    pass


def ffmpeg_exe():
    global _ffmpeg
    if _ffmpeg:
        return _ffmpeg
    exe = None
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = None
    _ffmpeg = exe or shutil.which("ffmpeg")
    return _ffmpeg


def _popen(args, **kw):
    return subprocess.Popen(args, creationflags=CREATE_NO_WINDOW, **kw)


def _run(args, timeout=None):
    return subprocess.run(args, capture_output=True, timeout=timeout, creationflags=CREATE_NO_WINDOW)


# ---------------------------------------------------------------- probe
STREAM_RE = re.compile(
    r"^\s*Stream #0:(\d+)(?:\[0x[0-9a-fA-F]+\])?(?:\(([A-Za-z]{2,3})\))?(?:\[0x[0-9a-fA-F]+\])?:\s*"
    r"(Video|Audio|Subtitle|Data|Attachment):\s*([A-Za-z0-9_]+)(.*)$")


def probe(path):
    exe = ffmpeg_exe()
    if not exe:
        raise RuntimeError("ffmpeg를 찾을 수 없어요. 프로그램 설치를 다시 해 주세요.")
    p = _run([exe, "-hide_banner", "-i", str(path)], timeout=120)
    err = p.stderr.decode("utf-8", errors="replace")
    info = {"duration": 0.0, "format": "", "streams": []}
    m = re.search(r"Input #0, (.+?), from", err)
    if m:
        info["format"] = m.group(1)
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    cur = None
    for line in err.splitlines():
        sm = STREAM_RE.match(line)
        if sm:
            idx, lang, kind, codec, rest = sm.groups()
            cur = {
                "index": int(idx), "type": kind.lower(), "codec": codec.lower(),
                "lang": (lang or "").lower(), "title": "",
                "default": "(default)" in rest, "forced": "(forced)" in rest,
                "attached_pic": "(attached pic)" in rest,
            }
            if kind == "Audio":
                am = re.search(r"(\d+) Hz, ([^,]+)", rest)
                if am:
                    cur["layout"] = am.group(2).strip()
            if kind == "Video":
                vm = re.search(r"\b(\d{2,5})x(\d{2,5})\b", rest)
                if vm:
                    cur["width"], cur["height"] = int(vm.group(1)), int(vm.group(2))
            info["streams"].append(cur)
            continue
        if cur is not None:
            tm = re.match(r"^\s{4,}title\s*:\s*(.*)$", line)
            if tm and not cur["title"]:
                cur["title"] = tm.group(1).strip()
            if re.match(r"^\s*(Input|Output) #", line) or line.startswith("At least one"):
                cur = None
    if not info["streams"] and "Invalid data" in err:
        raise RuntimeError("영상 파일을 읽을 수 없어요 (지원하지 않거나 손상된 파일).")
    return info


def streams(info, kind):
    return [s for s in info["streams"] if s["type"] == kind and not s.get("attached_pic")]


def pick_audio(info):
    auds = streams(info, "audio")
    if not auds:
        return None
    for test in (lambda s: s["lang"] in ("eng", "en"),
                 lambda s: re.search(r"(?i)english|영어", s.get("title", "")),
                 lambda s: s["default"]):
        for s in auds:
            if test(s) and not re.search(r"(?i)commentary|코멘터리|해설", s.get("title", "")):
                return s["index"]
    return auds[0]["index"]


def play_plan(info, path, audio_idx, hevc_ok=False):
    """direct | remux | transcode | audio"""
    vids = streams(info, "video")
    auds = streams(info, "audio")
    if not vids:
        return "audio"
    v = vids[0]
    a = next((s for s in auds if s["index"] == audio_idx), None)
    ext = Path(path).suffix.lower()
    first_audio = auds[0]["index"] if auds else None
    if (ext in DIRECT_EXTS and v["codec"] in BROWSER_VIDEO and (a is None or a["codec"] in BROWSER_AUDIO)
            and audio_idx == first_audio and len(auds) <= 1):
        return "direct"
    if v["codec"] in BROWSER_VIDEO or (hevc_ok and v["codec"] == "hevc"):
        return "remux"
    return "transcode"


# ---------------------------------------------------------------- running with progress
def run_progress(args, duration, on_progress=None, cancel=None):
    """Run ffmpeg with -progress; on_progress(fraction 0..1)."""
    exe = ffmpeg_exe()
    full = [exe, "-hide_banner", "-nostdin", "-loglevel", "error", "-progress", "pipe:1", "-nostats"] + args
    proc = _popen(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    err_chunks = []

    def drain():
        for chunk in iter(lambda: proc.stderr.read(4096), b""):
            err_chunks.append(chunk)

    t = threading.Thread(target=drain, daemon=True)
    t.start()
    try:
        for raw in iter(proc.stdout.readline, b""):
            if cancel and cancel():
                proc.kill()
                raise Cancelled()
            line = raw.decode("utf-8", errors="replace").strip()
            if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
                try:
                    us = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                if on_progress and duration:
                    on_progress(max(0.0, min(1.0, us / 1e6 / duration)))
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
    t.join(timeout=2)
    if cancel and cancel():
        raise Cancelled()
    if proc.returncode != 0:
        msg = b"".join(err_chunks).decode("utf-8", errors="replace").strip().splitlines()
        tail = "\n".join(msg[-6:])
        raise RuntimeError("ffmpeg 오류: " + (tail or f"코드 {proc.returncode}"))


def extract_subtitle(path, stream_index, out_path, duration=0, on_progress=None, cancel=None):
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_progress(["-y", "-i", str(path), "-map", f"0:{stream_index}", "-c:s", "srt", str(out_path)],
                 duration, on_progress, cancel)
    return out_path


def extract_wav16k(path, audio_idx, out_path, duration=0, on_progress=None, cancel=None):
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".part.wav")
    args = ["-y", "-i", str(path)]
    if audio_idx is not None:
        args += ["-map", f"0:{audio_idx}"]
    args += ["-vn", "-sn", "-dn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(tmp)]
    run_progress(args, duration, on_progress, cancel)
    os.replace(tmp, out_path)
    return out_path


def _test_encoder(name):
    exe = ffmpeg_exe()
    try:
        p = _run([exe, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=black:s=320x240:d=0.5",
                  "-c:v", name, "-f", "null", "-"], timeout=25)
        return p.returncode == 0
    except Exception:
        return False


def hw_encoder():
    global _hw_encoder
    if _hw_encoder is None:
        _hw_encoder = ""
        if os.name == "nt":
            for name in ("h264_qsv", "h264_nvenc", "h264_amf"):
                if _test_encoder(name):
                    _hw_encoder = name
                    break
    return _hw_encoder


def make_playable(path, info, audio_idx, plan, out_path, on_progress=None, cancel=None):
    """Write a browser-friendly MP4 (H.264/AAC). plan: remux | transcode | audio."""
    out_path = Path(out_path)
    tmp = out_path.with_name(out_path.stem + ".part" + out_path.suffix)
    dur = info.get("duration") or 0
    a = next((s for s in info["streams"] if s["index"] == audio_idx), None)
    audio_args = []
    if audio_idx is not None:
        if a and a["codec"] == "aac" and plan == "remux" and (a.get("layout") in (None, "stereo", "mono")):
            audio_args = ["-map", f"0:{audio_idx}", "-c:a", "copy"]
        else:
            audio_args = ["-map", f"0:{audio_idx}", "-c:a", "aac", "-b:a", "160k", "-ac", "2"]
    if plan == "audio":
        args = ["-y", "-i", str(path), "-vn"] + (audio_args or ["-c:a", "aac", "-b:a", "160k", "-ac", "2"])
        args += ["-movflags", "+faststart", str(tmp)]
        run_progress(args, dur, on_progress, cancel)
    else:
        v = streams(info, "video")[0]
        vmap = ["-map", f"0:{v['index']}"]
        if plan == "remux":
            vargs = ["-c:v", "copy"] + (["-tag:v", "hvc1"] if v["codec"] == "hevc" else [])
        else:
            enc = hw_encoder()
            scale = ["-vf", "scale=-2:'min(720,ih)':flags=bicubic,format=yuv420p"]
            if enc == "h264_qsv":
                vargs = scale + ["-c:v", "h264_qsv", "-preset", "veryfast", "-global_quality", "25"]
            elif enc == "h264_nvenc":
                vargs = scale + ["-c:v", "h264_nvenc", "-preset", "p3", "-cq", "25"]
            elif enc == "h264_amf":
                vargs = scale + ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "24", "-qp_p", "26"]
            else:
                vargs = scale + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "24"]
        args = ["-y", "-i", str(path)] + vmap + vargs + audio_args + ["-sn", "-dn", "-movflags", "+faststart", str(tmp)]
        try:
            run_progress(args, dur, on_progress, cancel)
        except RuntimeError:
            if plan == "transcode" and _hw_encoder:
                # hardware encoder failed on this file: fall back to software once
                vargs = ["-vf", "scale=-2:'min(720,ih)':flags=bicubic,format=yuv420p", "-c:v", "libx264",
                         "-preset", "veryfast", "-crf", "24"]
                args = ["-y", "-i", str(path)] + vmap + vargs + audio_args + ["-sn", "-dn", "-movflags", "+faststart", str(tmp)]
                run_progress(args, dur, on_progress, cancel)
            else:
                raise
    os.replace(tmp, out_path)
    return out_path


# ---------------------------------------------------------------- wav access
def wav_duration(path):
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def read_wav(path, start, dur):
    import numpy as np
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        a = max(0, int(start * sr))
        b = min(n, int((start + dur) * sr))
        w.setpos(a)
        frames = w.readframes(max(0, b - a))
    x = np.frombuffer(frames, dtype=np.int16).astype("float32") / 32768.0
    return x


def file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def now():
    return time.time()
