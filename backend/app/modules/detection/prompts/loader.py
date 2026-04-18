from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


PROMPTS_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt_bundle(filename: str) -> dict[str, Any]:
    prompt_path = PROMPTS_DIR / filename
    with prompt_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError(f"提示词文件 {prompt_path} 不是 JSON 对象。")

    return payload
