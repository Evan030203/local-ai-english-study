"""Rule-based helpers that do not need the AI.

1. FUNCTION_PATTERNS: conversation functions (asking to repeat, giving opinions ...)
   used to rank movie lines for interview/meeting practice.
2. Connected-speech notes: reductions (gonna), flap T, linking, held T,
   same-consonant merging, weak function words — explained in Korean.
"""
import re

CATEGORIES = {
    "clarify": "되묻기·확인",
    "opinion": "의견 말하기",
    "agree": "동의·맞장구",
    "disagree": "반대·완곡하게",
    "request": "부탁·요청",
    "suggest": "제안",
    "experience": "경험·자기소개",
    "plan": "계획·일정",
    "thanks": "감사",
    "apology": "사과",
    "feeling": "감정·반응",
    "smalltalk": "인사·스몰토크",
    "other": "기타",
}

WEIGHTS = {"clarify": 1.2, "experience": 1.1, "opinion": 1.0, "request": 1.0, "suggest": 1.0,
           "disagree": 1.0, "plan": 0.9, "agree": 0.8, "smalltalk": 0.8, "thanks": 0.6,
           "apology": 0.6, "feeling": 0.4, "other": 0.0}

FUNCTION_PATTERNS = {
    "clarify": [r"what do you mean", r"what does (that|it) mean", r"(could|can|would) you (say|repeat|explain|clarify)",
                r"say (that|it) again", r"^sorry\?$", r"\bpardon\b", r"\byou mean\b", r"are you saying",
                r"so you're saying", r"if i understand", r"let me (get|make) (this|that|it) (straight|clear)",
                r"just to (be clear|clarify|confirm|make sure)", r"what was that", r"did you say", r"make sure i",
                r"in other words", r"what do you think"],
    "opinion": [r"\bi think\b", r"\bi believe\b", r"\bi feel like\b", r"\bi guess\b", r"in my opinion",
                r"the way i see it", r"if you ask me", r"to be honest", r"\bhonestly\b", r"\bpersonally\b",
                r"i'm (pretty |quite )?sure", r"\bi doubt\b", r"\bit seems\b", r"\bi'd say\b", r"\bi mean\b"],
    "agree": [r"\bi agree\b", r"\bexactly\b", r"that makes sense", r"fair enough", r"you're right",
              r"\b(good|fair|great|valid) point\b", r"\babsolutely\b", r"sounds (good|great|like a plan|fine)",
              r"\bme too\b", r"\bdefinitely\b", r"\bof course\b", r"\bi see\b", r"\bgot it\b",
              r"works for me", r"no problem", r"that's true", r"\bi know\b"],
    "disagree": [r"i'm not sure", r"i don't think", r"i see your point", r"i'm afraid", r"\bi disagree\b",
                 r"\bnot really\b", r"i don't agree", r"on the other hand", r"\bi'd rather\b", r"^actually\b",
                 r"\bi'm not convinced\b", r"that's not (what|how|true)"],
    "request": [r"\b(could|can|would|will) you\b", r"would you mind", r"do you mind", r"\bplease\b",
                r"i need you to", r"i'd like (you )?to", r"\b(can|could|may) i\b",
                r"do you have a (minute|second|moment|sec)"],
    "suggest": [r"\blet's\b", r"why don't (we|you)", r"\bhow about\b", r"\bwhat about\b", r"\bshall we\b",
                r"maybe (we|you) (should|could)", r"\bwe (should|could)\b", r"\byou should\b", r"\bwhat if\b",
                r"\bi suggest\b", r"\bwe might\b"],
    "experience": [r"i've (been|worked|done|had|always|never|learned|seen)", r"\bi used to\b", r"\bi worked\b",
                   r"\bi was in charge\b", r"\bmy (job|work|team|experience|boss|company|project|major)\b",
                   r"i'm good at", r"\bi graduated\b", r"\bi studied\b", r"\bi grew up\b", r"\bwhen i was\b",
                   r"\bi learned\b", r"\bi've got\b", r"i'm (a|an) [a-z]+(er|or|ist|ian|ant|ent)\b"],
    "plan": [r"\bi'm (going to|gonna)\b", r"\bwe're (going to|gonna)\b", r"\bi'll\b", r"\bwe'll\b",
             r"\bwe need to\b", r"\bi need to\b", r"get back to you", r"\blet me (check|see|know|think)\b",
             r"\bby (monday|tuesday|wednesday|thursday|friday|tomorrow|tonight|the end)\b",
             r"\bnext (week|month|time|step)\b", r"\bas soon as\b", r"\bdeadline\b", r"\bschedule\b",
             r"\bmeeting\b", r"\bthe plan\b", r"\bon my way\b"],
    "thanks": [r"\bthank(s| you)\b", r"\bi appreciate\b", r"\bgrateful\b"],
    "apology": [r"\bi'm sorry\b", r"\bsorry (about|for|to)\b", r"\bmy apologies\b", r"\bmy bad\b",
                r"\bexcuse me\b", r"\bmy fault\b"],
    "feeling": [r"i'm (so |really )?(glad|happy|excited|worried|nervous|afraid|scared|tired|proud|surprised)",
                r"i can't believe", r"that's (great|amazing|awesome|terrible|too bad|wonderful)",
                r"\bi love\b", r"\bi hate\b", r"\bwow\b"],
    "smalltalk": [r"how are you", r"how's it going", r"nice to meet you", r"good to see you",
                  r"how (was|is) your", r"what's up", r"have a (good|nice|great)", r"\bsee you\b",
                  r"\btake care\b", r"\bweekend\b", r"\bweather\b", r"how have you been", r"long time"],
}
_COMPILED = {k: [re.compile(p) for p in v] for k, v in FUNCTION_PATTERNS.items()}

