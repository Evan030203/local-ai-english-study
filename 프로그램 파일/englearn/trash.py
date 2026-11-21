"""Send files to the Recycle Bin, so a movie removed from the app can still be restored from there."""
import os
import shutil
import time
from pathlib import Path
from urllib.parse import quote


def send(path):
    path = Path(path)
    if not path.exists():
        return
    if os.name == "nt":
        _windows(path)
    else:
        _freedesktop(path)


def _windows(path):
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", wintypes.WORD), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE = 3
    FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
    FOF_WANTNUKEWARNING = 0x4000   # ask first if Windows could only delete it for good (no Recycle Bin there)
    op = SHFILEOPSTRUCTW()
    op.wFunc = FO_DELETE
    op.pFrom = str(path.resolve()) + "\0"   # the list must end with two zero characters
    op.fFlags = FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI | FOF_WANTNUKEWARNING
    com = ctypes.windll.ole32.CoInitialize(None) in (0, 1)   # the shell may need COM on this thread
    try:
        rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    finally:
        if com:
            ctypes.windll.ole32.CoUninitialize()
    if op.fAnyOperationsAborted:
        raise OSError("휴지통으로 보내기를 취소했어요")
    if rc or path.exists():
        raise OSError("다른 프로그램이 쓰고 있어서 보내지 못했어요" if rc in (32, 0x20, 0x78, 0x7C)
                      else f"휴지통으로 보내지 못했어요 (코드 {rc})")


def _freedesktop(path):
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Trash"
    files, info = base / "files", base / "info"
    files.mkdir(parents=True, exist_ok=True)
    info.mkdir(parents=True, exist_ok=True)
    name, k = path.name, 1
    while (files / name).exists() or (info / f"{name}.trashinfo").exists():
        k += 1
        name = f"{path.stem} ({k}){path.suffix}"
    (info / f"{name}.trashinfo").write_text(
        f"[Trash Info]\nPath={quote(str(path.resolve()))}\nDeletionDate={time.strftime('%Y-%m-%dT%H:%M:%S')}\n",
        encoding="utf-8")
    shutil.move(str(path), str(files / name))
