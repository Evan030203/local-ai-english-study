"""Interview / meeting role-play with the local AI.

Each scenario has planned questions so even small models keep a good structure;
the AI reacts, gives Korean feedback, a more natural answer, and asks the next question.
"""
import difflib
import logging
import random
import re
import time
import uuid

from . import ollama, paths, textutil
from .storage import read_json, write_json

log = logging.getLogger("englearn.roleplay")

SCENARIOS = {
    "interview_basic": {
        "title": "영어 면접: 자기소개와 기본 질문",
        "desc": "자기소개, 지원 동기, 강점, 팀워크, 마지막 질문까지 가장 자주 나오는 흐름이에요.",
        "role": "a friendly but professional hiring manager",
        "kind": "job interview",
        "me": "지원자", "ai": "면접관",
        "seeds": ["Thanks for coming in today. Could you briefly introduce yourself?",
                  "Why are you interested in this position?",
                  "What would you say is your greatest strength?",
                  "Can you tell me about a time you worked as part of a team?",
                  "What is one weakness you are working on?",
                  "Where do you see yourself in five years?",
                  "Do you have any questions for us?"],
        "close": "Thank you for your time today. We'll be in touch soon.",
    },
    "interview_behavior": {
        "title": "영어 면접: 경험·상황 질문",
        "desc": "어려웠던 일, 실수, 갈등, 압박 상황을 어떻게 해결했는지 묻는 질문이에요.",
        "role": "an experienced interviewer who asks behavioral questions",
        "kind": "job interview",
        "me": "지원자", "ai": "면접관",
        "seeds": ["Tell me about a challenge you faced and how you handled it.",
                  "Describe a time when you made a mistake. What did you learn?",
                  "How do you handle stress or tight deadlines?",
                  "Tell me about a time you disagreed with a teammate. What happened?",
                  "Give me an example of a goal you reached and how you did it.",
                  "Why should we hire you?"],
        "close": "That's all from me. Thank you, it was great talking with you.",
    },
    "meeting_update": {
        "title": "팀 미팅: 진행 상황 보고",
        "desc": "내 업무 진행 상황, 문제점, 필요한 도움, 일정을 짧게 보고하는 연습이에요.",
        "role": "a team manager leading a weekly team meeting",
        "kind": "weekly team meeting",
        "me": "팀원", "ai": "팀장",
        "seeds": ["Okay, let's get started. Could you give us a quick update on your work?",
                  "Are there any problems or risks we should know about?",
                  "What do you need from the team to move forward?",
                  "When do you think it will be finished?",
                  "Is there anything else you'd like to add before we wrap up?"],
        "close": "Great, thanks for the update. Let's talk again next week.",
    },
    "meeting_discuss": {
        "title": "팀 미팅: 의견 내고 조율하기",
        "desc": "아이디어 제안, 정중하게 반대하기, 결정 정리하기를 연습해요.",
        "role": "a colleague in a meeting who discusses a problem and sometimes politely disagrees",
        "kind": "team meeting to solve a problem",
        "me": "나", "ai": "동료",
        "seeds": ["We need to reduce delays in our project. What do you think we should do?",
                  "Interesting. But wouldn't that take too much time? How would you handle that?",
                  "What if the other team doesn't agree with this plan?",
                  "Okay. Can you summarize what we decided today?",
                  "Who should take care of the next steps, and by when?"],
        "close": "Sounds like a plan. Thanks, that was a productive meeting.",
    },
    "schedule": {
        "title": "일정 잡기·부탁하기",
        "desc": "회의 시간 정하기, 자료 부탁하기, 일정 바꾸기 같은 짧은 업무 대화예요.",
        "role": "a coworker from another department",
        "kind": "short work conversation about scheduling and requests",
        "me": "나", "ai": "동료",
        "seeds": ["Hi, do you have a minute? I wanted to talk about our next meeting.",
                  "Would Thursday afternoon work for you?",
                  "Could you send me the documents before the meeting?",
                  "Sorry, something came up. Can we move the meeting to next week?",
                  "Great. Is there anything else before we wrap up?"],
        "close": "Perfect. See you then, and thanks for your help.",
    },
    "smalltalk": {
        "title": "회의 전 스몰토크",
        "desc": "처음 만난 사람과 날씨, 주말, 일 이야기로 가볍게 대화를 이어가요.",
        "role": "a friendly coworker you meet before a meeting starts",
        "kind": "small talk before a meeting",
        "me": "나", "ai": "동료",
        "seeds": ["Hi! I don't think we've met. I'm Alex from the marketing team.",
                  "How's your day going so far?",
                  "Did you do anything fun over the weekend?",
                  "How long have you been working here?",
                  "Oh, I think the meeting is about to start. Shall we go in?"],
        "close": "It was nice talking with you. Let's grab a coffee sometime.",
    },
    "custom": {
        "title": "내가 정하는 상황",
        "desc": "원하는 상황을 직접 적으면 AI가 그 상황에 맞춰 질문해요.",
        "role": "the other person in the situation",
        "kind": "conversation",
        "me": "나", "ai": "상대",
        "seeds": [],
        "close": "Thank you. That's all for today.",
    },
}