PROFANITY_STRONG = re.compile(r"\b(fuck\w*|shit\w*|bitch\w*|asshole|motherf\w*|dick|cunt|bastard)\b")
PROFANITY_MILD = re.compile(r"\b(damn|hell|crap|ass|sucks?|screw)\b")


def pos_norm(text: str) -> str:
    """Lower-case + quote normalisation that keeps every character position."""
    table = str.maketrans({"’": "'", "‘": "'", "`": "'", "“": '"', "”": '"', "…": ".", "–": "-", "—": "-"})
    return text.translate(table).lower()


def function_tags(text: str):
    t = pos_norm(text).strip()
    tags = []
    for cat, pats in _COMPILED.items():
        if any(p.search(t) for p in pats):
            tags.append(cat)
    return tags


def rule_score(text: str, n_words: int, tags) -> float:
    t = pos_norm(text)
    if n_words < 3:
        base = 0.1
    elif n_words == 3:
        base = 0.4
    elif n_words <= 5:
        base = 0.7
    elif n_words <= 14:
        base = 1.0
    elif n_words <= 20:
        base = 0.7
    else:
        base = 0.35
    bonus = min(1.5, sum(WEIGHTS.get(c, 0) for c in tags))
    s = base + bonus
    if PROFANITY_STRONG.search(t):
        s -= 1.0
    elif PROFANITY_MILD.search(t):
        s -= 0.3
    words = re.findall(r"[A-Za-z']+", text)
    if words:
        caps = sum(1 for i, w in enumerate(words) if i > 0 and w[0].isupper() and w not in ("I", "I'm", "I'll", "I've", "I'd"))
        s -= 0.6 * caps / len(words)
    return round(max(0.0, s), 3)


# ------------------------------------------------------------------ connected speech
FUNC_NEXT_NOT_VERB = {"the", "a", "an", "my", "your", "his", "her", "our", "their", "this", "that", "these",
                      "those", "school", "work", "bed", "church", "jail", "be", "someone", "somewhere", "there",
                      "here", "it", "him", "them", "us", "me", "you"}

