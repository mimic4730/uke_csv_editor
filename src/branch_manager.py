# branch_manager.py
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Literal, Optional

Digits = Literal[1, 2]  # 型ヒント用

# ------------------------------------------------------------
# 保存先: ユーザー領域（AppData\Local\UKE_CSV_Editor\branches.json）
#   - PyInstaller の凍結実行や権限制約でも確実に書き込める場所
#   - 既存の古い保存場所からの「一度きり移行」もサポート
# ------------------------------------------------------------

def _user_app_dir() -> Path:
    # Windows: %LOCALAPPDATA% があれば最優先
    lad = os.getenv("LOCALAPPDATA")
    base = Path(lad) if lad else (Path.home() / "AppData" / "Local")
    return base / "UKE_CSV_Editor"

APP_DIR: Path = _user_app_dir()
APP_DIR.mkdir(parents=True, exist_ok=True)
_DEFAULT_JSON: Path = APP_DIR / "branches.json"

# 旧保存候補（存在すれば移行対象）
_LEGACY_JSONS: List[Path] = [
    # モジュール隣（旧実装）
    Path(__file__).with_name("branches.json"),
    # ホーム直下の隠しフォルダ（旧実装のフォールバック）
    Path.home() / ".uke_editor" / "branches.json",
]

def _migrate_legacy_if_needed() -> None:
    """旧保存場所にデータがあり、新保存先が未作成なら移行する（初回のみ）"""
    if _DEFAULT_JSON.exists():
        return
    for legacy in _LEGACY_JSONS:
        try:
            if legacy.exists():
                data = legacy.read_text(encoding="utf-8")
                # 書き込めたら移行完了
                _DEFAULT_JSON.write_text(data, encoding="utf-8")
                return
        except Exception:
            # 読み/書き失敗は無視して次へ
            pass

_migrate_legacy_if_needed()

# ---------- 内部ユーティリティ ---------- #
def _empty() -> Dict[str, List[str]]:
    return {"suffixes_1d": [], "suffixes_2d": []}

def _normalize_data(data: object) -> Dict[str, List[str]]:
    """
    後方互換を考慮してデータを正規化:
    - 旧スキーマ（list）: 2桁側として扱う
    - 現行スキーマ（dict）: 欠損キーは空で補う
    """
    if isinstance(data, list):
        return {"suffixes_1d": [], "suffixes_2d": sorted(set(map(str, data)))}
    if isinstance(data, dict):
        return {
            "suffixes_1d": sorted(set(map(str, data.get("suffixes_1d", [])))),
            "suffixes_2d": sorted(set(map(str, data.get("suffixes_2d", [])))),
        }
    return _empty()

def _load(path: Optional[Path] = None) -> Dict[str, List[str]]:
    """JSON を dict 形式で取得（存在しなければ空の構造を返す）"""
    p = path or _DEFAULT_JSON
    if not p.exists():
        return _empty()
    try:
        with p.open(encoding="utf-8") as f:
            raw = json.load(f)
        return _normalize_data(raw)
    except Exception:
        # 壊れていたら空で返す
        return _empty()

def _save(data: Dict[str, List[str]], path: Optional[Path] = None) -> None:
    """dict を JSON 書き込み（重複排除＋ソート）"""
    p = path or _DEFAULT_JSON
    norm = {
        "suffixes_1d": sorted(set(map(str, data.get("suffixes_1d", [])))),
        "suffixes_2d": sorted(set(map(str, data.get("suffixes_2d", [])))),
    }
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        json.dump(norm, f, ensure_ascii=False, indent=2)

# ---------- 公開 API ---------- #
def register_suffix(suffix: str, *, json_path: Optional[Path] = None) -> None:
    """
    枝番を登録
      * 1 桁（0〜9） → suffixes_1d
      * 2 桁（00〜99）→ suffixes_2d
    """
    s = suffix.strip()
    if not s.isdigit() or not (1 <= len(s) <= 2):
        raise ValueError("枝番は 0〜99 の数字で入力してください")

    path = json_path or _DEFAULT_JSON
    data = _load(path)
    key = "suffixes_1d" if len(s) == 1 else "suffixes_2d"

    if s not in data[key]:
        data[key].append(s)
        _save(data, path)

def list_suffixes(digits: Optional[Digits] = None, *, json_path: Optional[Path] = None) -> List[str]:
    """
    登録済み枝番を取得
      * digits=1 … 1桁のみ
      * digits=2 … 2桁のみ
      * digits=None … 両方まとめて（桁混在でソート）
    """
    data = _load(json_path or _DEFAULT_JSON)
    if digits == 1:
        return data["suffixes_1d"]
    if digits == 2:
        return data["suffixes_2d"]
    return sorted(data["suffixes_1d"] + data["suffixes_2d"])