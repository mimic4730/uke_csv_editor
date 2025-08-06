# branch_manager.py  （置き換え or 新規ファイル）
from __future__ import annotations
import json
from pathlib import Path
from typing import List

# 保存場所
DEFAULT_JSON = Path(__file__).with_name("branches.json")

# ── 内部 ────────────────────────────────────────────────
def _load(path: Path = DEFAULT_JSON) -> List[str]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        obj = json.load(f)
    # 古い dict 形式だった場合も壊れないように救済
    if isinstance(obj, dict) and "suffixes" in obj:
        return obj["suffixes"]
    if isinstance(obj, list):
        return obj
    return []

def _save(suffixes: List[str], path: Path = DEFAULT_JSON) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump({"suffixes": sorted(set(suffixes))}, f, ensure_ascii=False, indent=2)

# ── 公開 API ────────────────────────────────────────────
def register_suffix(suffix: str, *, json_path: Path | None = None) -> None:
    """枝番を追加登録（重複は無視）"""
    path = json_path or DEFAULT_JSON
    data = _load(path)
    if suffix not in data:
        data.append(suffix)
        _save(data, path)

def list_suffixes(*, json_path: Path | None = None) -> List[str]:
    """登録済み枝番一覧"""
    return _load(json_path or DEFAULT_JSON)