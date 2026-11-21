"""Folder layout. Everything stays inside the tool folder.

로컬 AI 영어학습도구/
  영어학습도구 실행.bat
  설명서와 예제/          manual + sample scene
  프로그램 파일/          this code, .venv, 모델/ (speech models), web/
  학습 기록/              per-movie study data, settings, review cards
"""
import os
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent
TOOL_DIR = ENGINE_DIR.parent
WEB_DIR = ENGINE_DIR / "web"
MODELS_DIR = Path(os.environ.get("ENGLEARN_MODELS") or (ENGINE_DIR / "모델"))
DATA_DIR = Path(os.environ.get("ENGLEARN_DATA") or (TOOL_DIR / "학습 기록"))
SAMPLE_DIR = TOOL_DIR / "설명서와 예제"
LOG_DIR = ENGINE_DIR / "로그"
EDGE_PROFILE_DIR = ENGINE_DIR / ".app-window"

PROJECTS_DIR = DATA_DIR  # one sub-folder per movie
ROLEPLAY_DIR = DATA_DIR / "_면접 미팅 연습"
SETTINGS_FILE = DATA_DIR / "_설정.json"
REVIEW_FILE = DATA_DIR / "_복습 카드.json"


def ensure_dirs():
    for d in (MODELS_DIR, DATA_DIR, ROLEPLAY_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
