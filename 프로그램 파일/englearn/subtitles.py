"""Subtitle reading: SRT, WebVTT, ASS/SSA, SAMI (.smi).

- Encoding detection (UTF-8/UTF-16/CP949/CP1252)
- Language detection (Korean / English / other)
- SMI files with several classes (KRCC, ENCC ...) and "dual" SRT files with an
  English and a Korean line in each cue are split into separate tracks.
- Cleaning: tags, sound descriptions [MUSIC] (laughs), lyrics, speaker labels.
"""
import html
import re
from pathlib import Path

SUB_EXTS = {".srt", ".vtt", ".ass", ".ssa", ".smi", ".sami"}

HANGUL = re.compile(r"[가-힣]")
LATIN = re.compile(r"[A-Za-z]")
EN_STOP = {
    "the", "you", "i", "to", "a", "and", "is", "it", "that", "of", "what", "in", "me",
    "we", "this", "don't", "i'm", "it's", "my", "your", "on", "for", "have", "be",
    "do", "are", "not", "with", "just", "can", "know", "was", "he", "she", "they",
}


# ---------------------------------------------------------------- encoding
def _looks_korean(s: str) -> bool:
    runs = re.findall(r"[가-힣]+", s)
    if not runs:
        return False
    multi = sum(1 for r in runs if len(r) >= 2)
    return multi / len(runs) > 0.3


def decode_bytes(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="replace")
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    head = data[:4000]
    if head and head.count(b"\x00") > len(head) // 4:
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        k = data.decode("cp949")
        if _looks_korean(k):
            return k
    except UnicodeDecodeError:
        pass
    return data.decode("cp1252", errors="replace")


def read_text_auto(path) -> str:
    return decode_bytes(Path(path).read_bytes())


# ---------------------------------------------------------------- language
def detect_lang(texts) -> str:
    sample = " ".join(t for t in texts[:600] if t)
    h = len(HANGUL.findall(sample))
    lat = len(LATIN.findall(sample))
    other = len(re.findall(r"[぀-ヿ一-鿿Ѐ-ӿ؀-ۿ฀-๿]", sample))
    total = h + lat + other
    if total < 5:
        return "?"
    if h / total > 0.25:
        return "ko"
    if lat / total > 0.7:
        words = re.findall(r"[a-z']+", sample.lower())
        if not words:
            return "?"
        stop = sum(1 for w in words if w in EN_STOP)
        return "en" if stop / len(words) > 0.12 else "other"
    return "other"


def lang_from_name(name: str) -> str:
    n = name.lower()
    toks = re.split(r"[._\-\s\[\]()]+", n)
    if any(t in ("ko", "kor", "korean", "kr", "한글", "한국어", "kor_sdh") for t in toks) or "한글" in n or "한국어" in n:
        return "ko"
    if any(t in ("en", "eng", "english", "enus", "en-us", "sdh", "영어", "영문") for t in toks) or "영어" in n or "영문" in n:
        return "en"
    return "?"


# ---------------------------------------------------------------- cleaning
TAG = re.compile(r"<[^>]*>")
ASS_TAG = re.compile(r"\{[^}]*\}")
SDH = re.compile(r"\[[^\]]{0,60}\]|\([^)]{0,60}\)|（[^）]{0,60}）|【[^】]{0,60}】")
MUSIC = re.compile(r"[♪♫♬#]")
SPEAKER = re.compile(r"^\s*([A-Z][A-Z0-9 .'&\-]{0,24}|[가-힣]{1,6})\s*:\s+(?=\S)")


def clean_text(raw: str) -> str:
    """Return cleaned text. A new speaker turn inside one cue starts a new line."""
    t = raw.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
    t = ASS_TAG.sub("", t)
    t = re.sub(r"(?i)<br\s*/?>", "\n", t)
    t = TAG.sub("", t)
    t = html.unescape(t).replace("\xa0", " ").replace("​", "")
    out = []
    for line in t.split("\n"):
        line = line.strip()
        if not line:
            continue
        if MUSIC.search(line):
            continue
        line = SDH.sub("", line).strip()
        turn = False
        if line[:1] in "-–—":
            turn = True
            line = line.lstrip("-–— ").strip()
        m = SPEAKER.match(line)
        if m and not m.group(1).strip().isdigit():
            line = line[m.end():].strip()
            turn = True
        line = re.sub(r"\s+", " ", line).strip()
        if not re.search(r"[A-Za-z가-힣]", line):
            continue
        if out and not turn:
            out[-1] = out[-1] + " " + line
        else:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------- timestamps
