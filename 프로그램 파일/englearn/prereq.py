"""Before the window opens: make sure Ollama is installed, running and has a language model.

Runs in the black console window that 영어학습도구 실행.bat opens. Every install asks first (Y/N);
answering N just skips it — the program still opens, and the screen offers the model download later.
"""
import os
import shutil
import subprocess
import sys
import time

from . import ollama

OLLAMA_PAGE = "https://ollama.com/download"


def say(msg=""):
    try:
        print(msg, flush=True)
    except Exception:  # noqa: BLE001
        print(msg.encode("ascii", "replace").decode(), flush=True)


def can_ask():
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:  # noqa: BLE001
        return False


def ask(question):
    """Y/N in the console. Enter alone means yes."""
    if not can_ask():
        return False
    while True:
        try:
            a = input(f"  {question} [Y=예 / N=아니요] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if a in ("", "y", "yes", "ㅛ", "예", "네"):
            return True
        if a in ("n", "no", "ㅜ", "아니요", "아니오"):
            return False


def winget():
    return shutil.which("winget") or ""


def install_ollama():
    wg = winget()
    if not wg:
        say("  [!] 이 컴퓨터에는 자동 설치 도구(winget)가 없어요.")
        say(f"      브라우저로 {OLLAMA_PAGE} 를 열게요. 설치한 뒤 이 프로그램을 다시 실행해 주세요.")
        try:
            os.startfile(OLLAMA_PAGE)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
        return False
    say("  Ollama 공식 설치 파일을 받아 설치해요. (약 1.5GB, 몇 분 걸려요)")
    say("  Windows가 '변경을 허용할까요?'라고 물으면 [예]를 눌러 주세요.")
    say()
    r = subprocess.call([wg, "install", "--id", "Ollama.Ollama", "-e",
                         "--accept-package-agreements", "--accept-source-agreements"])
    say()
    exe = ollama.find_exe()
    if not exe:
        say(f"  [!] Ollama 설치가 끝나지 않았어요 (결과 코드 {r}). {OLLAMA_PAGE} 에서 직접 설치해 주세요.")
        return False
    say("  Ollama 설치 완료.")
    return True


def pull_model():
    name = ollama.RECOMMENDED
    say(f"  {name} 받는 중… (창을 닫지 마세요)")
    last = [0.0]

    def show(frac, status, done, total):
        now = time.time()
        if now - last[0] < 0.5 and status != "success":
            return
        last[0] = now
        if frac is None:
            line = f"  {status[:60]}"
        else:
            n = int(frac * 30)
            line = f"  [{'#' * n}{'.' * (30 - n)}] {frac * 100:5.1f}%  {done / 1e9:.2f} / {total / 1e9:.2f} GB"
        sys.stdout.write("\r" + line.ljust(78))
        sys.stdout.flush()

    try:
        ollama.pull(name, on_progress=show)
    except ollama.OllamaError as e:
        say()
        say(f"  [!] 모델을 받지 못했어요: {e}")
        say("      프로그램 화면의 [모델 받기] 버튼으로 다시 시도할 수 있어요.")
        return False
    say()
    say(f"  {name} 준비 완료.")
    return True


def ensure_ollama():
    """Best effort. Never raises; returns True when a usable model answers."""
    try:
        return _ensure()
    except Exception as e:  # noqa: BLE001
        say(f"  [!] AI 준비 확인 중 문제가 생겼어요: {e}")
        return False


def _ensure():
    if ollama.is_running():
        if ollama.has_usable_model():
            return True
        return _offer_model()
    exe = ollama.find_exe()
    if exe:
        say("  Ollama를 켜는 중…")
        if ollama.start(exe):
            return True if ollama.has_usable_model() else _offer_model()
        say("  [!] Ollama가 켜지지 않았어요. 시작 메뉴에서 Ollama를 켜 주세요.")
        return False
    if os.name != "nt":
        say(f"  [!] Ollama가 없어요. {OLLAMA_PAGE} 에서 설치해 주세요.")
        return False
    say()
    say("  ─────────────────────────────────────────────")
    say("  AI 대화·분석에 쓰는 Ollama가 이 컴퓨터에 없어요.")
    say("  (Ollama: 내 컴퓨터 안에서 AI 모델을 돌리는 무료 프로그램)")
    if not ask("지금 설치할까요?"):
        say("  건너뛰었어요. 자막·받아쓰기·따라 말하기는 Ollama 없이도 돼요.")
        return False
    if not install_ollama():
        return False
    say("  Ollama를 켜는 중…")
    if not ollama.start(wait=40):
        say("  [!] Ollama가 아직 켜지지 않았어요. 잠시 뒤 화면의 [다시 확인]을 눌러 주세요.")
        return False
    return _offer_model()


def _offer_model():
    say()
    say("  ─────────────────────────────────────────────")
    say(f"  AI 언어 모델이 아직 없어요. 추천 모델: {ollama.RECOMMENDED} (약 {ollama.RECOMMENDED_GB}GB)")
    if not ask("지금 받을까요?"):
        say("  건너뛰었어요. 나중에 프로그램 화면에서 [모델 받기]를 누르면 돼요.")
        return False
    return pull_model()
