"""Word tokenizing, normalizing and aligning (dictation / speaking scores)."""
import difflib
import re

WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)*|['’](?:em|cause|til|bout)\b", re.I)

_PRON = r"(?:i|you|he|she|it|we|they|that|there|what|who|where|how|here|this|everyone|everybody|nobody|someone|somebody)"

CONTRACTIONS = {
    "i'm": ["i", "am"], "you're": ["you", "are"], "we're": ["we", "are"], "they're": ["they", "are"],
    "let's": ["let", "us"], "isn't": ["is", "not"], "aren't": ["are", "not"], "wasn't": ["was", "not"],
    "weren't": ["were", "not"], "don't": ["do", "not"], "doesn't": ["does", "not"], "didn't": ["did", "not"],
    "haven't": ["have", "not"], "hasn't": ["has", "not"], "hadn't": ["had", "not"], "won't": ["will", "not"],
    "wouldn't": ["would", "not"], "can't": ["can", "not"], "cannot": ["can", "not"], "couldn't": ["could", "not"],
    "shouldn't": ["should", "not"], "mustn't": ["must", "not"], "needn't": ["need", "not"], "ain't": ["am", "not"],
    "could've": ["could", "have"], "would've": ["would", "have"], "should've": ["should", "have"],
    "might've": ["might", "have"], "must've": ["must", "have"],
    "gonna": ["going", "to"], "wanna": ["want", "to"], "gotta": ["got", "to"], "kinda": ["kind", "of"],
    "sorta": ["sort", "of"], "lemme": ["let", "me"], "gimme": ["give", "me"], "dunno": ["do", "not", "know"],
    "outta": ["out", "of"], "lotta": ["lot", "of"], "y'all": ["you", "all"], "'cause": ["because"],
    "cuz": ["because"], "'em": ["them"], "'til": ["until"], "till": ["until"], "'bout": ["about"],
    "ok": ["okay"], "o.k": ["okay"], "alright": ["all", "right"], "whaddya": ["what", "do", "you"],
    "gotcha": ["got", "you"], "ya": ["you"], "c'mon": ["come", "on"], "ma'am": ["madam"],
    "mr": ["mister"], "mrs": ["missus"], "ms": ["miss"], "dr": ["doctor"],
}

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
ORD = {"1st": "first", "2nd": "second", "3rd": "third", "4th": "fourth", "5th": "fifth", "6th": "sixth",
       "7th": "seventh", "8th": "eighth", "9th": "ninth", "10th": "tenth", "20th": "twentieth", "30th": "thirtieth"}


def num_words(n: int):
    if n < 20:
        return [ONES[n]]
    if n < 100:
        return [TENS[n // 10]] + ([ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        rest = n % 100
        return [ONES[n // 100], "hundred"] + (num_words(rest) if rest else [])
    if n < 10000 and n % 100 == 0 and 1100 <= n <= 9900 and n % 1000:
        return num_words(n // 100) + ["hundred"]
    if n < 1000000:
        rest = n % 1000
        return num_words(n // 1000) + ["thousand"] + (num_words(rest) if rest else [])
    return [str(n)]


_QUOTES = str.maketrans({"’": "'", "‘": "'", "`": "'", "“": '"', "”": '"', "…": ".", "–": "-", "—": "-"})


def norm_quotes(s: str) -> str:
    """Quote/dash normalisation that keeps every character position (spans stay valid)."""
    return s.translate(_QUOTES)


def words_with_spans(text: str):
    t = norm_quotes(text)
    return [(m.group(0), m.start(), m.end()) for m in WORD_RE.finditer(t)]


def canon_word(w: str, nxt: str = ""):
    """Canonical pieces for one surface word."""
    lw = norm_quotes(w).lower().strip("'") if not w.startswith(("'", "’")) else norm_quotes(w).lower()
    if lw in CONTRACTIONS:
        return list(CONTRACTIONS[lw])
    if lw in ORD:
        return [ORD[lw]]
    m = re.fullmatch(r"(\w+)'s", lw)
    if m:
        base = m.group(1)
        if re.fullmatch(_PRON, base):
            return [base, "has" if nxt in ("been", "got", "gotten") else "is"]
        return [base]  # possessive: John's -> john
    m = re.fullmatch(r"(\w+)'d", lw)
    if m:
        return [m.group(1), "had" if nxt in ("been", "better", "gotten") else "would"]
    m = re.fullmatch(r"(\w+)'ll", lw)
    if m:
        return [m.group(1), "will"]
    m = re.fullmatch(r"(\w+)'ve", lw)
    if m:
        return [m.group(1), "have"]
    m = re.fullmatch(r"(\w+)'re", lw)
    if m:
        return [m.group(1), "are"]
    if lw.isdigit():
        try:
            return num_words(int(lw))
        except (ValueError, IndexError):
            return [lw]
    if lw in ("yep", "yup"):
        return ["yeah"]
    if lw in ("okay",):
        return ["okay"]
    return [lw.replace("'", "")]


def canon_seq(text: str):
    """Return (pieces, owners, surface_words) where owners[k] = index of surface word."""
    surf = words_with_spans(text)
    pieces, owners = [], []
    for i, (w, _, _) in enumerate(surf):
        nxt = surf[i + 1][0].lower() if i + 1 < len(surf) else ""
        for p in canon_word(w, nxt):
            pieces.append(p)
            owners.append(i)
    return pieces, owners, surf


def _near(a: str, b: str) -> bool:
    if a == b:
        return True
    if min(len(a), len(b)) < 3:
        return False
    r = difflib.SequenceMatcher(None, a, b).ratio()
    return r >= (0.72 if max(len(a), len(b)) >= 6 else 0.8)


def align(ref_text: str, hyp_text: str):
    """Compare what was said/typed (hyp) against the reference line."""
    rp, ro, rs = canon_seq(ref_text)
    hp, ho, hs = canon_seq(hyp_text)
    rstat = ["miss"] * len(rp)
    hstat = ["extra"] * len(hp)
    sm = difflib.SequenceMatcher(None, rp, hp, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                rstat[i1 + k] = "hit"
                hstat[j1 + k] = "hit"
        elif tag == "replace":
            used = set()
            for i in range(i1, i2):
                for j in range(j1, j2):
                    if j in used:
                        continue
                    if _near(rp[i], hp[j]):
                        rstat[i] = "near"
                        hstat[j] = "near"
                        used.add(j)
                        break
                    # spacing mistakes: "some thing" for "something"
                    if j + 1 < j2 and (j + 1) not in used and hp[j] + hp[j + 1] == rp[i]:
                        rstat[i] = "near"
                        hstat[j] = hstat[j + 1] = "near"
                        used.update((j, j + 1))
                        break
                    if i + 1 < i2 and rp[i] + rp[i + 1] == hp[j]:
                        rstat[i] = rstat[i + 1] = "near"
                        hstat[j] = "near"
                        used.add(j)
                        break
    # surface-level status for the reference words
    ref_words = []
    for si, (w, a, b) in enumerate(rs):
        sts = [rstat[k] for k in range(len(rp)) if ro[k] == si]
        if not sts:
            st = "hit"
        elif all(s == "hit" for s in sts):
            st = "hit"
        elif all(s == "miss" for s in sts):
            st = "miss"
        else:
            st = "near"
        ref_words.append({"w": w, "s": st, "a": a, "b": b})
    hyp_words = []
    for si, (w, a, b) in enumerate(hs):
        sts = [hstat[k] for k in range(len(hp)) if ho[k] == si]
        st = "hit" if sts and all(s == "hit" for s in sts) else ("extra" if sts and all(s == "extra" for s in sts) else "near")
        hyp_words.append({"w": w, "s": st})
    total = max(1, len(rp))
    hits = rstat.count("hit")
    near = rstat.count("near")
    extras = hstat.count("extra")
    score = (hits + 0.6 * near) / total - 0.2 * min(extras, total) / total
    score = max(0.0, min(1.0, score))
    return {
        "ref": ref_words,
        "hyp": hyp_words,
        "score": round(score, 3),
        "hits": hits,
        "near": near,
        "total": total,
        "extras": extras,
        "missed": [ref_words[i]["w"] for i in range(len(ref_words)) if ref_words[i]["s"] == "miss"],
    }


def word_count(text: str) -> int:
    return len(words_with_spans(text))


def find_span(line: str, expr: str):
    """Locate expr inside line (case/punctuation-insensitive). Returns (start, end) chars or None."""
    if not expr or not line:
        return None
    lw = words_with_spans(line)
    ew = [w.lower() for w, _, _ in words_with_spans(expr)]
    if not ew or not lw:
        return None
    low = [w.lower() for w, _, _ in lw]
    n = len(ew)
    for i in range(len(low) - n + 1):
        if low[i:i + n] == ew:
            return (lw[i][1], lw[i + n - 1][2])
    # fuzzy: best window of similar length
    best, best_r = None, 0.0
    target = " ".join(ew)
    for size in range(max(1, n - 2), min(len(low), n + 2) + 1):
        for i in range(len(low) - size + 1):
            cand = " ".join(low[i:i + size])
            r = difflib.SequenceMatcher(None, target, cand).ratio()
            if r > best_r:
                best_r, best = r, (lw[i][1], lw[i + size - 1][2])
    return best if best_r >= 0.75 else None


def has_hangul(s: str) -> bool:
    return bool(re.search(r"[가-힣]", s or ""))
