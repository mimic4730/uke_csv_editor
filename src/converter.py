# src/converter.py
from __future__ import annotations
from typing import Callable, Iterable, List, Tuple
import re

def convert_rows(
    rows: Iterable[List[str]],
    regex: re.Pattern,                  # Highlighterの検出パターン（第1段）
    trailing_commas: int,
    primary_fn: Callable[[str], str],   # 第1段: 通常変換
    fallback_fn: Callable[[str], str],  # 第2段: フォールバック本体（右端 out_len 桁）
    *,
    fallback_in_len: int,               # ← 追加：フォールバック対象の入力桁数（例: 12-2=10）
    fallback_out_len: int,              # ← 追加：フォールバックの出力桁数（例: 6）
) -> Tuple[List[str], List[List[str]], List[List[str]]]:
    out_lines: List[str] = []
    changes_rows: List[List[str]] = []
    error_rows:   List[List[str]] = []

    RE_FIELD = re.compile(r'(^|,)\s*"?RE"?\s*(,|$)', re.IGNORECASE)

    tc   = "," * trailing_commas
    tc_re = re.escape(tc)

    # === 可変長フォールバック検出：,(\d{N})<カンマ*trailing_commas> のみを対象（クォート対応）
    # 例: ,0000004680,,  / ,"0000004680",,
    FALLBACK_PAT_VAR = re.compile(
        rf'(?<=,)"?(\d{{{fallback_in_len}}})"?(?={tc_re}(?:,|$))'
    )

    for idx, row in enumerate(rows, 1):
        line = ",".join(row)

        m_re = RE_FIELD.search(line)
        if not m_re:
            out_lines.append(line)
            continue

        head = line[:m_re.end()]
        tail = line[m_re.end():]

        # --- 第0段：主検出 ---
        matches = list(regex.finditer(tail))
        if not matches:
            # 主検出0件 → フォールバックのみ
            changed = False

            def _repl_fb(m: re.Match) -> str:
                nonlocal changed
                old = m.group(1)
                # 入力桁= fallback_in_len が保証されている前提で、右端 fallback_out_len 桁へ
                new = fallback_fn(old)
                if new != old:
                    changed = True
                    changes_rows.append([str(idx), old, new, line, None, "fallback"])
                return new

            tail_fixed = FALLBACK_PAT_VAR.sub(_repl_fb, tail)
            if changed:
                fixed = head + tail_fixed
                out_lines.append(fixed)
                for r in changes_rows:
                    if r[0] == str(idx) and r[4] is None:
                        r[4] = fixed
                continue

            error_rows.append([str(idx), "", "no_code_detected", line])
            out_lines.append(line)
            continue

        # --- 第1段：通常変換 ---
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
            # --- 第2段：可変長フォールバック（Highlighterのregexには適用しない）---
            changed_any_2 = False

            def _repl_fb2(m: re.Match) -> str:
                nonlocal changed_any_2
                old = m.group(1)
                new = fallback_fn(old)
                if new != old:
                    changed_any_2 = True
                    changes_rows.append([str(idx), old, new, line, None, "fallback"])
                return new

            tail_fixed_2 = FALLBACK_PAT_VAR.sub(_repl_fb2, tail)
            fixed_line_2 = head + tail_fixed_2

            if changed_any_2 and fixed_line_2 != line:
                out_lines.append(fixed_line_2)
                for r in changes_rows:
                    if r[0] == str(idx) and r[4] is None:
                        r[4] = fixed_line_2
                continue

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