VOICE = {"interview_basic": "af_heart", "interview_behavior": "am_michael", "meeting_update": "bf_emma",
         "meeting_discuss": "bm_george", "schedule": "af_bella", "smalltalk": "am_fenrir", "custom": "af_heart"}
RATE = {"easy": 0.85, "normal": 0.95, "real": 1.02}

LEVELS = {
    "easy": "Use short, simple sentences (max 12 words per sentence) and very common words.",
    "normal": "Use natural, everyday spoken English with a few useful expressions.",
    "real": "Speak like a real person in this situation at a natural pace; you may ask a follow-up question.",
}

def _str_schema(*keys):
    return {"type": "object", "required": list(keys), "properties": {k: {"type": "string"} for k in keys}}


# Self-describing keys help small local models put the right kind of text in each field.
TURN_SCHEMA = _str_schema("improved_answer_first_person", "feedback_in_korean", "short_reaction",
                          "your_question", "movie_expression")
FIX_SCHEMA = _str_schema("improved_answer_first_person", "feedback_in_korean")
FIRST_SCHEMA = _str_schema("greeting_and_first_question")
INTERVIEWS = {"interview_basic", "interview_behavior"}
FIRST_PERSON = {"i", "i'm", "i've", "i'd", "i'll", "my", "me", "mine", "myself",
                "we", "we're", "we've", "we'll", "our", "us"}
ASK_START = re.compile(r"(what|when|where|who|which|how|why|is|are|am|do|does|did|can|could|would|will|"
                       r"should|may|shall|have|has)\b", re.I)
LEAD_FILLER = re.compile(r"^(okay|ok|great|interesting|oh|perfect|alright|all right|right)[.,!]\s+", re.I)
CANNED = ["I see.", "Thank you.", "Got it.", "Okay.", "Thanks."]

SUM_SCHEMA = {"type": "object", "required": ["overall_ko", "good_ko", "improve_ko", "phrases"],
              "properties": {"overall_ko": {"type": "string"},
                             "good_ko": {"type": "array", "items": {"type": "string"}},
                             "improve_ko": {"type": "array", "items": {"type": "string"}},
                             "phrases": {"type": "array", "items": {
                                 "type": "object", "required": ["en", "ko"],
                                 "properties": {"en": {"type": "string"}, "ko": {"type": "string"}}}}}}


def scenario_list():
    return [{"id": k, "title": v["title"], "desc": v["desc"], "me": v["me"], "ai": v["ai"]}
            for k, v in SCENARIOS.items()]


def _path(sid):
    return paths.ROLEPLAY_DIR / f"{sid}.json"


def save(sess):
    write_json(_path(sess["id"]), sess)


def load(sid):
    if not re.fullmatch(r"[\w\-]+", sid or ""):
        return None
    return read_json(_path(sid))


