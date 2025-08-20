#!/usr/bin/env python3
"""患者コードのハイライト専用モジュール"""

from __future__ import annotations

import tkinter as tk 
import re
from typing import List, Tuple



class Highlighter:
    
    # ---------------- 初期化 ----------------
    def __init__(self, text_widget):
        self.txt = text_widget

        # タグ定義
        self.txt.tag_configure("hit",    background="#ffff66", foreground="#000000")
        self.txt.tag_configure("single", background="#a0ffa0", foreground="#000000")
        self.txt.tag_configure("branch", background="#ff6666", foreground="#000000")
        self.txt.tag_configure("prefix", background="#99ddff", foreground="#000000")
        self.txt.tag_configure("re",     background="#ffff66", foreground="#000000")

        # 状態
        self.regex: re.Pattern | None = None
        self.branch_mode: int = 0          # 0=off / 1=1桁 / 2=2桁
        self.br_1d: List[str] = []         # 登録済み枝番1桁
        self.br_2d: List[str] = []         # 登録済み枝番２桁
        self.base_code_len = None  # 初期桁数        
        self.allowed_code_lengths: list[int] | None = None  # 許容桁数   
        
        # (start, end, tag) -- tag は hit / single
        self.matches: List[Tuple[str, str, str]] = []
        # 枝番だけを塗るための区間
        self.branch_spans: List[Tuple[str, str]] = []
        self.focus_idx: int = -1           # -1 = 全件モード
        self.prefix_spans: List[Tuple[str, str]] = [] # ハイフンより前
        
        # RE
        self.re_spans: list[tuple[str, str]] = []
        self.re_line_count = 0
        self.no_re_line_count = 0
        self.re_token_count = 0

    # ---------------- 設定 ----------------
    def set_regex(self, pattern: re.Pattern | None):
            self.regex = pattern

    def set_branch_mode(
        self,
        mode: int,
        suffixes_1d: List[str],
        suffixes_2d: List[str],
    ):
        """mode=0/1/2 と枝番リストを受け取って内部状態を更新"""
        self.branch_mode = mode
        self.br_1d = suffixes_1d
        self.br_2d = suffixes_2d

    def set_base_code_len(self, n: int | None):
        self.base_code_len = n

    def set_allowed_code_lengths(self, lengths: list[int] | None):
        """後方カンマモード時に許容するコード桁（例: [10, 12]）"""
        if lengths:
            self.allowed_code_lengths = sorted({int(L) for L in lengths if isinstance(L, int) and L > 0})
        else:
            self.allowed_code_lengths = None

    def _build_regex(self, n_digits: int, trailing_commas: int, detect_mode: int, custom_sym: str) -> re.Pattern:
        charclass = r"[0-9\-]"

        if detect_mode == 0:  # 後方カンマモード
            tc = "," * trailing_commas
            lengths = self.allowed_code_lengths or [n_digits]  # ★許容桁セットがあれば使う
            group = "|".join(rf"{charclass}{{{L}}}" for L in lengths)
            return re.compile(rf",\s*({group})\s*{tc}")

        # 任意記号モード（従来通り）
        rng = f"{{1,{n_digits}}}"
        sym = re.escape(custom_sym or "*")
        return re.compile(rf",\s*({charclass}{rng})\s*{sym}")

    # ---------------- スキャン ----------------
    def scan(self, rows, display_indices, line_starts):
        """行データを走査して self.matches / self.re_spans を更新"""
        self.matches.clear()
        self.branch_spans.clear()
        self.prefix_spans.clear()
        self.re_spans.clear()
        # ★ 統計をリセット
        self.re_line_count = 0
        self.no_re_line_count = 0
        self.re_token_count = 0
        
        base = getattr(self, "base_code_len", None)

        detect_mode = getattr(self, "detect_mode_current", 0)
        if self.regex is None:
            return

        RE_FIELD = re.compile(r'(?:(^|,))\s*"?RE"?\s*(?:(,|$))', re.IGNORECASE)

        for disp_idx, row_idx in enumerate(display_indices):
            if not rows[row_idx]:
                continue

            # ★ 1セル=生UKE行の想定を維持。将来分割されたら要調整
            raw_line = rows[row_idx][0] if len(rows[row_idx]) == 1 else ",".join(rows[row_idx])
            line_no = int(float(line_starts[disp_idx]))  # "N.0" → N

            # 行内の RE を全部拾う（ハイライト用 & 統計用）
            re_iters = list(RE_FIELD.finditer(raw_line))
            if not re_iters:
                self.no_re_line_count += 1
                continue

            self.re_line_count += 1
            self.re_token_count += len(re_iters)

            # ★ 各 RE の "RE" 文字部分だけ黄色で塗る
            for m_re in re_iters:
                inner = re.search(r'RE', raw_line[m_re.start():m_re.end()], re.IGNORECASE)
                if inner:
                    re_s = m_re.start() + inner.start()
                    re_e = re_s + 2
                    self.re_spans.append((f"{line_no}.{re_s}", f"{line_no}.{re_e}"))

            # ★ 既存の患者コードスキャンは「先頭の RE 以降」を対象
            search_from = re_iters[0].end()
            for m in self.regex.finditer(raw_line, search_from):
                code = m.group(1)

                if detect_mode == 1 and "-" in code:
                    p_start = f"{line_no}.{m.start(1)}"
                    p_end   = f"{line_no}.{m.start(1) + code.find('-')}"
                    self.prefix_spans.append((p_start, p_end))

                # 枝番着色
                if self.branch_mode == 1 and base and len(code) == base + 1 and code[-1:] in self.br_1d:
                    suf_ofs = len(code) - 1
                    b_s = f"{line_no}.{m.start(1)+suf_ofs}"
                    b_e = f"{line_no}.{m.start(1)+suf_ofs+1}"
                    self.branch_spans.append((b_s, b_e))
                elif self.branch_mode == 2 and base and len(code) == base + 2 and code[-2:] in self.br_2d:
                    suf_ofs = len(code) - 2
                    b_s = f"{line_no}.{m.start(1)+suf_ofs}"
                    b_e = f"{line_no}.{m.start(1)+suf_ofs+2}"
                    self.branch_spans.append((b_s, b_e))

                start = f"{line_no}.{m.start()}"
                end   = f"{line_no}.{m.end()}"
                self.matches.append((start, end, "hit"))

    # ---------------- 描画 ----------------
    def _clear_tags(self):
        self.txt.tag_remove("hit", "1.0", "end")
        self.txt.tag_remove("single", "1.0", "end")
        self.txt.tag_remove("branch", "1.0", "end")
        self.txt.tag_remove("prefix", "1.0", "end")
        self.txt.tag_remove("re", "1.0", "end")

    def draw_all(self):
        self.focus_idx = -1
        self.txt.config(state="normal")
        self._clear_tags()
        # コード全件
        for s, e, tag in self.matches:
            self.txt.tag_add(tag, s, e)
        # 枝番
        for s, e in self.branch_spans:
            self.txt.tag_add("branch", s, e)
        # 任意記号の前半
        for s, e in self.prefix_spans:
            self.txt.tag_add("prefix", s, e)
        # ★ REタグ（最後でもOK。コードと位置が被らない想定）
        for s, e in self.re_spans:
            self.txt.tag_add("re", s, e)
        self.txt.config(state="disabled")

    def draw_single(self, idx: int):
        if not self.matches:
            return
        self.focus_idx = idx % len(self.matches)
        s, e, tag = self.matches[self.focus_idx]
        focus_tag = "single" if tag == "hit" else "branch"
        self.txt.config(state="normal")
        self._clear_tags()
        self.txt.tag_add(focus_tag, s, e)
        for b_s, b_e in self.branch_spans:
            self.txt.tag_add("branch", b_s, b_e)
        for ps, pe in self.prefix_spans:
            self.txt.tag_add("prefix", ps, pe)
        # ★ REタグも常に表示
        for rs, re_ in self.re_spans:
            self.txt.tag_add("re", rs, re_)
        self.txt.see(s)
        self.txt.config(state="disabled")