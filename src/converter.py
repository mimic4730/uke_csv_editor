# src/converter.py
from __future__ import annotations
from typing import Callable, Iterable, List, Tuple
import re

def convert_rows(
    rows: Iterable[List[str]],
    regex: re.Pattern,                 # Highlighter が作った正規表現（患者コード）
    trailing_commas: int,
    primary_fn: Callable[[str], str],  # 第1段: 通常変換（枝番モード等を反映）
    fallback_fn: Callable[[str], str], # 第2段: 先頭4桁除去→6桁（枝番無視）
) -> Tuple[List[str], List[List[str]], List[List[str]]]:
    """
    rows を UKE 文字列に再構成しつつ、患者コードを変換する。
    返り値:
      - out_lines: 変換後の全行（CRLF なしの一行文字列）
      - changes_rows: [line_no, original_code, converted_code, original_line, converted_line, method]
      - error_rows:   [line_no, matched_codes, error_reason, original_line]
    """
    out_lines: List[str] = []
    changes_rows: List[List[str]] = []
    error_rows:   List[List[str]] = []

    # --- “RE フィールド”以降だけが対象 ---
    RE_FIELD = re.compile(r'(^|,)\s*"?RE"?\s*(,|$)', re.IGNORECASE)

    # 置換フォーマット（患者コードの直後に続く空フィールド数）
    tc   = "," * trailing_commas
    tc_re = re.escape(tc)

    # --- フォールバック検出（10桁・クォート対応・フィールド境界・直後に空フィールド）---
    #   例: ,0000004680,,   や ,"0000004680",,
    FALLBACK_PAT_10 = re.compile(rf'(?<=,)"?(\d{{10}})"?(?={tc_re}(?:,|$))')

    for idx, row in enumerate(rows, 1):
        line = ",".join(row)

        # RE 不在はそのまま通す
        m_re = RE_FIELD.search(line)
        if not m_re:
            out_lines.append(line)
            continue

        head = line[:m_re.end()]
        tail = line[m_re.end():]

        # --- 第0段: 主検出 ---
        matches = list(regex.finditer(tail))
        if not matches:
            # 主検出0件 → フォールバックだけを試す
            fallback_changed = False

            def _repl_fb(m: re.Match) -> str:
                nonlocal fallback_changed
                old = m.group(1)
                new = fallback_fn(old)
                if new != old:
                    fallback_changed = True
                    changes_rows.append([str(idx), old, new, line, None, "fallback"])
                return f",{new}{tc}"

            tail_fixed_fb = FALLBACK_PAT_10.sub(_repl_fb, tail)
            if fallback_changed:
                fixed_line_fb = head + tail_fixed_fb
                out_lines.append(fixed_line_fb)
                # converted_line を埋める
                for r in changes_rows:
                    if r[0] == str(idx) and r[4] is None:
                        r[4] = fixed_line_fb
                continue

            error_rows.append([str(idx), "", "no_code_detected", line])
            out_lines.append(line)
            continue

        # --- 第1段: 通常変換 ---
        changed_any_1 = False
        matched_codes: List[str] = []

        def _repl_primary(m: re.Match) -> str:
            nonlocal changed_any_1
            old = m.group(1)
            new = primary_fn(old)
            matched_codes.append(old)
            if new != old:
                changed_any_1 = True
                changes_rows.append([str(idx), old, new, line, None, "normal"])
            return f",{new}{tc}"

        tail_fixed_1 = regex.sub(_repl_primary, tail)
        fixed_line_1 = head + tail_fixed_1

        if not changed_any_1 and fixed_line_1 == line:
            # --- 第2段: フォールバック ---
            changed_any_2 = False

            def _repl_fallback(m: re.Match) -> str:
                nonlocal changed_any_2
                old = m.group(1)
                new = fallback_fn(old)
                if new != old:
                    changed_any_2 = True
                    changes_rows.append([str(idx), old, new, line, None, "fallback"])
                return f",{new}{tc}"

            # 主パターンで置換 → 念のため10桁専用でも置換
            tail_fixed_2 = regex.sub(_repl_fallback, tail)
            tail_fixed_2 = FALLBACK_PAT_10.sub(_repl_fallback, tail_fixed_2)
            fixed_line_2 = head + tail_fixed_2

            if changed_any_2 and fixed_line_2 != line:
                out_lines.append(fixed_line_2)
                for r in changes_rows:
                    if r[0] == str(idx) and r[4] is None:
                        r[4] = fixed_line_2
                continue

            # 最終的に変わらない → エラー
            joined = " ".join(dict.fromkeys(matched_codes))
            error_rows.append([str(idx), joined, "no_change", line])
            out_lines.append(line)
            continue

        # 第1段で変換済み
        out_lines.append(fixed_line_1)
        for r in changes_rows:
            if r[0] == str(idx) and r[4] is None:
                r[4] = fixed_line_1

    return out_lines, changes_rows, error_rows