"""Preparation jobs: dialogue lines, playable media, AI analysis, examples, model download."""
import logging
import os
import shutil
from pathlib import Path

from . import analysis, config, media, ollama, project, stt, subtitles, tts
from .jobs import jobs
from .storage import read_json, write_json

log = logging.getLogger("englearn")
EN_CODES = {"eng": "en", "en": "en", "kor": "ko", "ko": "ko"}


def fmt_time(sec):
    sec = int(max(0, sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def ensure_probe(pid):
    proj = project.load(pid)
    movie = Path(proj["movie"])
    if not movie.exists():
        raise FileNotFoundError(f"영화 파일을 찾을 수 없어요: {movie}\n파일을 옮겼다면 원래 자리로 되돌려 주세요.")
    info = proj.get("probe")
    if not info:
        info = media.probe(movie)
        proj = project.update(pid, probe=info, duration=info.get("duration") or 0.0,
                              audio_stream=media.pick_audio(info))
    return proj, info


def _track_opt(kind, ident, name, t, extra=None):
    cues = t["cues"]
    sample = next((c["text"].replace("\n", " ") for c in cues[len(cues) // 3:] if len(c["text"]) > 12), "")
    d = {"id": ident, "kind": kind, "name": name, "lang": t["lang"], "count": len(cues),
         "sample": sample[:90], "usable": True}
    d.update(extra or {})
    return d


def scan_file(path):
    """Options from one subtitle file chosen by the user (any folder)."""
    path = Path(path)
    out = []
    for ti, t in enumerate(subtitles.load_tracks(path)):
        label = f"{path.name}" + (f" — {t['label']}" if t.get("label") else "")
        out.append(_track_opt("file", f"file|{path}|{ti}", label, t))
    return out


def scan(pid):
    proj, info = ensure_probe(pid)
    movie = Path(proj["movie"])
    en, ko = [], []
    for f in subtitles.find_external(movie):
        try:
            tracks = subtitles.load_tracks(f)
        except Exception as e:  # noqa: BLE001
            log.warning("subtitle read failed %s: %s", f, e)
            continue
        for ti, t in enumerate(tracks):
            label = f.name + (f" — {t['label']}" if t.get("label") else "")
            opt = _track_opt("external", f"file|{f}|{ti}", label, t)
            if t["lang"] == "en":
                en.append(opt)
            elif t["lang"] == "ko":
                ko.append(opt)
    for s in media.streams(info, "subtitle"):
        usable = s["codec"] in media.TEXT_SUB_CODECS
        lang = EN_CODES.get(s["lang"], "?")
        bits = [s["lang"] or "언어 표시 없음"]
        if s.get("title"):
            bits.append(s["title"])
        opt = {"id": f"emb|{s['index']}", "kind": "embedded", "name": f"영화 안에 든 자막 #{s['index']} ({', '.join(bits)})",
               "lang": lang, "count": None, "sample": "", "usable": usable, "codec": s["codec"]}
        if not usable:
            opt["note"] = "그림으로 된 자막이라 글자로 꺼낼 수 없어요"
        if lang in ("en", "?"):
            en.append(dict(opt))
        if lang in ("ko", "?"):
            ko.append(dict(opt))
    dur_min = (info.get("duration") or 0) / 60
    en.append({"id": "whisper", "kind": "whisper", "name": "음성 인식으로 대사 만들기 (자막이 없을 때)",
               "lang": "en", "count": None, "usable": stt.available(),
               "note": f"이 컴퓨터에서 약 {max(1, round(dur_min * 0.35))}분 걸릴 수 있어요 (영화 {round(dur_min)}분 기준)"
               if stt.available() else "음성 인식 프로그램이 설치되지 않았어요"})

    def best(opts):
        for o in opts:
            if o["kind"] in ("external", "file") and (o.get("count") or 0) >= 10:
                return o["id"]
        for o in opts:
            if o["kind"] == "embedded" and o["usable"] and o["lang"] != "?":
                return o["id"]
        for o in opts:
            if o["kind"] == "embedded" and o["usable"]:
                return o["id"]
        return None

    auds = [{"index": s["index"], "lang": s["lang"], "codec": s["codec"], "title": s.get("title", ""),
             "layout": s.get("layout", "")} for s in media.streams(info, "audio")]
    vids = media.streams(info, "video")
    return {"en": en, "ko": ko, "default_en": best(en) or "whisper", "default_ko": best(ko) or "",
            "duration": info.get("duration"), "audio": auds, "audio_stream": proj.get("audio_stream"),
            "video": ({"codec": vids[0]["codec"], "width": vids[0].get("width"), "height": vids[0].get("height")}
                      if vids else None)}


def _load_choice(pid, proj, info, choice, want, job, p0, p1):
    kind, _, rest = choice.partition("|")
    if kind == "file":
        path, _, ti = rest.rpartition("|")
        tracks = subtitles.load_tracks(path)
        t = tracks[int(ti)] if ti.isdigit() and int(ti) < len(tracks) else tracks[0]
        return t["cues"], {"kind": "file", "name": Path(path).name}
    if kind == "emb":
        idx = int(rest)
        out = project.media_dir(pid) / f"sub_{idx}.srt"
        if not out.exists() or out.stat().st_size == 0:
            job.set(p0, "영화 안의 자막을 꺼내는 중…")
            media.extract_subtitle(proj["movie"], idx, out, info.get("duration") or 0,
                                   on_progress=lambda f: job.set(p0 + (p1 - p0) * f), cancel=job.cancelled)
        tracks = subtitles.load_tracks(out)
        if not tracks:
            raise RuntimeError("꺼낸 자막에 글자가 없어요. 다른 자막을 골라 주세요.")
        t = next((t for t in tracks if t["lang"] == want), tracks[0])
        return t["cues"], {"kind": "embedded", "name": f"영화 안의 자막 #{idx}"}
    raise ValueError(f"알 수 없는 자막 선택: {choice}")


def job_prepare(pid, en_choice, ko_choice="", whisper_model=None):
    proj = project.load(pid)

    def run(job):
        proj, info = ensure_probe(pid)
        project.update(pid, prep={"state": "running", "en": en_choice, "ko": ko_choice, "model": whisper_model})
        ko_cues, ko_meta = None, None
        if ko_choice:
            ko_cues, ko_meta = _load_choice(pid, proj, info, ko_choice, "ko", job, 0.0, 0.05)
        if en_choice == "whisper":
            lines = _whisper_lines(pid, proj, info, job, whisper_model or config.get("movie_stt_model"))
            if job.cancelled():
                return
            if ko_cues:
                subtitles.pair_korean(lines, ko_cues)
            en_meta = {"kind": "whisper", "name": f"음성 인식 ({whisper_model or config.get('movie_stt_model')})"}
        else:
            en_cues, en_meta = _load_choice(pid, proj, info, en_choice, "en", job, 0.05, 0.9)
            lines = subtitles.cues_to_lines(en_cues, ko_cues)
        if job.cancelled():
            return
        if not lines:
            raise RuntimeError("영어 대사를 하나도 찾지 못했어요. 다른 자막을 골라 보세요.")
        analysis.add_features(lines)
        project.save_lines(pid, lines)
        project.update(pid, lines_ready=True, line_count=len(lines), en=en_meta, ko=ko_meta,
                       analysis={"state": "none", "done": 0, "total": 0, "depth": ""},
                       prep={"state": "done", "en": en_choice, "ko": ko_choice, "model": whisper_model})
        job.set(1.0, f"대사 {len(lines)}줄 준비 완료")

    return jobs.start("prepare", pid, f"{proj['title']} 대사 준비", run)


def _whisper_lines(pid, proj, info, job, model):
    if not stt.available():
        raise RuntimeError("음성 인식 프로그램(faster-whisper)이 설치되지 않았어요: " + stt.import_error())
    if not stt.is_ready(model):
        job.set(0.0, "음성 인식 모델을 내려받는 중… (처음 한 번)")
        stt.download(model, on_progress=lambda d, t: job.set(0.04 * d / max(1, t),
                                                              f"음성 인식 모델 내려받는 중… {d / 1e6:.0f} / {t / 1e6:.0f} MB"),
                     cancel=job.cancelled)
    wav = project.media_dir(pid) / "audio16k.wav"
    dur = info.get("duration") or 0
    if not wav.exists():
        job.set(0.04, "영화에서 소리를 꺼내는 중…")
        media.extract_wav16k(proj["movie"], proj.get("audio_stream"), wav, dur,
                             on_progress=lambda f: job.set(0.04 + 0.04 * f), cancel=job.cancelled)
    dur = media.wav_duration(wav)
    sp = project.folder(pid) / "음성인식_진행.json"
    state = read_json(sp, None)
    if not state or state.get("model") != model:
        state = {"model": model, "pos": 0.0, "segments": []}

    def prog(f):
        job.set(0.08 + 0.9 * f, f"음성 인식 중… {fmt_time(f * dur)} / {fmt_time(dur)}")

    stt.transcribe_movie(wav, model, state, on_progress=prog, cancel=job.cancelled,
                         on_save=lambda s: write_json(sp, s), beam_size=1 if model.startswith(("tiny", "base")) else 5)
    stt.unload("movie")
    return stt.segments_to_lines(state["segments"])


def job_media(pid, hevc_ok=False, force_plan=None):
    proj = project.load(pid)

    def run(job):
        proj, info = ensure_probe(pid)
        movie = proj["movie"]
        a_idx = proj.get("audio_stream")
        plan = force_plan or media.play_plan(info, movie, a_idx, hevc_ok)
        if plan == "transcode" and not media.streams(info, "video"):
            plan = "audio"
        md = project.media_dir(pid)
        if plan == "direct":
            project.update(pid, media={"plan": "direct", "file": movie, "state": "ready", "audio_only": False})
            job.set(1.0, "원본 영상을 그대로 재생해요")
            return
        free = shutil.disk_usage(md).free
        size = os.path.getsize(movie)
        if plan == "remux" and free < size * 1.1 + 500e6:
            plan = "transcode"
        audio_file = md / "learn-audio.m4a"
        if plan in ("transcode", "audio") and not audio_file.exists():
            job.set(0.0, "소리만 먼저 준비하는 중… (영상보다 빨라요)")
            media.make_playable(movie, info, a_idx, "audio", audio_file,
                                on_progress=lambda f: job.set(0.1 * f if plan == "transcode" else f),
                                cancel=job.cancelled)
            project.update(pid, media={"plan": plan, "file": str(audio_file), "state": "audio" if plan == "transcode" else "ready",
                                       "audio_only": True})
            if plan == "audio":
                return
        if plan == "transcode" and free < 1.5e9:
            project.update(pid, media={"state": "ready", "note": "디스크 공간이 부족해 소리만으로 학습해요."})
            return
        out = md / "learn.mp4"
        p0 = 0.1 if plan == "transcode" else 0.0
        enc = media.hw_encoder() if plan == "transcode" else ""
        label = {"remux": "재생용 사본을 만드는 중… (화질 그대로)", "transcode": "재생용 영상으로 바꾸는 중…" + (f" ({enc} 가속)" if enc else "")}[plan]
        job.set(p0, label)
        media.make_playable(movie, info, a_idx, plan, out,
                            on_progress=lambda f: job.set(p0 + (1 - p0) * f, label), cancel=job.cancelled)
        project.update(pid, media={"plan": plan, "file": str(out), "state": "ready", "audio_only": False})
        job.set(1.0, "재생 준비 완료")

    return jobs.start("media", pid, f"{proj['title']} 영상 준비", run)


def job_analyze(pid, depth="normal", redo=False):
    proj = project.load(pid)

    def run(job):
        lines = project.lines(pid)
        if not lines:
            raise RuntimeError("먼저 대사를 준비해 주세요.")
        ids = analysis.candidates(lines, depth)
        if redo:
            for l in lines:
                l.pop("ai", None)
                l["key"] = False
            project.save_lines(pid, lines)
        total = len(ids)
        model = ollama.pick_model()  # fail early if Ollama is off
        project.update(pid, analysis={"state": "running", "done": sum(1 for i in ids if lines[i].get("ai")),
                                      "total": total, "depth": depth, "model": model})

        def prog(f):
            done = int(round(f * total))
            job.set(f, f"AI({model})가 대사를 읽는 중… {done} / {total}줄")
            project.update(pid, analysis={"done": done})

        job.set(0.0, f"AI({model})가 대사를 읽는 중… 0 / {total}줄")
        ok = analysis.analyze(lines, ids, on_progress=prog, cancel=job.cancelled,
                              on_save=lambda ls: project.save_lines(pid, ls), log=log.warning)
        keys = sum(1 for l in lines if l.get("key"))
        if ok:
            project.update(pid, analysis={"state": "done", "done": total, "total": total, "depth": depth, "keys": keys})
            job.set(1.0, f"분석 완료: 핵심 문장 {keys}개")
        else:
            project.update(pid, analysis={"state": "paused"})

    return jobs.start("analyze", pid, f"{proj['title']} AI 분석", run)


def job_examples(pid):
    proj = project.load(pid)

    def run(job):
        lines = project.lines(pid)
        exprs = analysis.expressions(lines)
        have = project.cache(pid, "예문")
        todo = [e for e in exprs if e["id"] not in have]
        for k, e in enumerate(todo):
            if job.cancelled():
                return
            while True:
                ollama.gate.wait_turn(job.cancelled)
                if job.cancelled():
                    return
                try:
                    ex = analysis.make_example(e["text"], lines[e["line"]]["text"], interactive=False,
                                               should_stop=lambda: ollama.gate.busy() or job.cancelled())
                    break
                except ollama.Preempted:
                    continue
                except ollama.OllamaError as err:
                    if "연결할 수 없어요" in str(err):
                        raise
                    ex = None
                    break
            if ex:
                project.update_cache(pid, "예문", lambda d, _id=e["id"], _ex=ex: d.__setitem__(_id, _ex))
            job.set((k + 1) / len(todo), f"면접·미팅 예문 만드는 중… {k + 1} / {len(todo)}")

    return jobs.start("examples", pid, f"{proj['title']} 예문 만들기", run)


def job_download(name):
    def run(job):
        job.set(0.0, f"음성 인식 모델({name}) 내려받는 중…")
        stt.download(name, on_progress=lambda d, t: job.set(d / max(1, t), f"음성 인식 모델 내려받는 중… {d / 1e6:.0f} / {t / 1e6:.0f} MB"),
                     cancel=job.cancelled)
        job.set(1.0, "내려받기 완료")

    return jobs.start("download", name, f"음성 인식 모델 {name}", run)


def job_tts_install():
    def run(job):
        job.set(0.0, "영어 음성 준비 중…")
        tts.install(on_progress=lambda d, t: job.set(d / max(1, t), f"영어 음성 모델 내려받는 중… {d / 1e6:.0f} / {t / 1e6:.0f} MB"),
                    on_msg=lambda m: job.set(None, m), cancel=job.cancelled)
        job.set(1.0, "영어 음성 준비 완료")

    return jobs.start("tts", "kokoro", "영어 음성(Kokoro)", run)
