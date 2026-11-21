"""Line analysis: Python features + local-AI judgement of which lines and expressions
are worth practising for interviews and meetings."""
import logging
import math
import re

from . import ollama, speech_rules, textutil
from .speech_rules import CATEGORIES

log = logging.getLogger("englearn")
DEPTH = {"quick": 60, "normal": 120, "deep": 250}
BATCH = 8


# ---------------------------------------------------------------- features
def features(line):
    text = line["text"]
    n = textutil.word_count(text)
    words = line.get("words")
    if words:
        dur = max(0.4, words[-1][2] - words[0][1])
    else:
        dur = max(0.4, (line["end"] - line["start"]) * 0.92)
    wps = n / dur
    red = speech_rules.reduction_count(text)
    if wps < 2.2 and n <= 8 and red == 0:
        level = 1
    elif wps > 3.2 or n > 16 or red >= 2:
        level = 3
    else:
        level = 2
    tags = speech_rules.function_tags(text)
    line["n_words"] = n
    line["wps"] = round(wps, 2)
    line["level"] = level
    line["tags"] = tags
    line["rule"] = speech_rules.rule_score(text, n, tags)
    return line


def add_features(lines):
    for ln in lines:
        features(ln)
    # Speed levels relative to this movie: subtitle timing styles differ a lot between files,
    # so "fast" means fast compared with the rest of the same movie.
    rates = sorted(l["wps"] for l in lines if l["n_words"] >= 3)
    if len(rates) >= 9:
        p33, p67 = rates[len(rates) // 3], rates[(2 * len(rates)) // 3]
        for l in lines:
            red = speech_rules.reduction_count(l["text"])
            if l["wps"] >= p67 or l["n_words"] > 18 or red >= 3:
                l["level"] = 3
            elif l["wps"] <= p33 and l["n_words"] <= 10:
                l["level"] = 1
            else:
                l["level"] = 2
    # preliminary picks before the AI has run: best 30 by rules
    ranked = sorted((l for l in lines if 4 <= l["n_words"] <= 20), key=lambda l: -l["rule"])
    top = {l["id"] for l in ranked[:30]}
    for l in lines:
        l["pre_key"] = l["id"] in top
    return lines


def candidates(lines, depth="normal"):
    n = DEPTH.get(depth, 120)
    pool = [l for l in lines if 3 <= l.get("n_words", 0) <= 26]
    if len(pool) <= n:
        return sorted(l["id"] for l in pool)
    chosen = set()
    if pool:
        t0, t1 = pool[0]["start"], pool[-1]["end"]
        parts = 10
        per = max(1, math.ceil(n * 0.3 / parts))
        span = max(1.0, (t1 - t0) / parts)
        for k in range(parts):
            bucket = [l for l in pool if t0 + k * span <= l["start"] < t0 + (k + 1) * span]
            bucket.sort(key=lambda l: -l["rule"])
            for l in bucket[:per]:
                chosen.add(l["id"])
    for l in sorted(pool, key=lambda l: -l["rule"]):
        if len(chosen) >= n:
            break
        chosen.add(l["id"])
    return sorted(chosen)


# ---------------------------------------------------------------- AI batch
SYS_BATCH = """You are an English speaking coach for Korean adults whose goal is to handle simple job interviews and work meetings in English.
You will see numbered lines from a movie. For EACH line return one item:
- "n": the line number.
- "useful": 0 to 3. 3 = can be reused in interviews or meetings (polite requests, opinions, agreeing or disagreeing politely, asking to clarify, talking about experience or plans). 2 = useful in everyday conversation. 1 = only fits this movie, or casual slang. 0 = not useful (names only, rude words, fragments).
- "expr": the most reusable chunk of the line, copied EXACTLY from the line, 2 to 8 words. Use "" when useful is 0.
- "expr_ko": the natural Korean meaning of expr.
- "cat": one of clarify, opinion, agree, disagree, request, suggest, experience, plan, thanks, apology, feeling, smalltalk, other.
%s
Return JSON only, like {"items": [{"n": 1, ...}]}."""
KO_FIELD = '- "ko": a natural Korean translation of the whole line.'


def _batch_schema(with_ko):
    props = {"n": {"type": "integer"}, "useful": {"type": "integer"}, "expr": {"type": "string"},
             "expr_ko": {"type": "string"}, "cat": {"type": "string", "enum": list(CATEGORIES)}}
    if with_ko:
        props["ko"] = {"type": "string"}
    return {"type": "object", "required": ["items"],
            "properties": {"items": {"type": "array", "items": {"type": "object", "properties": props,
                                                                  "required": list(props)}}}}


def ai_batch(batch, should_stop=None):
    with_ko = any(not l.get("ko") for l in batch)
    rows = []
    for i, l in enumerate(batch, 1):
        rows.append(f"{i}. {l['text'].replace(chr(10), ' ')}")
        if l.get("ko"):
            rows.append(f"   (Korean subtitle: {l['ko']})")
    msgs = [{"role": "system", "content": SYS_BATCH % (KO_FIELD if with_ko else "")},
            {"role": "user", "content": "\n".join(rows)}]
    data = ollama.chat_json(msgs, _batch_schema(with_ko), temperature=0.2, num_predict=160 * len(batch) + 200,
                            should_stop=should_stop, interactive=False)
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ollama.OllamaError("AI 답에 items가 없어요.")
    results = {}
    nums = []
    for it in items:
        try:
            nums.append(int(it.get("n")))
        except (TypeError, ValueError, AttributeError):
            pass
    shift = 1 if (0 in nums and len(batch) not in nums) else 0  # model counted from 0
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            n = int(it.get("n")) + shift
        except (TypeError, ValueError):
            continue
        if not 1 <= n <= len(batch) or n in results:
            continue
        line = batch[n - 1]
        try:
            useful = max(0, min(3, int(it.get("useful", 0))))
        except (TypeError, ValueError):
            useful = 0
        expr = _accept_expr(str(it.get("expr") or ""), line["text"])
        expr_ko = str(it.get("expr_ko") or "").strip()
        if not textutil.has_hangul(expr_ko):
            expr_ko = ""
        cat = it.get("cat") if it.get("cat") in CATEGORIES else "other"
        res = {"useful": useful, "expr": expr, "expr_ko": expr_ko if expr else "", "cat": cat}
        ko = str(it.get("ko") or "").strip()
        if ko and textutil.has_hangul(ko) and not line.get("ko"):
            res["ko"] = ko
        results[n - 1] = res
    return results


def _accept_expr(expr, text):
    """Keep the model's expression if it is (nearly) in the line, or a dictionary form of it."""
    expr = expr.strip().strip('"“”').strip()
    if not expr or textutil.has_hangul(expr):
        return ""
    span = textutil.find_span(text, expr)
    if span:
        out = text[span[0]:span[1]]
    else:
        ew = [w.lower() for w, _, _ in textutil.words_with_spans(expr)]
        lw = {w.lower() for w, _, _ in textutil.words_with_spans(text)}
        if 2 <= len(ew) <= 8 and sum(w in lw for w in ew) / len(ew) >= 0.6:
            out = expr.rstrip(".?!,")  # e.g. "be in charge of" for "I was in charge of ..."
        else:
            out = ""
    if out and textutil.word_count(out) > 12:
        out = ""
    if not out:
        log.info("expression not used: %r | line: %r", expr, text)
    return out


def mark_keys(lines):
    for l in lines:
        ai = l.get("ai") or {}
        l["key"] = bool(ai.get("useful", 0) >= 2 and ai.get("expr"))
    return lines


def analyze(lines, ids, on_progress=None, cancel=None, on_save=None, log=None):
    """Run the AI over the chosen line ids (skips lines already done)."""
    todo = [i for i in ids if not lines[i].get("ai")]
    done_before = len(ids) - len(todo)
    queue = [todo[k:k + BATCH] for k in range(0, len(todo), BATCH)]
    finished = done_before
    fails = 0
    while queue:
        if cancel and cancel():
            return False
        b = queue.pop(0)
        ollama.gate.wait_turn(cancel)
        if cancel and cancel():
            return False
        batch = [lines[i] for i in b]
        try:
            res = ai_batch(batch, should_stop=lambda: ollama.gate.busy() or (cancel and cancel()))
        except ollama.Preempted:
            queue.insert(0, b)
            continue
        except ollama.OllamaError as e:
            if "연결할 수 없어요" in str(e) or "HTTP 404" in str(e):
                raise
            fails += 1
            if log:
                log(f"AI 묶음 실패({len(b)}줄): {e}")
            if len(b) > 1:
                half = len(b) // 2
                queue[0:0] = [b[:half], b[half:]]
                continue
            lines[b[0]]["ai"] = {"useful": 0, "expr": "", "expr_ko": "", "cat": "other", "failed": True}
            finished += 1
            continue
        missing = []
        for k, idx in enumerate(b):
            r = res.get(k)
            if r is None:
                missing.append(idx)
                continue
            ko = r.pop("ko", None)
            if ko:
                lines[idx]["ko"] = ko
                lines[idx]["ko_src"] = "ai"
            lines[idx]["ai"] = r
            finished += 1
        if missing:
            if len(missing) < len(b):
                queue.insert(0, missing)  # retry only the lines the model skipped
            elif len(b) > 1:
                half = len(b) // 2
                queue[0:0] = [missing[:half], missing[half:]]
            else:
                lines[b[0]]["ai"] = {"useful": 0, "expr": "", "expr_ko": "", "cat": "other", "failed": True}
                finished += 1
        mark_keys(lines)
        if on_save:
            on_save(lines)
        if on_progress:
            on_progress(finished / max(1, len(ids)))
    mark_keys(lines)
    if on_save:
        on_save(lines)
    return True


# ---------------------------------------------------------------- expressions
def expressions(lines):
    seen = {}
    out = []
    for l in lines:
        ai = l.get("ai") or {}
        e = ai.get("expr")
        if not e or ai.get("useful", 0) < 2:
            continue
        k = re.sub(r"[^a-z' ]", "", e.lower()).strip()
        if k in seen:
            seen[k]["lines"].append(l["id"])
            continue
        item = {"id": f"e{l['id']}", "text": e, "ko": ai.get("expr_ko", ""), "cat": ai.get("cat", "other"),
                "useful": ai.get("useful", 0), "line": l["id"], "lines": [l["id"]]}
        seen[k] = item
        out.append(item)
    return out


SYS_TUTOR = ("You are a friendly English tutor for Korean adults preparing for job interviews and work meetings. "
             "Write Korean explanations in natural, polite Korean (해요체). Keep everything short and practical. Return JSON only.")


def explain_line(line):
    schema = {"type": "object", "required": ["ko", "points", "nuance_ko", "example_en", "example_ko"],
              "properties": {
                  "ko": {"type": "string"},
                  "points": {"type": "array", "items": {"type": "object", "required": ["en", "ko"],
                                                         "properties": {"en": {"type": "string"}, "ko": {"type": "string"}}}},
                  "nuance_ko": {"type": "string"},
                  "example_en": {"type": "string"},
                  "example_ko": {"type": "string"}}}
    ko = f"\nKorean subtitle: {line['ko']}" if line.get("ko") else ""
    user = (f"Movie line: \"{line['text']}\"{ko}\n\n"
            "Return:\n"
            "- \"ko\": a natural Korean translation of the line.\n"
            "- \"points\": 1 to 3 useful expressions copied from the line, each with its Korean meaning.\n"
            "- \"nuance_ko\": one or two Korean sentences about tone or grammar (for example: polite or casual, when people say it).\n"
            "- \"example_en\": one natural sentence (max 20 words) using one of the expressions in a job interview or work meeting.\n"
            "- \"example_ko\": Korean meaning of example_en.")
    data = ollama.chat_json([{"role": "system", "content": SYS_TUTOR}, {"role": "user", "content": user}],
                            schema, temperature=0.3, num_predict=600)
    pts = []
    for p in data.get("points") or []:
        if isinstance(p, dict) and p.get("en"):
            pts.append({"en": str(p["en"]).strip(), "ko": str(p.get("ko") or "").strip()})
    out = {"ko": str(data.get("ko") or "").strip(), "points": pts[:3],
           "nuance_ko": str(data.get("nuance_ko") or "").strip(),
           "example_en": str(data.get("example_en") or "").strip(),
           "example_ko": str(data.get("example_ko") or "").strip()}
    if textutil.has_hangul(out["example_en"]):
        out["example_en"] = ""
    return out


EX_SCHEMA = {"type": "object", "required": ["example_en", "example_ko", "when_ko", "caution_ko"],
             "properties": {"example_en": {"type": "string"}, "example_ko": {"type": "string"},
                            "when_ko": {"type": "string"}, "caution_ko": {"type": "string"}}}


def make_example(expr, line_text, interactive=True, should_stop=None):
    user = (f"Expression: \"{expr}\"\nFrom the movie line: \"{line_text}\"\n\n"
            "Return:\n"
            "- \"example_en\": one natural sentence (max 20 words) that uses this expression in a job interview or a work meeting.\n"
            "- \"example_ko\": the Korean meaning of example_en.\n"
            "- \"when_ko\": when to use this expression, in one short Korean sentence.\n"
            "- \"caution_ko\": if it is too casual or rude for an interview, a short Korean warning with a politer option; otherwise \"\".")
    data = ollama.chat_json([{"role": "system", "content": SYS_TUTOR}, {"role": "user", "content": user}],
                            EX_SCHEMA, temperature=0.5, num_predict=350, interactive=interactive,
                            should_stop=should_stop)
    out = {k: str(data.get(k) or "").strip() for k in EX_SCHEMA["properties"]}
    if textutil.has_hangul(out["example_en"]):
        out["example_en"] = ""
    return out


CHECK_SCHEMA = {"type": "object", "required": ["natural", "corrected", "feedback_ko"],
                "properties": {"natural": {"type": "boolean"}, "corrected": {"type": "string"},
                               "feedback_ko": {"type": "string"}}}


def check_sentence(expr, meaning, said):
    user = (f"The learner practised the expression \"{expr}\" ({meaning}).\n"
            f"The learner said: \"{said}\"\n(This text came from speech recognition, so ignore small punctuation issues.)\n\n"
            "Return:\n"
            "- \"natural\": true if the sentence is correct and natural English.\n"
            "- \"corrected\": a corrected, natural version that keeps the learner's meaning and uses the expression.\n"
            "- \"feedback_ko\": one or two short Korean sentences: what is good and what to fix.")
    data = ollama.chat_json([{"role": "system", "content": SYS_TUTOR}, {"role": "user", "content": user}],
                            CHECK_SCHEMA, temperature=0.3, num_predict=300)
    used = bool(textutil.find_span(said, expr))
    return {"natural": bool(data.get("natural")), "corrected": str(data.get("corrected") or "").strip(),
            "feedback_ko": str(data.get("feedback_ko") or "").strip(), "used_expr": used}