def delete(sid):
    sess = load(sid)
    if not sess:
        return False
    _path(sid).unlink(missing_ok=True)
    return True


def history(limit=30):
    out = []
    for p in sorted(paths.ROLEPLAY_DIR.glob("*.json"), reverse=True)[:limit]:
        s = read_json(p)
        if s:
            out.append({"id": s["id"], "title": s.get("title"), "created": s.get("created"),
                        "answers": sum(1 for t in s.get("turns", []) if t["role"] == "me"),
                        "done": s.get("done"), "model": s.get("model", "")})
    return out


def _model():
    try:
        return ollama.pick_model()
    except ollama.OllamaError:
        return ""


def _system(sess):
    sc = SCENARIOS[sess["scenario"]]
    prof = sess.get("profile") or {}
    bits = []
    if prof.get("job"):
        bits.append(f"The learner is applying for or works as: {prof['job']}.")
    if prof.get("company"):
        bits.append(f"Company or field: {prof['company']}.")
    if prof.get("background"):
        bits.append(f"Learner background: {prof['background']}.")
    if sess["scenario"] == "custom" and sess.get("custom"):
        bits.append(f"Situation described by the learner (may be in Korean): {sess['custom']}")
    exprs = sess.get("exprs") or []
    expr_line = ("Movie expressions the learner is studying: " + "; ".join(f'"{e}"' for e in exprs[:12])) \
        if exprs else "There is no movie expression list, so use \"\" for movie_expression."
    return (f"You are {sc['role']}. You are having a {sc['kind']} in English with a Korean learner of English.\n"
            + (" ".join(bits) + "\n" if bits else "")
            + f"Language level for what you say: {LEVELS.get(sess.get('level'), LEVELS['normal'])}\n"
            "Each time the learner answers, reply in JSON with these fields:\n"
            "- improved_answer_first_person: the learner's answer rewritten as natural spoken English, "
            "as the learner would say it (I, my). Keep their facts and meaning; fix grammar and word choice. "
            "1-3 sentences, max 45 words. If they answered in Korean, say it in natural English. "
            "English only, and do not talk to the learner here.\n"
            "- feedback_in_korean: 1-2 short sentences written in Korean (해요체) for the learner: one good point "
            "and one concrete fix with the English words in quotes, e.g. \"경험을 구체적으로 말해서 좋아요. "
            "'I very like it' 대신 'I really like it'이라고 하면 더 자연스러워요.\" Always talk about the English. "
            "If they answered in Korean, encourage them and show one key English phrase for what they meant.\n"
            "- short_reaction: what you say right after hearing the answer, in your role: one short natural "
            "sentence (max 15 words) about what they said. If they asked or suggested something, respond to it. "
            "No question here.\n"
            "- your_question: follow the instruction in the latest message.\n"
            "- movie_expression: one expression from the movie list below that would fit their answer, "
            "copied exactly, or \"\".\n"
            + expr_line)


def start(scenario, level="normal", n_questions=5, profile=None, project_id=None, exprs=None, custom=""):
    if scenario not in SCENARIOS:
        scenario = "interview_basic"
    sc = SCENARIOS[scenario]
    seeds = list(sc["seeds"])
    n_questions = max(2, min(int(n_questions or 5), 10))
    if seeds:
        first, rest = seeds[0], seeds[1:]
        if len(rest) > n_questions - 1:
            # keep the last planned question (usually a natural ending), sample the middle
            middle = rest[:-1]
            keep = sorted(random.sample(range(len(middle)), max(0, n_questions - 2)))
            rest = [middle[i] for i in keep] + [rest[-1]]
        plan = [first] + rest
    else:
        plan = []
    sess = {
        "id": time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4],
        "scenario": scenario, "title": sc["title"], "level": level, "n": n_questions,
        "profile": profile or {}, "project": project_id, "exprs": exprs or [], "custom": custom or "",
        "plan": plan, "turns": [], "asked": 0, "done": False, "summary": None, "created": time.time(),
        "me": sc["me"], "ai": sc["ai"], "followups": 0, "fu_for": -1,
        "voice": VOICE.get(scenario, "af_heart"), "rate": RATE.get(level, 0.95), "model": _model(),
    }
    if plan:
        first_q = plan[0]
    else:
        msgs = [{"role": "system", "content": _system(sess)},
                {"role": "user", "content": "Start the conversation now: greet the learner in one short sentence "
                                            "and ask your first question. Reply in JSON only."}]
        data = ollama.chat_json(msgs, FIRST_SCHEMA, temperature=0.6, num_predict=200)
        first_q = _clean(data.get("greeting_and_first_question"))
        if not first_q or textutil.has_hangul(first_q) or "?" not in first_q:
            first_q = "Hi! Thanks for joining. Could you tell me a little about yourself?"
    sess["turns"].append({"role": "ai", "text": first_q, "t": time.time()})
    sess["asked"] = 1
    save(sess)
    return sess