def _ts(h, m, s, ms):
    ms = (ms or "0")
    ms = int((ms + "00")[:3])
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + ms / 1000.0


SRT_TS = r"(\d{1,2}):(\d{1,2}):(\d{1,2})(?:[,.:](\d{1,3}))?"
SRT_ARROW = re.compile(SRT_TS + r"\s*-->\s*" + SRT_TS)
VTT_TS = r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})"
VTT_ARROW = re.compile(VTT_TS + r"\s*-->\s*" + VTT_TS)


def _lines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def parse_srt(text):
    cues, cur = [], None

    def close():
        if cur and cur["raw"]:
            cues.append(cur)

    for line in _lines(text):
        m = SRT_ARROW.search(line)
        if m:
            if cur is not None and cur["raw"] and cur["raw"][-1].strip().isdigit():
                cur["raw"].pop()  # index line of the next cue (missing blank line)
            close()
            g = m.groups()
            cur = {"start": _ts(*g[0:4]), "end": _ts(*g[4:8]), "raw": []}
            continue
        if cur is None:
            continue
        if not line.strip():
            close()
            cur = None
            continue
        cur["raw"].append(line)
    close()
    return [{"start": c["start"], "end": c["end"], "raw": "\n".join(c["raw"])} for c in cues]


def parse_vtt(text):
    cues, cur, skip = [], None, False
    for line in _lines(text):
        if cur is None and (line.startswith("NOTE") or line.startswith("STYLE") or line.startswith("REGION")):
            skip = True
            continue
        if skip:
            if not line.strip():
                skip = False
            continue
        m = VTT_ARROW.search(line)
        if m:
            if cur and cur["raw"]:
                cues.append(cur)
            g = m.groups()
            cur = {"start": _ts(*g[0:4]), "end": _ts(*g[4:8]), "raw": []}
            continue
        if cur is None:
            continue
        if not line.strip():
            if cur["raw"]:
                cues.append(cur)
            cur = None
            continue
        line = re.sub(r"<\d{1,2}:\d{2}(?::\d{2})?[.,]\d{3}>", "", line)  # karaoke timestamps
        line = re.sub(r"<v(?:\.[^ >]*)?\s+([^>]+)>", "", line)            # <v Speaker>
        cur["raw"].append(line)
    if cur and cur["raw"]:
        cues.append(cur)
    return [{"start": c["start"], "end": c["end"], "raw": "\n".join(c["raw"])} for c in cues]


def parse_ass(text):
    cues = []
    fmt = None
    in_events = False
    skip_style = re.compile(r"(?i)sign|song|lyric|karaoke|^op$|^ed$|title|note")
    for line in _lines(text):
        s = line.strip()
        if s.startswith("["):
            in_events = s.lower() == "[events]"
            continue
        if not in_events:
            continue
        if s.lower().startswith("format:"):
            fmt = [f.strip().lower() for f in s.split(":", 1)[1].split(",")]
            continue
        if not s.lower().startswith("dialogue:"):
            continue
        body = s.split(":", 1)[1]
        f = fmt or ["layer", "start", "end", "style", "name", "marginl", "marginr", "marginv", "effect", "text"]
        parts = body.split(",", len(f) - 1)
        if len(parts) < len(f):
            continue
        rec = dict(zip(f, [p.strip() if k != "text" else p for k, p in zip(f, parts)]))
        if skip_style.search(rec.get("style", "") or ""):
            continue
        txt = rec.get("text", "")
        if re.search(r"\{[^}]*\\p[1-9]", txt):
            continue  # vector drawing
        try:
            st = _ass_time(rec["start"])
            en = _ass_time(rec["end"])
        except (KeyError, ValueError):
            continue
        cues.append({"start": st, "end": en, "raw": txt})
    cues.sort(key=lambda c: c["start"])
    return cues


def _ass_time(t):
    h, m, s = t.strip().split(":")
    sec, _, frac = s.partition(".")
    return int(h) * 3600 + int(m) * 60 + int(sec) + (int((frac + "00")[:2]) / 100.0 if frac else 0)


