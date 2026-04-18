from __future__ import annotations

from functools import lru_cache
from pathlib import Path


ASSETS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_text_asset(*path_parts: str) -> str:
    asset_path = ASSETS_DIR.joinpath(*path_parts)
    return asset_path.read_text(encoding="utf-8")


@lru_cache(maxsize=None)
def load_binary_asset(*path_parts: str) -> bytes:
    asset_path = ASSETS_DIR.joinpath(*path_parts)
    return asset_path.read_bytes()
