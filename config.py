"""集中設定管理模組

優先順序：環境變數 > config.json > 預設值
掃描路徑等使用者設定存在 DB settings 表，由 Web UI 管理。
"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

# 專案根目錄
BASE_DIR = Path(__file__).parent.resolve()

# ── 預設值 ──

DEFAULTS = {
    "port": 5000,
    "debug": False,
    "db_path": str(BASE_DIR / "doujin.db"),
    "thumb_dir": str(BASE_DIR / "thumbs"),
    "thumb_size": "300x400",
    "thumb_workers": 4,
    "thumb_quality": 80,
    "request_delay": 1.5,
}

# ── config.json（可選）──

_config_file = BASE_DIR / "config.json"
_file_config = {}
if _config_file.exists():
    try:
        _file_config = json.loads(_config_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass


def get(key: str, default=None):
    """讀取設定值。優先順序：環境變數 DOUJIN_{KEY} > config.json > DEFAULTS。"""
    env_key = f"DOUJIN_{key.upper()}"
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val
    if key in _file_config:
        return _file_config[key]
    if key in DEFAULTS:
        return DEFAULTS[key]
    return default


def get_int(key: str, default: int = 0) -> int:
    return int(get(key, default))


def get_bool(key: str, default: bool = False) -> bool:
    val = get(key, default)
    if isinstance(val, bool):
        return val
    return str(val).lower() in ("1", "true", "yes")


# ── 衍生設定 ──

PORT = get_int("port", 5000)
DEBUG = get_bool("debug", False)
DB_PATH = Path(get("db_path"))
THUMB_DIR = Path(get("thumb_dir"))
THUMB_WORKERS = get_int("thumb_workers", 4)
THUMB_QUALITY = get_int("thumb_quality", 80)
REQUEST_DELAY = float(get("request_delay", 1.5))

_ts = get("thumb_size", "300x400")
THUMB_SIZE = tuple(int(x) for x in _ts.split("x"))


def default_viewer() -> str:
    """回傳平台預設的閱讀器路徑。"""
    system = platform.system()
    if system == "Windows":
        # 常見漫畫閱讀器路徑
        candidates = [
            r"C:\Program Files\Honeyview\Honeyview.exe",
            r"C:\Program Files (x86)\Honeyview\Honeyview.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
    return ""


def open_file_cross_platform(filepath: str):
    """跨平台開啟檔案。"""
    system = platform.system()
    if system == "Windows":
        os.startfile(filepath)
    elif system == "Darwin":
        subprocess.Popen(["open", filepath])
    else:
        subprocess.Popen(["xdg-open", filepath])
