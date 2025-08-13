# processor.py
import re
from typing import Iterable

RE_TOKEN = re.compile(r'(?<![A-Z])RE(?![A-Z])')  # 単独の "RE" を検出（英字に隣接しない）

def row_has_re(row: Iterable[str]) -> bool:
    # 行全体から RE を探す。UIがハイライトしているのと同等の最低限の判定。
    joined = " ".join(map(lambda x: x if isinstance(x, str) else str(x), row))
    return bool(RE_TOKEN.search(joined))

def convert_patient_code_if_needed(row: list[str], code_col_index: int) -> tuple[list[str], bool, str | None]:
    """
    患者コードの変換を実施。
    戻り値: (新しい行, 変換を実行したか, スキップ理由)
    - スキップ理由の例: "missing_branch", "digit_mismatch", None（変換した）
    """
    new_row = row[:]  # シャローコピー
    code = (row[code_col_index] or "").strip()

    # ここをあなたの変換条件に合わせて実装：
    # 例：枝番付き想定 "123456-01"（ハイフン+2桁）でなければ対象外
    if "-" not in code:
        return new_row, False, "missing_branch"

    head, tail = code.split("-", 1)
    if not (head.isdigit() and tail.isdigit() and len(tail) == 2):
        return new_row, False, "digit_mismatch"

    # 例の変換処理（必要に応じて修正してください）
    # new_code = head + tail  # とか、所望の形式へ
    new_code = f"{head}{tail}"  # ダミー例
    new_row[code_col_index] = new_code
    return new_row, True, None


def process_rows_with_error_capture(
    rows: list[list[str]],
    code_col_index: int,
) -> tuple[list[list[str]], list[list[str]]]:
    """
    全行を処理。RE があるのに変換されなかった行を error_rows に収集。
    戻り値: (処理後行, エラー行)
    """
    out_rows: list[list[str]] = []
    error_rows: list[list[str]] = []

    # 先頭行がヘッダなら、必要に応じて保持
    header = rows[0]
    data_rows = rows[1:] if header else rows

    out_rows.append(header)

    for r in data_rows:
        new_r, converted, skip_reason = convert_patient_code_if_needed(r, code_col_index)
        out_rows.append(new_r)
        if (not converted) and row_has_re(r):
            # 末尾にエラー理由の列を追加して書き出しやすく
            error_rows.append(new_r + [skip_reason or "unknown"])
    return out_rows, error_rows