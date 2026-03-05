"""縮圖生成模組 — 從 zip/資料夾抽取第一張圖，縮放後存為 webp 快取。"""

import os
import zipfile
import io
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from PIL import Image

import config

logger = logging.getLogger(__name__)

THUMB_DIR = config.THUMB_DIR
THUMB_DIR.mkdir(exist_ok=True)
THUMB_SIZE = config.THUMB_SIZE
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}
# 防止解碼超大圖片吃光記憶體
Image.MAX_IMAGE_PIXELS = 50_000_000


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTS


def _natural_sort_key(s: str):
    """自然排序 key（page_2 < page_10）。"""
    import re
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


def get_thumbnail_path(doujinshi_id: int) -> Path | None:
    """回傳縮圖路徑（若已快取）。"""
    p = THUMB_DIR / f"{doujinshi_id}.webp"
    return p if p.exists() else None


def _failed_marker(doujinshi_id: int) -> Path:
    return THUMB_DIR / f"{doujinshi_id}.failed"


def generate_thumbnail(filepath: str, doujinshi_id: int) -> Path | None:
    """從 zip 或資料夾產生縮圖，存為 thumbs/{id}.webp。"""
    out = THUMB_DIR / f"{doujinshi_id}.webp"
    if out.exists():
        return out
    if _failed_marker(doujinshi_id).exists():
        return None

    try:
        img_bytes = _extract_first_image(filepath)
        if not img_bytes:
            _failed_marker(doujinshi_id).touch()
            return None

        img = Image.open(io.BytesIO(img_bytes))
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.save(out, 'WEBP', quality=config.THUMB_QUALITY)
        return out
    except Exception as e:
        logger.warning("縮圖生成失敗 [%s]: %s", doujinshi_id, e)
        _failed_marker(doujinshi_id).touch()
        return None


def _extract_first_image(filepath: str) -> bytes | None:
    """從 zip 或資料夾取出第一張圖片的 bytes。"""
    if filepath.lower().endswith('.zip'):
        return _extract_from_zip(filepath)
    elif os.path.isdir(filepath):
        return _extract_from_dir(filepath)
    return None


def _extract_from_zip(zip_path: str) -> bytes | None:
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            images = sorted(
                [n for n in zf.namelist() if _is_image(n) and not n.startswith('__MACOSX')],
                key=_natural_sort_key
            )
            if not images:
                return None
            return zf.read(images[0])
    except (zipfile.BadZipFile, OSError, KeyError) as e:
        logger.warning("zip 讀取失敗 [%s]: %s", zip_path, e)
        return None


def _extract_from_dir(dir_path: str) -> bytes | None:
    try:
        images = sorted(
            [f for f in os.listdir(dir_path) if _is_image(f)],
            key=_natural_sort_key
        )
        if not images:
            # 嘗試第一層子目錄
            for sub in sorted(os.listdir(dir_path)):
                sub_path = os.path.join(dir_path, sub)
                if os.path.isdir(sub_path):
                    sub_images = sorted(
                        [f for f in os.listdir(sub_path) if _is_image(f)],
                        key=_natural_sort_key
                    )
                    if sub_images:
                        with open(os.path.join(sub_path, sub_images[0]), 'rb') as f:
                            return f.read()
            return None
        with open(os.path.join(dir_path, images[0]), 'rb') as f:
            return f.read()
    except OSError as e:
        logger.warning("資料夾讀取失敗 [%s]: %s", dir_path, e)
        return None


class ThumbWorker:
    """背景縮圖生成器，使用 ThreadPoolExecutor 限制並發。"""

    def __init__(self, max_workers: int = 2):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._pending = set()
        self._lock = Lock()

    def submit(self, filepath: str, doujinshi_id: int):
        """提交縮圖生成任務（若未在佇列中）。"""
        with self._lock:
            if doujinshi_id in self._pending:
                return
            self._pending.add(doujinshi_id)
        self._executor.submit(self._run, filepath, doujinshi_id)

    def _run(self, filepath: str, doujinshi_id: int):
        try:
            generate_thumbnail(filepath, doujinshi_id)
        finally:
            with self._lock:
                self._pending.discard(doujinshi_id)