REDUCTIONS = [
    (r"\bgoing to(?= (?!(?:%s)\b)[a-z])" % "|".join(FUNC_NEXT_NOT_VERB), "going to", "gonna [거나]",
     "'going to + 동사'는 빠르게 말할 때 '거나'처럼 줄어들어요."),
    (r"\bwant to\b", "want to", "wanna [워너]", "'want to'는 t 소리가 사라지고 '워너'처럼 들려요."),
    (r"\bhave to\b", "have to", "hafta [해프터]", "'have to'는 v가 f처럼 바뀌어 '해프터'로 들려요."),
    (r"\bhas to\b", "has to", "hasta [해스터]", "'has to'는 '해스터'처럼 붙여 말해요."),
    (r"\bgot to\b", "got to", "gotta [가러]", "'got to'는 '가러'처럼 줄어들어요."),
    (r"\bkind of\b", "kind of", "kinda [카인더]", "'kind of'는 '카인더'처럼 한 단어로 들려요."),
    (r"\bsort of\b", "sort of", "sorta [소러]", "'sort of'는 '소러'처럼 들려요."),
    (r"\ba lot of\b", "a lot of", "a lotta [얼라러]", "'a lot of'는 t가 굴러 '얼라러'처럼 들려요."),
    (r"\bout of\b", "out of", "outta [아우러]", "'out of'는 '아우러'처럼 줄어요."),
    (r"\blet me\b", "let me", "lemme [레미]", "'let me'는 t가 빠져 '레미'처럼 들려요."),
    (r"\bgive me\b", "give me", "gimme [기미]", "'give me'는 '기미'처럼 들려요."),
    (r"\bdon't know\b", "don't know", "dunno [더노우]", "'don't know'는 '더노우'처럼 뭉개져 들리기도 해요."),
    (r"\bwhat do you\b", "what do you", "whaddaya [와러야]", "'what do you'는 '와러야'처럼 아주 빨리 지나가요."),
    (r"\bwhat are you\b", "what are you", "whatcha [와챠]", "'what are you'는 '와챠'처럼 줄어들어요."),
    (r"\bdid you\b", "did you", "didja [디쥬]", "d와 you가 만나 '디쥬'처럼 붙어요."),
    (r"\bwould you\b", "would you", "wouldja [우쥬]", "d와 you가 만나 '우쥬'처럼 붙어요."),
    (r"\bcould you\b", "could you", "couldja [쿠쥬]", "d와 you가 만나 '쿠쥬'처럼 붙어요."),
    (r"\bshould you\b", "should you", "shouldja [슈쥬]", "d와 you가 만나 '슈쥬'처럼 붙어요."),
    (r"\bgot you\b", "got you", "gotcha [가챠]", "t와 you가 만나 '챠'처럼 들려요."),
    (r"\b(?:don't|won't|can't|didn't|wouldn't|couldn't) you\b", "don't you", "donchu [돈츄]", "t와 you가 만나 '츄' 소리가 나요."),
    (r"\b(?:meet|get|bet|want|let|at|but|that|what|not|put) you\b", "t you", "t+you [츄]", "t로 끝나는 단어 뒤 you는 '츄'처럼 붙어요 (meet you → 미츄)."),
    (r"\b(?:need|and|told|did|made|had|would|could|should|find|mind) you\b", "d you", "d+you [쥬]", "d로 끝나는 단어 뒤 you는 '쥬'처럼 붙어요 (need you → 니쥬)."),
    (r"\b(?:tell|ask|give|let|make|call|help|see|saw|told|asked|gave|met|love|got) (?:him|her|his)\b", "tell him",
     "h 탈락 [텔림]", "him/her/his의 h가 약해져 앞 단어에 붙어요 (tell him → 텔림)."),
    (r"\b(?:tell|ask|give|let|make|call|help|see|saw|told|got|get|take|put|keep|find) them\b", "them", "'em [엄]",
     "them은 아주 약하게 '엄'처럼 들려요 (tell them → 텔럼)."),
    (r"\bbecause\b", "because", "'cause [커즈]", "because는 앞부분이 빠져 '커즈'로 들리곤 해요."),
]

FLAP_WORDS = {"water", "better", "matter", "letter", "later", "little", "city", "pretty", "getting", "setting",
              "sitting", "putting", "cutting", "waiting", "writing", "meeting", "eating", "beautiful", "computer",
              "party", "thirty", "forty", "duty", "total", "item", "data", "butter", "bottle", "battle", "title",
              "metal", "notice", "whatever", "matters", "bitter", "daughter", "hotter", "shutter", "greater",
              "voted", "started", "forgotten", "getting", "letting", "patty", "kitty", "fatter", "notified",
              "potato", "tomato", "auto", "photo", "motto", "lottery", "attitude", "community", "opportunity",
              "quality", "security", "university", "reality", "ability", "activity", "society", "priority"}
FLAP_KO = {"water": "워러", "better": "베러", "matter": "매러", "letter": "레러", "later": "레이러", "little": "리를",
           "city": "시리", "pretty": "프리리", "getting": "게링", "meeting": "미링", "party": "파리", "thirty": "써리",
           "forty": "포리", "computer": "컴퓨러", "beautiful": "뷰리풀", "whatever": "와레버", "daughter": "도러",
           "total": "토럴", "bottle": "바를", "butter": "버러", "waiting": "웨이링", "writing": "롸이링",
           "putting": "푸링", "sitting": "시링", "setting": "세링", "eating": "이링", "greater": "그레이러",
           "notice": "노리스", "data": "데이러", "photo": "포로", "potato": "포테이로", "tomato": "토메이로"}
FLAP_PAIRS = {
    "get it": "게릿", "got it": "가릿", "what about": "와러바웃", "not at all": "나래롤", "put it": "푸릿",
    "let it": "레릿", "but i": "버라이", "shut up": "셔럽", "what if": "와리프", "get out": "게라웃",
    "about it": "어바우릿", "that is": "대리즈", "what is": "와리즈", "it is": "이리즈", "eat it": "이릿",
    "bit about": "비러바웃", "get up": "게럽", "put on": "푸론", "set up": "세럽", "lot of": "라러브",
    "sit down": None, "check it out": "체키라웃", "pick it up": "피키럽", "a lot": "얼랏",
}
T_END = r"(?:get|got|put|what|that|it|not|but|lot|let|bit|sit|shut|eat|at|out|about|right|hit|wait|meet|set|forget|bought|thought|might|wanted)"


