"""Find subtitles that are burned into the picture, so the study screen can cover them.

Frames from the middle of spoken lines are compared with frames from quiet gaps between lines.
Rows where sharp letter edges show up mostly while people talk are where the burned-in subtitles sit.
Everything runs on this computer with the bundled ffmpeg; nothing is sent anywhere.
"""
import concurrent.futures as cf
import subprocess

import numpy as np

from . import media

WIDTH = 768             # analysis width: thin letters (yellow, thin outline) keep their edges here
EDGE = 40               # grey-level jump that counts as a letter edge
DEFAULT = {"top": 0.78, "height": 0.16}


def _frame(path, t):
    cmd = [media.ffmpeg_exe(), "-hide_banner", "-nostdin", "-loglevel", "error", "-ss", f"{max(0.0, t):.2f}",
           "-i", str(path), "-frames:v", "1", "-an", "-sn",
           "-vf", f"scale={WIDTH}:-2:flags=area,format=gray", "-f", "rawvideo", "-"]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=90, creationflags=media.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        return None
    data = p.stdout
    if p.returncode != 0 or len(data) < WIDTH * 16 or len(data) % WIDTH:
        return None
    return np.frombuffer(data, dtype=np.uint8).reshape(-1, WIDTH).astype(np.float32)


def _edges(img):
    """Per row: the share of sharp left-right changes. Outlined letters make many of them."""
    return (np.abs(np.diff(img, axis=1)) > EDGE).mean(axis=1)


def _spread(items, k):
    n = len(items)
    if n <= k:
        return list(items)
    return [items[round(i * (n - 1) / (k - 1))] for i in range(k)]


def sample_times(lines, offset=0.0, duration=None, k=20):
    spans = sorted((float(l["start"]) + offset, float(l["end"]) + offset)
                   for l in lines if float(l.get("end", 0)) > float(l.get("start", 0)))
    speech = _spread([(a + b) / 2 for a, b in spans if b - a >= 0.6 and a >= 0], k)
    gaps = [(a2 - b1, b1 + (a2 - b1) / 2) for (a1, b1), (a2, b2) in zip(spans, spans[1:]) if a2 - b1 >= 0.8]
    long = [m for g, m in gaps if g >= 1.6]  # subtitles may stay a moment after the speech ends
    quiet = long if len(long) >= 6 else [m for g, m in gaps]
    if spans and spans[0][0] >= 1.6:          # before the first line
        quiet.append(spans[0][0] / 2)
    if spans and duration and duration - spans[-1][1] >= 1.6:   # after the last line
        quiet.append(spans[-1][1] + (duration - spans[-1][1]) / 2)
    return speech, _spread(sorted(quiet), k)


def _bands(d, core, grow):
    """Runs of rows above the core level, widened while they stay above the grow level."""
    out, i, h = [], 0, len(d)
    while i < h:
        if not core[i]:
            i += 1
            continue
        j = i
        while j + 1 < h and core[j + 1]:
            j += 1
        a, b = i, j
        while a > 0 and d[a - 1] >= grow:   # a second subtitle line shows up less often: grow into it
            a -= 1
        while b + 1 < h and d[b + 1] >= grow:
            b += 1
        if not out or a > out[-1][1]:
            out.append((a, b))
        i = j + 1
    return out


def _centred(frames, a, b):
    """1 when the text in rows a..b sits in the middle of the picture (subtitles), 0 when it sits to one side."""
    offs = []
    for f in frames:
        col = (np.abs(np.diff(f[a:b + 1], axis=1)) > EDGE).sum(axis=0)
        tot = col.sum()
        if tot < 6:
            continue
        c = float((col * np.arange(len(col))).sum() / tot) / max(1, len(col) - 1)
        offs.append(abs(c - 0.5))
    if not offs:
        return 0.0
    return max(0.0, 1.0 - float(np.mean(offs)) / 0.3)


def _bright_edges(img):
    """Per row: share of sharp left-right changes next to a bright pixel (white or yellow letters)."""
    dx = np.abs(np.diff(img, axis=1))
    bright = np.maximum(img[:, 1:], img[:, :-1]) > 170
    return ((dx > 50) & bright).mean(axis=1)


def _smooth(d, h):
    k = max(1, h // 80)
    return np.convolve(d, np.ones(2 * k + 1) / (2 * k + 1), mode="same")


def _contrast_score(fs, fq, h):
    """Rows that look like text while people speak but not in the quiet gaps between lines."""
    es = np.array([_edges(f) for f in fs])
    eq = np.array([_edges(f) for f in fq])
    return _smooth((es > 0.06).mean(axis=0) - (eq > 0.06).mean(axis=0), h)


def _changing_text_score(fs, h):
    """Without quiet gaps: rows with bright letters in most spoken frames whose content keeps changing.
    Fixed titles and name tags look the same in every frame, subtitles do not."""
    pres = np.array([_bright_edges(f) > 0.03 for f in fs]).mean(axis=0)
    diffs = np.array([np.abs(a - b).mean(axis=1) / 255.0 for a, b in zip(fs, fs[1:])])
    change = np.clip(np.median(diffs, axis=0) / 0.08, 0, 1)
    return _smooth(pres * change, h)


def detect(path, lines, offset=0.0, duration=None, workers=4):
    speech, quiet = sample_times(lines, offset, duration)
    if len(speech) < 6:
        return {"found": False, "reason": "few", **DEFAULT}
    with cf.ThreadPoolExecutor(workers) as ex:
        frames = list(ex.map(lambda t: _frame(path, t), speech + quiet))
    fs = [f for f in frames[:len(speech)] if f is not None]
    fq = [f for f in frames[len(speech):] if f is not None]
    if len(fs) < 6:
        return {"found": False, "reason": "frames", **DEFAULT}
    h = min(f.shape[0] for f in fs + fq)
    fs, fq = [f[:h] for f in fs], [f[:h] for f in fq]
    if len(fq) >= 3:
        d, how = _contrast_score(fs, fq, h), "gaps"
    else:
        d, how = _changing_text_score(fs, h), "text"
    best = None
    for a, b in _bands(d, d >= 0.35, 0.15):
        if (b - a + 1) / h > 0.36:
            continue
        score = float(d[a:b + 1].sum()) * _centred(fs, a, b)
        if score > 0 and (best is None or score > best[0]):
            best = (score, a, b)
    if not best:
        return {"found": False, "reason": "none", "score": round(float(d.max()), 3), **DEFAULT}
    _, a, b = best
    pad = max(round(h * 0.015), round((b - a + 1) * 0.2))
    a, b = max(0, a - pad), min(h - 1, b + pad)
    return {"found": True, "top": round(a / h, 4), "height": round((b - a + 1) / h, 4),
            "score": round(float(d[a:b + 1].max()), 3), "frames": len(fs) + len(fq), "how": how}
