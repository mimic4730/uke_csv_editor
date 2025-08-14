# src/editor.py
from pathlib import Path
import csv, chardet
from datetime import datetime
from typing import List, Tuple


def _detect_encoding(path: Path, sample_bytes: int = 4096) -> str:
    """バイト先頭をサンプリングして文字コード推定（fallback は UTF-8）"""
    with path.open("rb") as f:
        raw = f.read(sample_bytes)
    guess = chardet.detect(raw)
    enc     = guess.get("encoding") or ""
    conf    = guess.get("confidence") or 0.0

    # chardet が高精度で当てられている場合はそのまま返す
    if enc and conf >= 0.80 and enc.lower() not in {"ascii", "iso-8859-1"}:
        return enc

    # ここからフォールバック作戦 -------------------------------
    candidates = [
        "utf-8-sig",  # UTF-8 BOM 付きを優先
        "utf-8",
        "cp932",      # Windows 日本語 (Shift-JIS superset)
        "shift_jis",
        "euc_jp",
        "iso2022_jp",
    ]
    best_enc: str = "utf-8"
    best_score    = float("inf")

    for cand in candidates:
        try:
           txt = raw.decode(cand)
        except UnicodeDecodeError:
            continue
        # � (U+FFFD) の出現率でスコアリング
        bad = txt.count("�")
        if bad < best_score:
            best_score = bad
            best_enc   = cand
            if bad == 0:   # パーフェクトなら即決
                break

    return best_enc

def _detect_dialect(path: Path, encoding: str) -> csv.Dialect:
    """
    区切り文字を推定。失敗したら
      1) カンマ
      2) タブ
      3) 単一列（擬似的にカンマ区切り扱い）
    の順でフォールバックする。
    """
    with path.open("r", encoding=encoding, errors="replace", newline="") as f:
        sample = f.read(2048)

    sniffer = csv.Sniffer()
    for delimiters in (",;\t", "\t", ","):
        try:
            return sniffer.sniff(sample, delimiters=delimiters)
        except csv.Error:
            continue  # 推定失敗、次の候補へ

    # ここまで来たら「区切りなし」と判断し、単一列ダイアレクトを作る
    class _SingleCol(csv.Dialect):
        delimiter = "\x1f"         # まず出現しない制御文字
        quotechar = '"'
        doublequote = True
        skipinitialspace = False
        lineterminator = "\n"
        quoting = csv.QUOTE_MINIMAL
    return _SingleCol

def load_csv(path: Path, has_header: bool = True) -> Tuple[List[str], List[List[str]]]:
    """
    CSV 全体を読み込み、ヘッダ(List[str]) と 行データ(List[List[str]]) を返す。
    has_header=False なら1行目をデータとして扱う。
    """
    enc = _detect_encoding(path)
    dialect = _detect_dialect(path, enc)

    with path.open("r", encoding=enc, newline="") as f:
        reader = csv.reader(f, dialect)
        rows = list(reader)

    if not rows:
        return [], []

    if has_header:
        header, body = rows[0], rows[1:]
    else:
        header, body = [], rows
    return header, body

def ensure_output_dirs(input_path: str | Path) -> tuple[Path, Path]:
    """
    入力ファイルと同じディレクトリ配下に
      - 「修正後UKE_yyyymmdd」
      - 「修正ログ_yyyymmdd」
    を作成して返す
    """
    base = Path(input_path).resolve().parent
    date_str = datetime.now().strftime("%Y%m%d")
    uke_dir = base / f"修正後UKE_{date_str}"
    log_dir = base / f"修正ログ_{date_str}"
    uke_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    return uke_dir, log_dir

def _dedup_path(p: Path) -> Path:
    """ファイル名が重複する場合は (2), (3), ... を付けて回避"""
    if not p.exists():
        return p
    stem, suffix = p.stem, p.suffix
    i = 2
    while True:
        cand = p.with_name(f"{stem}({i}){suffix}")
        if not cand.exists():
            return cand
        i += 1

def build_uke_output_path(input_path: str | Path) -> Path:
    """UKE 出力: 修正後UKE_yyyymmdd/修正後_<元ファイル名>"""
    inpath = Path(input_path)
    uke_dir, _ = ensure_output_dirs(inpath)
    out = uke_dir / f"修正後_{inpath.name}"
    return _dedup_path(out)

def build_log_paths(input_path: str | Path, uke_out_path: Path) -> tuple[Path, Path]:
    """
    ログ出力: 修正ログ_yyyymmdd/修正後_<元ファイル名>_changes.csv / _エラー行.csv
    """
    _, log_dir = ensure_output_dirs(input_path)
    changes = log_dir / f"{uke_out_path.stem}_changes.csv"
    errors  = log_dir / f"{uke_out_path.stem}_エラー行.csv"
    return _dedup_path(changes), _dedup_path(errors)