# ---------- checking what a small model returns ----------

def _clean(s):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    if len(s) >= 2 and s[0] in "\"'“" and s[-1] in "\"'”":
        s = s[1:-1].strip()
    return s


def _words(s):
    return re.findall(r"[a-z']+", (s or "").lower().replace("’", "'"))


def _hangul_count(s):
    return sum(1 for ch in s or "" if "가" <= ch <= "힣")


def _sentences(s):
    return [x.strip() for x in re.split(r"(?<=[.!?])\s+", s or "") if x.strip()]


def _limit_words(s, n):
    out, total = [], 0
    for sent in _sentences(s):
        w = len(sent.split())
        if out and total + w > n:
            break
        out.append(sent)
        total += w
    res = " ".join(out)
    words = res.split()
    if len(words) > n + 10:
        res = " ".join(words[:n]).rstrip(",;:-") + "."
    return res


def _similar(a, b):
    a, b = " ".join(_words(a)), " ".join(_words(b))
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def _asks(text):
    t = (text or "").strip()
    return "?" in t or any(ASK_START.match(x) for x in _sentences(t))


SECOND_PERSON = {"you", "your", "you're", "you've", "you'll", "you'd", "yours", "yourself"}
POLITE_YOU = re.compile(r"\b(thank you|thanks to you|you know|see you|nice to meet you|meet you)\b", re.I)


def _you(text):
    return bool(set(_words(POLITE_YOU.sub(" ", text or ""))) & SECOND_PERSON)


def _good_better(better, question, answer):
    """A rewrite of the learner's answer, not the partner talking back to the learner."""
    if not better or textutil.has_hangul(better):
        return False
    if len(_words(better)) < 2:
        return False
    if _asks(answer):
        return True  # the learner asked something, so a question in the rewrite is fine
    if better.rstrip().endswith("?"):
        return False
    if _you(better) and not _you(answer):
        return False  # "I see you're passionate about..." is the partner talking, not the learner
    return _similar(better, question) < 0.8


def _good_ko(text):
    return _hangul_count(text) >= 8


def _reaction(raw, last):
    raw = _clean(raw)
    if not raw or textutil.has_hangul(raw):
        return ""
    keep = [x for x in _sentences(raw) if not x.endswith("?")]
    if not last:
        keep = keep[:1]  # a second sentence tends to announce a topic the planned question does not follow
    return _limit_words(" ".join(keep), 40 if last else 22)


def _question(raw, sess):
    q = _clean(raw)
    if not q or textutil.has_hangul(q) or not q.endswith("?"):
        return ""
    if not 3 <= len(q.split()) <= 30:
        return ""
    asked = [t["text"] for t in sess["turns"] if t["role"] == "ai"] + list(sess.get("plan") or [])
    if any(_similar(q, a) >= 0.75 for a in asked):
        return ""
    return q


STOP = {"that", "this", "with", "your", "you're", "we'll", "we're", "will", "would", "could", "have", "there",
        "what", "about", "from", "they", "them", "just", "really", "very", "let's", "lets", "it's"}


