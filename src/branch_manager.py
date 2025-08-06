# branch_manager.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Literal

# 保存先 …/src/branches.json
_DEFAULT_JSON = Path(__file__).with_name("branches.json")

Digits = Literal[1, 2]   # 型ヒント用

# ---------- 内部ユーティリティ ---------- #
def _empty() -> Dict[str, List[str]]:
    return {"suffixes_1d": [], "suffixes_2d": []}


def _load(path: Path = _DEFAULT_JSON) -> Dict[str, List[str]]:
    """JSON を dict 形式で取得（存在しなければ空の構造を返す）"""
    if not path.exists():
        return _empty()

    with path.open(encoding="utf-8") as f:
        data = json.load(f)

    # ↓ 後方互換：旧スキーマ（suffixes のみ）を 2 桁リストとして扱う
    if isinstance(data, list):
        return {"suffixes_1d": [], "suffixes_2d": sorted(set(data))}
    if isinstance(data, dict):
        return {
            "suffixes_1d": sorted(set(data.get("suffixes_1d", []))),
            "suffixes_2d": sorted(set(data.get("suffixes_2d", []))),
        }
    return _empty()


def _save(data: Dict[str, List[str]], path: Path = _DEFAULT_JSON) -> None:
    """dict を JSON 書き込み（重複排除＋ソート）"""
    data = {
        "suffixes_1d": sorted(set(data["suffixes_1d"])),
        "suffixes_2d": sorted(set(data["suffixes_2d"])),
    }
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- 公開 API ---------- #
def register_suffix(suffix: str, *, json_path: Path | None = None) -> None:
    """
    枝番を登録  
    * 1 桁（0〜9） → suffixes_1d へ  
    * 2 桁（00〜99）→ suffixes_2d へ
    """
    if not suffix.isdigit() or not (1 <= len(suffix) <= 2):
        raise ValueError("枝番は 0〜99 の数字で入力してください")

    path = json_path or _DEFAULT_JSON
    data = _load(path)

    key: str = "suffixes_1d" if len(suffix) == 1 else "suffixes_2d"
    if suffix not in data[key]:
        data[key].append(suffix)
        _save(data, path)


def list_suffixes(digits: Digits | None = None,
                  *, json_path: Path | None = None) -> List[str]:
    """
    登録済み枝番を取得  
    * digits=1 … 1 桁のみ  
    * digits=2 … 2 桁のみ  
    * digits=None … 両方まとめて（桁混在でソート）
    """
    data = _load(json_path or _DEFAULT_JSON)
    if digits == 1:
        return data["suffixes_1d"]
    if digits == 2:
        return data["suffixes_2d"]
    # None → 全部
    return sorted(data["suffixes_1d"] + data["suffixes_2d"])