SMI_LANG_BY_CLASS = {
    "KRCC": "ko", "KOCC": "ko", "KOKRCC": "ko", "KRKRCC": "ko", "KORCC": "ko", "KORSC": "ko",
    "ENCC": "en", "EGCC": "en", "ENUSCC": "en", "ENGCC": "en", "ENGSC": "en", "ENUKCC": "en",
}


def parse_smi(text):
    """Return list of tracks: {"cls", "lang", "cues": [...]}"""
    styles = {}
    for m in re.finditer(r"\.([\w-]+)\s*\{([^}]*)\}", text):
        body = m.group(2)
        lm = re.search(r"lang\s*:\s*([A-Za-z]{2})", body, re.I)
        styles[m.group(1).upper()] = (lm.group(1).lower() if lm else "")
    syncs = list(re.finditer(r"<sync\s+start\s*=\s*[\"']?(-?\d+)[\"']?[^>]*>", text, re.I))
    events = {}
    for k, m in enumerate(syncs):
        t = max(0, int(m.group(1))) / 1000.0
        seg = text[m.end(): syncs[k + 1].start() if k + 1 < len(syncs) else len(text)]
        ps = list(re.finditer(r"<p(\s+[^>]*)?>", seg, re.I))
        if not ps:
            events.setdefault("_", []).append((t, seg))
            continue
        for j, pm in enumerate(ps):
            cm = re.search(r"class\s*=\s*[\"']?([\w-]+)", pm.group(1) or "", re.I)
            cls = cm.group(1).upper() if cm else "_"
            content = seg[pm.end(): ps[j + 1].start() if j + 1 < len(ps) else len(seg)]
            events.setdefault(cls, []).append((t, content))
    tracks = []
    for cls, evs in events.items():
        evs.sort(key=lambda e: e[0])
        cues = []
        for i, (t, content) in enumerate(evs):
            raw = re.sub(r"(?i)<br\s*/?>", "\n", content)
            raw = re.sub(r"(?i)</?(sync|p|body|sami|html)[^>]*>", "", raw)
            if not clean_text(raw):
                continue
            nxt = evs[i + 1][0] if i + 1 < len(evs) else t + 4.0
            end = min(nxt, t + 10.0) if nxt > t else t + 3.0
            cues.append({"start": t, "end": end, "raw": raw})
        lang = styles.get(cls, "")
        lang = {"ko": "ko", "en": "en"}.get(lang, "") or SMI_LANG_BY_CLASS.get(cls, "")
        tracks.append({"cls": cls, "lang": lang, "cues": cues})
    return [t for t in tracks if t["cues"]]


# ---------------------------------------------------------------- public API
def _finish(cues):
    out = []
    for c in cues:
        txt = clean_text(c["raw"])
        if not txt:
            continue
        st, en = float(c["start"]), float(c["end"])
        if en <= st:
            en = st + 1.5
        out.append({"start": round(st, 3), "end": round(en, 3), "text": txt})
    out.sort(key=lambda c: c["start"])
    return out


def _raw_lines(raw):
    parts = re.split(r"\n|\\N|<br\s*/?>", raw, flags=re.I)
    return [p for p in parts if TAG.sub("", ASS_TAG.sub("", p)).strip()]


def _split_dual(cues):
    """If many cues contain both a Hangul line and a Latin line, split into two tracks."""
    if not cues:
        return None
    both = 0
    for c in cues:
        lines = [TAG.sub("", ASS_TAG.sub("", l)) for l in _raw_lines(c["raw"])]
        has_ko = any(HANGUL.search(l) for l in lines)
        has_en = any(not HANGUL.search(l) and LATIN.search(l) for l in lines)
        both += has_ko and has_en
    if both / len(cues) < 0.4:
        return None
    en, ko = [], []
    for c in cues:
        lines = _raw_lines(c["raw"])
        k = [l for l in lines if HANGUL.search(TAG.sub("", l))]
        e = [l for l in lines if not HANGUL.search(TAG.sub("", l))]
        if e:
            en.append({"start": c["start"], "end": c["end"], "raw": "\n".join(e)})
        if k:
            ko.append({"start": c["start"], "end": c["end"], "raw": "\n".join(k)})
    return en, ko