def _content(s):
    out = set()
    for w in _words(s):
        if len(w) < 4 or w in STOP:
            continue
        out.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return out


def _closing(reaction, close):
    """Leave out closing sentences that repeat what the reaction already said (e.g. two 'soon's)."""
    sents = _sentences(close)
    if not reaction or len(sents) < 2:
        return close
    said = _content(reaction)
    keep = [x for x in sents if not (_content(x) & said)]
    return " ".join(keep) if keep else sents[-1]


def _match_expr(tip, exprs):
    norm = lambda x: re.sub(r"\s+", " ", re.sub(r"[^a-z0-9' ]", " ", (x or "").lower().replace("’", "'"))).strip()
    t = norm(tip)
    if not t:
        return ""
    for e in exprs or []:
        en = norm(e)
        if not en:
            continue
        if t == en or (t in en and len(t) >= 0.6 * len(en)) or (en in t and len(en) >= 0.6 * len(t)):
            return e
    return ""


QUOTED = re.compile(r"['‘\"“]([^'’\"”]{1,80})['’\"”]")
FILLERS = {"hello", "hi", "um", "uh", "oh", "well", "so", "yeah", "yes", "okay", "ok"}


FB_TAG = re.compile(r"^\s*(\[[^\]]{1,12}\]|\((?:korean|한국어)\)|(?:korean|한국어|피드백|feedback)\s*[:：])\s*", re.I)


FB_TAG_ANY = re.compile(r"\s*(\[(?:한국어|korean|피드백|feedback)\]|\((?:한국어|korean)\))\s*", re.I)


def _clean_feedback(text):
    """Drop sentences that only compare Korean wordings: the learner needs advice about the English."""
    text = FB_TAG_ANY.sub(" ", FB_TAG.sub("", text or "")).strip()
    keep = []
    for sent in _sentences(text):
        quotes = QUOTED.findall(sent)
        if quotes and all(textutil.has_hangul(q) for q in quotes):
            continue
        keep.append(sent)
    return " ".join(keep)


def _fixes(answer, better, limit=2):
    """Word-level changes between the learner's answer and the improved one, e.g. 'I am student' → 'I am a student'."""
    if not answer or not better or textutil.has_hangul(answer):
        return []
    pa, oa, sa = textutil.canon_seq(answer)
    pb, ob, sb = textutil.canon_seq(better)
    if not pa or not pb:
        return []
    sm = difflib.SequenceMatcher(None, pa, pb, autojunk=False)
    if sm.ratio() < 0.45:
        return []  # a full rewrite: the improved answer itself is the lesson
    out, used = [], set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or set(pa[i1:i2] + pb[j1:j2]) <= FILLERS:
            continue
        if i2 - i1 > 8 or j2 - j1 > 8:
            continue
        if i1 == i2 or j1 == j2:  # insert / delete: show the next (or previous) word so the change has a place
            if i2 < len(pa) and j2 < len(pb):
                i2, j2 = i2 + 1, j2 + 1
            elif i1 > 0 and j1 > 0:
                i1, j1 = i1 - 1, j1 - 1
            else:
                continue
        while True:  # context pieces are equal on both sides: widen both to whole surface words
            if i1 > 0 and j1 > 0 and (oa[i1 - 1] == oa[i1] or ob[j1 - 1] == ob[j1]) and pa[i1 - 1] == pb[j1 - 1]:
                i1, j1 = i1 - 1, j1 - 1
            elif i2 < len(pa) and j2 < len(pb) and (oa[i2] == oa[i2 - 1] or ob[j2] == ob[j2 - 1]) \
                    and pa[i2] == pb[j2]:
                i2, j2 = i2 + 1, j2 + 1
            else:
                break
        wa = range(oa[i1], oa[i2 - 1] + 1) if i2 > i1 else range(0)
        wb = range(ob[j1], ob[j2 - 1] + 1) if j2 > j1 else range(0)
        a = " ".join(sa[k][0] for k in wa)
        b = " ".join(sb[k][0] for k in wb)
        if not a or not b or a.lower() == b.lower() or (wa.start, wa.stop) in used:
            continue
        used.add((wa.start, wa.stop))
        out.append({"from": a, "to": b})
        if len(out) >= limit:
            break
    return out


