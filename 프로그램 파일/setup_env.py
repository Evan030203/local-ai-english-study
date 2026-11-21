"""처음 한 번: 프로그램 전용 파이썬 환경(.venv)을 만들고 부품을 설치합니다.

영어학습도구 실행.bat 이 컴퓨터에 설치된 파이썬으로 이 파일을 실행합니다.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
VENV = os.path.join(HERE, ".venv")
PY = os.path.join(VENV, "Scripts", "python.exe") if os.name == "nt" else os.path.join(VENV, "bin", "python")
REQ = os.path.join(HERE, "requirements.txt")


def say(msg=""):
    try:
        print(msg, flush=True)
    except Exception:  # noqa: BLE001
        print(msg.encode("ascii", "replace").decode(), flush=True)


def main():
    say()
    say("  로컬 AI 영어학습도구 — 처음 실행 준비")
    say("  필요한 부품을 설치해요. 인터넷이 필요하고 3~10분 정도 걸려요.")
    say()
    if sys.version_info < (3, 10):
        say(f"  [!] 파이썬 3.10 이상이 필요해요. 지금 버전: {sys.version.split()[0]}")
        return 1
    if not os.path.exists(PY):
        say("  1/3 전용 환경 만드는 중…")
        r = subprocess.call([sys.executable, "-m", "venv", VENV])
        if r != 0 or not os.path.exists(PY):
            say("  [!] 전용 환경(.venv)을 만들지 못했어요.")
            return 1
    say("  2/3 pip 준비 중…")
    subprocess.call([PY, "-m", "pip", "install", "--upgrade", "pip", "--disable-pip-version-check", "-q"])
    say("  3/3 부품 설치 중… (영상 도구, 음성 인식, 영어 음성)")
    with open(REQ, encoding="utf-8") as fh:
        reqs = [l.strip() for l in fh if l.strip() and not l.startswith("#")]
    core = [r for r in reqs if r.split(">")[0].split("=")[0] in ("imageio-ffmpeg", "numpy")]
    rest = [r for r in reqs if r not in core]
    if subprocess.call([PY, "-m", "pip", "install", "--disable-pip-version-check", *core]) != 0:
        say("  [!] 기본 부품을 설치하지 못했어요. 인터넷 연결을 확인하고 다시 실행해 주세요.")
        return 1
    for r in rest:  # each optional part on its own, so one failure doesn't block the others
        if subprocess.call([PY, "-m", "pip", "install", "--disable-pip-version-check", r]) != 0:
            say(f"  [!] {r} 설치에 실패했어요. 프로그램은 먼저 실행하고, 다음 실행 때 다시 시도해요.")
    say()
    say("  설치 완료!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
