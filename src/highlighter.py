#!/usr/bin/env python3
"""患者コードのハイライト専用モジュール"""

from __future__ import annotations
import re
from typing import List, Tuple


class Highlighter:
    """
    Text ウィジェットに対して

    * 全件ハイライト（黄）
    * 1 件だけハイライト（緑）
    * 枝番一致部分ハイライト（赤）

    を切り替え描画するユーティリティ
    """

    # ---------------- 初期化 ----------------
    def __init__(self, text_widget):
        self.txt = text_widget

        # タグ定義
        self.txt.tag_configure("hit",    background="#ffff66", foreground="#000000")
        self.txt.tag_configure("single", background="#a0ffa0", foreground="#000000")
        self.txt.tag_configure("branch", background="#ff6666", foreground="#000000")

        # 状態
        self.regex: re.Pattern | None = None
        self.branch_mode: int = 0          # 0=off / 1=1桁 / 2=2桁
        self.br_1d: List[str] = []         # 登録済み枝番
        self.br_2d: List[str] = []
        # (start, end, tag) -- tag は hit / single
        self.matches: List[Tuple[str, str, str]] = []
        # 枝番だけを塗るための区間
        self.branch_spans: List[Tuple[str, str]] = []
        self.focus_idx: int = -1           # -1 = 全件モード

    # ---------------- 設定 ----------------
    def set_regex(self, patient_len: int, trailing_commas: int):
        self.regex = re.compile(rf",([0-9]{{{patient_len}}}){','*trailing_commas}")

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

    # ---------------- スキャン ----------------
    def scan(
        self,
        rows: List[List[str]],
        display_indices: List[int],
        line_starts: List[str],
    ):
        """行データを走査して self.matches を更新"""
        self.matches.clear()
        self.branch_spans.clear()
        
        if self.regex is None:
            return

        for disp_idx, row_idx in enumerate(display_indices):
            row_string = "|".join(rows[row_idx])
            print(rows[0][0])
            if not rows[row_idx]:
                continue

            cell0 = rows[row_idx][0].strip().strip('"')
            # 行全体が 1 セルの場合は先頭カンマまでを取り出す
            rec_type = cell0.split(",", 1)[0]
            if rec_type != "RE":
                continue
            row_string = "|".join(rows[row_idx])
            for m in self.regex.finditer(row_string):
                line = int(float(line_starts[disp_idx]))        # 1-indexed

                code = m.group(1)
                tag  = "hit"

                # 枝番処理 --------------------------
                if self.branch_mode == 1 and len(code) >= 1:
                    if code[-1:] in self.br_1d:
                        suf_ofs = len(code) - 1
                        b_s = f"{line}.{m.start()+1+suf_ofs}"
                        b_e = f"{line}.{m.start()+1+suf_ofs+1}"
                        self.branch_spans.append((b_s, b_e))
                elif self.branch_mode == 2 and len(code) >= 2:
                    if code[-2:] in self.br_2d:
                        suf_ofs = len(code) - 2
                        b_s = f"{line}.{m.start()+1+suf_ofs}"
                        b_e = f"{line}.{m.start()+1+suf_ofs+2}"
                        self.branch_spans.append((b_s, b_e))

                start = f"{line}.{m.start()}"
                end   = f"{line}.{m.end()}"
                self.matches.append((start, end, tag))

    # ---------------- 描画 ----------------
    def _clear_tags(self):
        self.txt.tag_remove("hit", "1.0", "end")
        self.txt.tag_remove("single", "1.0", "end")
        self.txt.tag_remove("branch", "1.0", "end")

    def draw_all(self):
        """全件（黄 or 赤）モードで描画"""
        self.focus_idx = -1
        self.txt.config(state="normal")
        self._clear_tags()
        for s, e, tag in self.matches:
            self.txt.tag_add(tag, s, e)           # hit / single
        for s, e in self.branch_spans:            # 枝番部分を赤で上書き
            self.txt.tag_add("branch", s, e)
        self.txt.config(state="disabled")

    def draw_single(self, idx: int):
        """idx 番目を緑／赤でフォーカス描画"""
        if not self.matches:
            return
        self.focus_idx = idx % len(self.matches)
        s, e, tag = self.matches[self.focus_idx]
        # 緑優先 → 枝番一致でもフォーカス時は緑に
        focus_tag = "single" if tag == "hit" else "branch"
        self.txt.config(state="normal")
        self._clear_tags()
        self.txt.tag_add(focus_tag, s, e)         # コード全体 (緑／黄)
        for b_s, b_e in self.branch_spans:        # 赤は常に重ねる
            self.txt.tag_add("branch", b_s, b_e)
        self.txt.see(s)
        self.txt.config(state="disabled")