def _repair(question, answer, need_better, better, model=None):
    user = (f"Question: \"{question}\"\nLearner's answer: \"{answer}\"\n"
            + ("" if need_better or not better else f"More natural answer: \"{better}\"\n")
            + "\nReturn JSON:\n"
              "- improved_answer_first_person: the learner's answer rewritten as natural spoken English, "
              "as the learner says it (I, my), keeping their meaning. Max 45 words. English only.\n"
              "- feedback_in_korean: 1-2 short sentences in Korean (한국어, 해요체) for the learner: one good point "
              "and one concrete fix. It must be written in Korean.")
    try:
        return ollama.chat_json([{"role": "system", "content": "You are a kind English speaking coach for Korean "
                                                                "adults. Return JSON only."},
                                 {"role": "user", "content": user}], FIX_SCHEMA, temperature=0.3, num_predict=320,
                                model=model)
    except ollama.OllamaError as e:
        log.warning("roleplay repair failed: %s", e)
        return {}


def answer(sess, text):
    text = (text or "").strip()
    if not text:
        raise ValueError("답변이 비어 있어요.")
    sc = SCENARIOS[sess["scenario"]]
    last = sess["asked"] >= sess["n"]
    question = next((t["text"] for t in reversed(sess["turns"]) if t["role"] == "ai"), "")
    planned = sess["plan"][sess["asked"]] if (not last and sess["asked"] < len(sess["plan"])) else ""
    if last:
        q_line = ("This was the last question. In short_reaction, respond to their answer; if they asked you "
                  f"something, answer it in 1-2 short sentences. Then the app says \"{sc['close']}\", so do not "
                  "repeat that or say goodbye. Use \"\" for your_question.")
    elif planned:
        q_line = "your_question: one short follow-up question about a detail in the learner's answer."
    else:
        q_line = "your_question: your next question for this conversation, on something not asked before."
    msgs = [{"role": "system", "content": _system(sess)}]
    for t in sess["turns"]:
        msgs.append({"role": "assistant" if t["role"] == "ai" else "user", "content": t["text"]})
    msgs.append({"role": "user", "content": f"Learner's answer: \"{text}\"\n\n{q_line}\nReply in JSON only."})
    model = ollama.pick_model()
    data = ollama.chat_json(msgs, TURN_SCHEMA, temperature=0.4, num_predict=450, model=model)

    better = _limit_words(_clean(data.get("improved_answer_first_person")), 60)
    feedback = _clean(data.get("feedback_in_korean"))
    ok_better, ok_ko = _good_better(better, question, text), _good_ko(feedback)
    if not (ok_better and ok_ko):
        log.info("roleplay repair (better=%s, ko=%s)", ok_better, ok_ko)
        fix = _repair(question, text, not ok_better, better if ok_better else "", model)
        if not ok_better:
            cand = _limit_words(_clean(fix.get("improved_answer_first_person")), 60)
            ok_better = _good_better(cand, question, text)
            better = cand if ok_better else ""
        if not ok_ko:
            cand = _clean(fix.get("feedback_in_korean"))
            ok_ko = _good_ko(cand)
            feedback = cand if ok_ko else ""
    feedback = _clean_feedback(feedback)
    if textutil.has_hangul(text) and better and feedback and not re.search(r"[A-Za-z]{2,}", feedback):
        feedback += f" 영어로는 '{_sentences(better)[0]}'처럼 말할 수 있어요."
    if not _good_ko(feedback):
        feedback = ""
    if not feedback:
        if textutil.has_hangul(text):
            feedback = "영어로는 아래처럼 말할 수 있어요. 소리 내어 두세 번 따라 해 보세요." if better else \
                "다음 답은 짧게라도 영어로 말해 보세요."
        else:
            feedback = "잘 전달됐어요. 아래 문장을 소리 내어 따라 하면서 표현을 익혀 보세요." if better else \
                "잘 들었어요. 다음 질문에도 영어로 답해 보세요."
    tip = _match_expr(_clean(data.get("movie_expression")), sess.get("exprs"))
    if tip and any(((t.get("fb") or {}).get("tip_expr") or "").lower() == tip.lower() for t in sess["turns"]):
        tip = ""  # small models repeat one favourite; suggest each expression once

    reaction = _reaction(data.get("short_reaction"), last)
    answers = sum(1 for t in sess["turns"] if t["role"] == "me")
    follow = ""
    if planned and sess["scenario"] in INTERVIEWS and sess.get("level") != "easy" \
            and not textutil.has_hangul(text) and sess.get("followups", 0) < 2 \
            and sess.get("fu_for") != sess["asked"]:
        short = 8 if sess.get("level") == "normal" else 15
        if len(_words(text)) < short:
            follow = _question(data.get("your_question"), sess)
    if last:
        nxt = (reaction + " " if reaction else "") + _closing(reaction, sc["close"])
    else:
        q = follow or planned or _question(data.get("your_question"), sess) or \
            "Could you tell me a little more about that?"
        if reaction:
            q = LEAD_FILLER.sub("", q, count=1)
            q = q[:1].upper() + q[1:]
        else:
            reaction = CANNED[answers % len(CANNED)] if not LEAD_FILLER.match(q) else ""
        nxt = (reaction + " " if reaction else "") + q

    fb = {"feedback_ko": feedback, "better": better, "tip_expr": tip, "fixes": _fixes(text, better), "model": model}
    sess["model"] = model
    sess["turns"].append({"role": "me", "text": text, "fb": fb, "t": time.time()})
    sess["turns"].append({"role": "ai", "text": nxt, "t": time.time(), "follow_up": bool(follow)})
    if last:
        sess["done"] = True
    elif follow:
        sess["followups"] = sess.get("followups", 0) + 1
        sess["fu_for"] = sess["asked"]
    else:
        sess["asked"] += 1
    save(sess)
    return sess


