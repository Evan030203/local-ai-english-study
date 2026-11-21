"""로컬 AI 영어학습도구 — 실행 시작점.

영어학습도구 실행.bat 이 이 파일을 .venv 의 파이썬으로 실행합니다.
옵션: --no-window (창을 띄우지 않고 서버만 실행)
"""
import logging
import os
import subprocess
import sys
from logging.handlers import RotatingFileHandler

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

NEEDED = (("imageio_ffmpeg", "imageio-ffmpeg"), ("numpy", "numpy"), ("faster_whisper", "faster-whisper"))


def ensure_packages():
    missing = []
    for mod, pkg in NEEDED:
        try:
            __import__(mod)
        except Exception:  # noqa: BLE001
            missing.append(pkg)
    if not missing:
        return
    print("필요한 부품을 설치해요:", ", ".join(missing))
    subprocess.call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", *missing])


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    from englearn import paths
    paths.ensure_dirs()
    fh = RotatingFileHandler(paths.LOG_DIR / "englearn.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter("  [%(levelname)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(ch)
    for noisy in ("faster_whisper", "httpx", "huggingface_hub", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    ensure_packages()
    from englearn import server
    return server.serve(open_ui="--no-window" not in sys.argv)


if __name__ == "__main__":
    sys.exit(main() or 0)