def load_tracks(path, name_hint=None):
    """Read a subtitle file. Returns list of {"lang","label","cues"} (cues cleaned)."""
    path = Path(path)
    text = read_text_auto(path)
    ext = path.suffix.lower()
    if ext in (".smi", ".sami") or re.search(r"<sami>", text[:2000], re.I):
        raw_tracks = [{"lang": t["lang"], "label": t["cls"], "cues": t["cues"]} for t in parse_smi(text)]
    elif ext in (".ass", ".ssa") or "[Events]" in text[:20000]:
        raw_tracks = [{"lang": "", "label": "", "cues": parse_ass(text)}]
    elif ext == ".vtt" or text.lstrip().startswith("WEBVTT"):
        raw_tracks = [{"lang": "", "label": "", "cues": parse_vtt(text)}]
    else:
        raw_tracks = [{"lang": "", "label": "", "cues": parse_srt(text)}]

    tracks = []
    for t in raw_tracks:
        dual = _split_dual(t["cues"]) if len(raw_tracks) == 1 else None
        if dual:
            en, ko = dual
            tracks.append({"lang": "en", "label": "영어 (이중 자막)", "cues": _finish(en)})
            tracks.append({"lang": "ko", "label": "한국어 (이중 자막)", "cues": _finish(ko)})
            continue
        cues = _finish(t["cues"])
        if not cues:
            continue
        lang = detect_lang([c["text"] for c in cues])
        if lang == "?":
            lang = t["lang"] or lang_from_name(name_hint or path.name)
        tracks.append({"lang": lang, "label": t["label"], "cues": cues})
    return tracks


def find_external(movie_path):
    """Subtitle files next to the movie. Same-stem files first."""
    movie_path = Path(movie_path)
    folder = movie_path.parent
    stem = movie_path.stem.lower()
    try:
        files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUB_EXTS]
    except OSError:
        return []
    def related(p):
        s = p.stem.lower()
        base = s.split(".")[0]
        return s.startswith(stem) or (len(base) >= 3 and stem.startswith(base))

    same = [p for p in files if related(p)]
    pool = same if same else (files if len(files) <= 6 else [])
    pool.sort(key=lambda p: (0 if p in same else 1, p.name.lower()))
    return pool


# ---------------------------------------------------------------- lines
def _nwords(t):
    return len(re.findall(r"[A-Za-z0-9']+", t))


TERMINAL = re.compile(r"[.?!…][\"'”’)\]]*$")


def merge_sentences(cues, max_words=22, max_dur=9.0, max_gap=0.7):
    out = []
    for c in cues:
        if out:
            p = out[-1]
            gap = c["start"] - p["end"]
            if (
                not TERMINAL.search(p["text"])
                and -0.2 <= gap <= max_gap
                and "\n" not in c["text"]
                and _nwords(p["text"]) + _nwords(c["text"]) <= max_words
                and c["end"] - p["start"] <= max_dur
            ):
                p["text"] = (p["text"].rstrip(" -—…") + " " + c["text"]).strip()
                p["end"] = max(p["end"], c["end"])
                continue
        out.append(dict(c))
    return out


def pair_korean(lines, ko_cues):
    """Attach overlapping Korean subtitle text to each English line."""
    j = 0
    n = len(ko_cues)
    for ln in lines:
        s, e = ln["start"], ln["end"]
        while j < n and ko_cues[j]["end"] < s - 1.0:
            j += 1
        parts = []
        k = j
        while k < n and ko_cues[k]["start"] < e + 0.3:
            c = ko_cues[k]
            ov = min(e, c["end"]) - max(s, c["start"])
            dur_c = max(0.3, c["end"] - c["start"])
            dur_l = max(0.3, e - s)
            if ov > 0 and (ov / dur_c >= 0.3 or ov / dur_l >= 0.3):
                parts.append(c["text"].replace("\n", " "))
            k += 1
        if parts:
            seen = []
            for p in parts:
                if p not in seen:
                    seen.append(p)
            ln["ko"] = " ".join(seen)
            ln["ko_src"] = "sub"
    return lines


def cues_to_lines(en_cues, ko_cues=None):
    merged = merge_sentences(en_cues)
    lines = []
    for c in merged:
        if not LATIN.search(c["text"]):
            continue
        lines.append({"start": c["start"], "end": c["end"], "text": c["text"], "ko": "", "ko_src": ""})
    if ko_cues:
        pair_korean(lines, ko_cues)
    for i, ln in enumerate(lines):
        ln["id"] = i
    return lines