def summarize(sess):
    rows = []
    q = None
    for t in sess["turns"]:
        if t["role"] == "ai":
            q = t["text"]
        else:
            rows.append(f"Q: {q}\nA (learner): {t['text']}\nBetter: {(t.get('fb') or {}).get('better', '')}")
    if not rows:
        raise ValueError("아직 답한 내용이 없어요.")
    user = ("Here is a practice conversation of a Korean learner.\n\n" + "\n\n".join(rows) +
            "\n\nReturn JSON:\n- \"overall_ko\": 2-3 Korean sentences summarising how they did.\n"
            "- \"good_ko\": 2 short Korean points they did well.\n"
            "- \"improve_ko\": 2-3 short Korean points to improve next time.\n"
            "- \"phrases\": 3-5 useful English phrases from the better answers to memorise, each with Korean meaning (\"en\", \"ko\").")
    model = ollama.pick_model()
    data = ollama.chat_json([{"role": "system", "content": "You are a kind English speaking coach for Korean adults. Return JSON only."},
                             {"role": "user", "content": user}], SUM_SCHEMA, temperature=0.3, num_predict=700,
                            model=model)
    phrases = [p for p in (data.get("phrases") or []) if isinstance(p, dict) and p.get("en")
               and not textutil.has_hangul(p.get("en"))]
    sess["summary"] = {
        "overall_ko": str(data.get("overall_ko") or "").strip(),
        "good_ko": [str(x) for x in (data.get("good_ko") or [])][:3],
        "improve_ko": [str(x) for x in (data.get("improve_ko") or [])][:4],
        "phrases": [{"en": str(p["en"]).strip(), "ko": str(p.get("ko") or "").strip()} for p in phrases][:6],
        "model": model,
    }
    sess["done"] = True
    save(sess)
    return sess