def _add(notes, a, b, kind, say, ko, text):
    for n in notes:
        if not (b <= n["a"] or a >= n["b"]):
            return
    notes.append({"a": a, "b": b, "kind": kind, "say": say, "ko": ko, "text": text[a:b]})


def speech_notes(text: str, limit: int = 5):
    t = pos_norm(text)
    notes = []
    for pair, say in FLAP_PAIRS.items():
        if say and pair.count(" ") >= 2:
            for m in re.finditer(r"\b%s\b" % re.escape(pair), t):
                _add(notes, m.start(), m.end(), "이어 말하기", f"[{say}]",
                     "단어 끝 자음이 다음 모음과 붙고, 모음 사이 t는 'ㄹ'처럼 굴러요.", text)
    for pat, _label, say, ko in REDUCTIONS:
        for m in re.finditer(pat, t):
            _add(notes, m.start(), m.end(), "줄여 말하기", say, ko, text)
    # flap T between words
    for m in re.finditer(r"\b(%s) (?=[aeiou])([a-z]+)" % T_END, t):
        pair = (m.group(1) + " " + m.group(2))
        a, b = m.start(), m.end()
        say = FLAP_PAIRS.get(pair)
        say = f"[{say}]" if say else "t를 'ㄹ'처럼 이어서"
        _add(notes, a, b, "t 굴리기", say, "모음 사이의 t는 미국식 발음에서 'ㄹ'처럼 부드럽게 굴러가요.", text)
    for m in re.finditer(r"\b[a-z]+\b", t):
        if m.group(0) in FLAP_WORDS:
            ko_say = FLAP_KO.get(m.group(0))
            _add(notes, m.start(), m.end(), "t 굴리기", f"[{ko_say}]" if ko_say else "t를 'ㄹ'처럼",
                 "모음 사이의 t(tt)는 'ㄹ'에 가깝게 들려요 (water → 워러, better → 베러).", text)
    # linking consonant + vowel (phrasal verbs etc.)
    for m in re.finditer(r"\b([a-z]*[bcdfgklmnpsvxz]) (it|up|on|out|off|in|about|over|away|again|an|a|all)\b", t):
        if len(m.group(1)) < 2:
            continue
        _add(notes, m.start(), m.end(), "이어 말하기", m.group(1) + "‿" + m.group(2) + " (붙여서)",
             "자음으로 끝난 단어와 모음으로 시작하는 단어가 붙어 한 단어처럼 들려요.", text)
    # same consonant merging
    for m in re.finditer(r"\b[a-z]*([bdgkptmnlsfvz]) \1[a-z]*\b", t):
        _add(notes, m.start(), m.end(), "자음 겹침", "겹친 자음은 한 번만",
             "앞 단어 끝 자음과 뒤 단어 첫 자음이 같으면 한 번만 길게 발음해요 (next time → 넥스타임).", text)
    # held / swallowed T
    for m in re.finditer(r"\b(just|can't|don't|won't|didn't|isn't|wasn't|doesn't|right|what|that|not|last|next|first|most|must|but|it|get|got|at|out) (?=[bcdfgjklmnpqrsvwz])", t):
        _add(notes, m.start(), m.end() - 1, "t 삼키기", "끝의 t를 거의 안 냄",
             "뒤에 자음이 오면 끝의 t를 거의 소리 내지 않고 멈추듯 넘어가요.", text)
    notes.sort(key=lambda n: n["a"])
    # weak function words summary
    weak = []
    for w, say in (("to", "터"), ("for", "퍼"), ("can", "큰"), ("of", "어브"), ("and", "은"), ("your", "여"), ("you", "여"), ("them", "엄"), ("have", "어브"), ("at", "엇")):
        if re.search(r"\b%s\b" % w, t) and w not in weak:
            weak.append(w)
    picked = notes[:limit]
    if len(weak) >= 2 and len(picked) < limit + 1:
        picked.append({"a": -1, "b": -1, "kind": "약하게", "say": ", ".join(weak[:5]),
                       "ko": "기능어(" + ", ".join(weak[:5]) + ")는 아주 약하고 짧게 발음돼서 받아쓰기에서 잘 놓쳐요.",
                       "text": ""})
    return picked


def reduction_count(text: str) -> int:
    t = pos_norm(text)
    n = 0
    for pat, *_ in REDUCTIONS:
        n += len(re.findall(pat, t))
    n += len(re.findall(r"\b(gonna|wanna|gotta|kinda|lemme|gimme|dunno|outta|y'all|ain't|'em|ya)\b", t))
    return n
