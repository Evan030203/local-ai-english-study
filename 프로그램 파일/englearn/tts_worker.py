"""Kokoro voice worker (separate process). Reads one JSON request per line on stdin,
writes the WAV to the requested path, answers one JSON line on stdout.

Run as:  python -m englearn.tts_worker   (from 프로그램 파일, started by englearn.tts)
"""
import io
import json
import os
import shutil
import sys
import tempfile
import wave
from pathlib import Path

MODELS_DIR = Path(os.environ.get("ENGLEARN_MODELS") or (Path(__file__).resolve().parent.parent / "모델"))
MODEL = MODELS_DIR / "kokoro" / "kokoro-v1.0.int8.onnx"
VOICES = MODELS_DIR / "kokoro" / "voices-v1.0.bin"


def ascii_data_dir(src: str) -> str:
    """espeak-ng opens its data with narrow (ANSI) paths on Windows and exits on failure,
    so give it a folder whose path is plain ASCII."""
    if src.isascii():
        return src
    roots = [tempfile.gettempdir(), os.environ.get("ProgramData") or "C:\\ProgramData", "C:\\"]
    for root in roots:
        dst = Path(root) / "englearn-espeak-ng-data"
        if not str(dst).isascii():
            continue
        try:
            marker = dst / "phontab"
            if not marker.is_file() or marker.stat().st_size != (Path(src) / "phontab").stat().st_size:
                shutil.copytree(src, dst, dirs_exist_ok=True)
            return str(dst)
        except OSError:
            continue
    return src


def load():
    import espeakng_loader
    import numpy as np
    import onnxruntime as rt
    from kokoro_onnx import Kokoro
    from kokoro_onnx.config import EspeakConfig
    from kokoro_onnx.tokenizer import Tokenizer

    lib = espeakng_loader.get_library_path()
    data = ascii_data_dir(str(espeakng_loader.get_data_path()))
    opts = rt.SessionOptions()
    opts.intra_op_num_threads = max(1, min(8, (os.cpu_count() or 4) - 1))
    opts.log_severity_level = 3
    with open(MODEL, "rb") as fh:
        sess = rt.InferenceSession(fh.read(), sess_options=opts, providers=["CPUExecutionProvider"])
    k = Kokoro.__new__(Kokoro)
    k.sess = sess
    with open(VOICES, "rb") as fh:
        k.voices = np.load(io.BytesIO(fh.read()))
    k.tokenizer = Tokenizer(EspeakConfig(lib_path=lib, data_path=data))
    return k


def write_wav(path, samples, sr):
    import numpy as np
    pcm = (np.clip(np.asarray(samples, dtype=np.float32), -1, 1) * 32767).astype("<i2").tobytes()
    tmp = Path(path).with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    os.replace(tmp, path)


def main():
    out = sys.stdout
    engine = None
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
            if engine is None:
                engine = load()
            if req.get("cmd") == "load":
                out.write(json.dumps({"ok": True}) + "\n")
                out.flush()
                continue
            voice = req.get("voice") or "af_heart"
            lang = "en-gb" if voice.startswith("b") else "en-us"
            samples, sr = engine.create(req["text"], voice=voice, speed=float(req.get("speed") or 1.0), lang=lang)
            write_wav(req["out"], samples, sr)
            resp = {"ok": True}
        except Exception as e:  # noqa: BLE001
            resp = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        out.write(json.dumps(resp) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
