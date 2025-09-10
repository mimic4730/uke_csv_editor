# src/gui.py
import datetime, re, tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from typing import List, Optional
import json
import csv

import branch_manager as bm
import highlighter
from editor import load_csv
import converter
import reconcile_patient_codes as rpc

DISPLAY_COL = 0   # フィルタ用列（先頭列）
MAX_TRAILING_COMMAS = 30
APP_VERSION = "v2.1.1"

class UKEEditorGUI(tk.Tk):
    # ────────────────────────── 初期化 ──────────────────────────
    def __init__(self) -> None:
        super().__init__()
        self.title(f"UKE CSV Editor {APP_VERSION}")
        self.geometry("900x540")
        self.minsize(900, 540)
        self.resizable(True, True)        

        # === データ ===
        self.file_path: Optional[Path] = None
        self.rows: List[List[str]] = []
        self.display_indices: List[int] = []

        # === GUI 部品 === -------------------------------------------------
        self._build_toolbar()
        self._build_text_area()
        self._build_statusbar()

        # === その他の状態 ===
        self.patient_code_len = 10
        self.patient_code_conv_len = 10
        self.trailing_commas = 2
        self.noise_marks = "*＊※★"  # よくある星印群（任意で編集）

        # Highlighter インスタンス
        self.detect_mode = tk.IntVar(value=0)   # 0=後方カンマ, 1=任意記号
        self.custom_sym  = tk.StringVar(value=",")
        self.hl = highlighter.Highlighter(self.row_text)
        self.hl.detect_mode_current = self.detect_mode.get()
        self.highlight_pat = None
        
        # 前回サイズを復元・終了時に保存
        self._restore_geometry()
        self.protocol("WM_DELETE_WINDOW", self._save_geometry_and_quit)        
        
        # 初回ロード
        _ = bm.list_suffixes(1); _ = bm.list_suffixes(2)
        self.bind_all("<Control-b>", lambda e: self.register_branches())
        
        # 枝番表示パネル
        self._build_suffix_panel()
        self._refresh_suffix_panel()

    # ────────────────────────── UI 構築 ──────────────────────────
    def _build_toolbar(self):
        self.br_mode = tk.IntVar(value=0)
        # 1段目
        f1 = tk.Frame(self); f1.pack(pady=4, anchor="w")
        tk.Button(f1, text="読み込みファイルをリネーム", width=20,
                  command=self.rename_files).grid(row=0, column=0, padx=4, sticky="w")
        tk.Button(f1, text="ファイル読み込み", width=18,
                  command=self.load_file).grid(row=0, column=1, padx=4, sticky="w")
        tk.Button(f1, text="全行表示", width=18,
                  command=lambda: (self.row_lb.selection_clear(0, tk.END),
                                   self.filter_by_code(None))).grid(row=0, column=2, padx=4, sticky="w")
        tk.Button(f1, text="設定", width=18,
                  command=self.open_settings).grid(row=0, column=3, padx=4, sticky="w")
        tk.Button(f1, text="患者コード照合（ログ×患者CSV）", width=28,
              command=lambda: rpc.run_reconcile_dialog(self)).grid(row=0, column=4, padx=4, sticky="w")

        # 2段目（ハイライト）
        f2 = tk.Frame(self); f2.pack(pady=2, anchor="w")
        tk.Button(f2, text="患者コード・全行ハイライト", width=20,
                  command=self.highlight_all_matches).grid(row=0, column=0, padx=4, sticky="w")
        tk.Button(f2, text="先頭 1 件ハイライト", width=18,
                  command=self.highlight_first_match).grid(row=0, column=1, padx=4, sticky="w")
        tk.Button(f2, text="次の行へ", width=18,
                  command=self.highlight_next_match).grid(row=0, column=2, padx=4, sticky="w")
        tk.Button(f2, text="ハイライト解除", width=18,
                  command=self.clear_highlight).grid(row=0, column=3, padx=4, sticky="w")

    def _build_suffix_panel(self):
        """登録済み枝番をUIに常時表示（1桁/2桁）"""
        wrap = tk.Frame(self); wrap.pack(pady=(0,2), padx=8, anchor="w", fill="x")

        tk.Label(wrap, text="登録済み枝番:", font=("", 9, "bold")).grid(row=0, column=0, sticky="w", padx=(0,8))

        self.suffix_ones_var = tk.StringVar(value="")
        self.suffix_twos_var = tk.StringVar(value="")

        # 1桁
        tk.Label(wrap, text="1桁").grid(row=0, column=1, sticky="w")
        tk.Label(wrap, textvariable=self.suffix_ones_var, relief="groove", anchor="w")\
            .grid(row=0, column=2, sticky="we", padx=(4,16))

        # 2桁
        tk.Label(wrap, text="2桁").grid(row=0, column=3, sticky="w")
        tk.Label(wrap, textvariable=self.suffix_twos_var, relief="groove", anchor="w")\
            .grid(row=0, column=4, sticky="we", padx=(4,0))

        # 横幅に合わせて広がるように
        wrap.grid_columnconfigure(2, weight=1)
        wrap.grid_columnconfigure(4, weight=1)

    def _build_text_area(self):
        list_frame = tk.Frame(self); list_frame.pack(pady=4, fill=tk.BOTH, expand=True)

        # 左: 2桁コードのリスト
        self.row_lb = tk.Listbox(list_frame, width=6)
        self.row_lb.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))
        self.row_lb.bind("<<ListboxSelect>>", self.filter_by_code)
        tk.Label(list_frame, text="コード").pack(side=tk.LEFT, anchor=tk.NW)

        # 右: 行内容
        self.row_text = tk.Text(list_frame, wrap="none", width=120, height=25)
        self.row_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._insert_help_text()

        # 下: 変換して保存
        bottom = tk.Frame(self); bottom.pack(side=tk.BOTTOM, pady=8)
        tk.Button(bottom, text="コード変換して保存", width=18,
                  command=self.convert_and_save).pack()

    def _build_statusbar(self):
        self.status = tk.StringVar(value="ファイル未選択")
        tk.Label(self, textvariable=self.status, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)

    # ────────────────────────── ファイル読み込み・表示 ──────────────────────────
    def load_file(self):
        path = filedialog.askopenfilename(
            title="UKE/CSV ファイル選択",
            filetypes=[("UKE/CSV", "*.UKE *.uke *.csv"), ("すべて", "*")])
        if not path:
            return
        try:
            self.file_path = Path(path)
            _, self.rows = load_csv(self.file_path, has_header=False)
            self.display_indices = list(range(len(self.rows)))
            self._refresh_lists_and_text()
            self.status.set(f"読み込み完了: {self.file_path.name}")
        except Exception as e:
            messagebox.showerror("読み込み失敗", str(e))

    # ────────────────────────── 表示系ユーティリティ ──────────────────────────
    def _refresh_lists_and_text(self):
        self._build_left_codes()
        self._build_text()

    def _build_left_codes(self):
        self.row_lb.delete(0, tk.END)
        seen = set()
        for idx in self.display_indices:
            code = self.rows[idx][DISPLAY_COL][:2] if DISPLAY_COL < len(self.rows[idx]) else ""
            if code not in seen:
                self.row_lb.insert(tk.END, code); seen.add(code)

    def _build_text(self):
        self.row_text.config(state="normal")
        self.row_text.delete("1.0", "end")
        self.line_starts = []

        for idx in self.display_indices:
            self.line_starts.append(self.row_text.index(tk.INSERT))
            self.row_text.insert(tk.END, "|".join(self.rows[idx]) + "\n")

        self.row_text.config(state="disabled")

        # ★ここで表示行数を更新し、ハイライト再描画後に status 表示へ使う
        # 表示行数を保存 → ハイライト再描画
        self.visible_count = len(self.display_indices)
        self._apply_highlight()            # ←従来どおり

        # ★ここでステータスバーを更新
        self._update_status_counts()

    def _count_branch_hits(self) -> tuple[int, int, int]:
        """
        表示中の行(self.display_indices)を RE 以降だけ self.hl.regex で再スキャンして、
        枝番のヒット数を数える（ハイライト結果オブジェクトに依存しない）
        戻り値: (total, one_digit_hits, two_digit_hits)
        """
        if not self.hl.regex:
            return 0, 0, 0

        pat = self.hl.regex
        RE_FIELD = re.compile(r'(^|,)\s*"?RE"?\s*(,|$)', re.IGNORECASE)

        ones = set(bm.list_suffixes(1))
        twos = set(bm.list_suffixes(2))
        
        L = self.patient_code_len; mode = self.br_mode.get()
        ones = set(bm.list_suffixes(1)); twos = set(bm.list_suffixes(2))

        one_hits = two_hits = 0

        for i in self.display_indices:
            if i < 0 or i >= len(self.rows):
                continue
            line = ",".join(self.rows[i])
            m_re = RE_FIELD.search(line)
            if not m_re:
                continue
            tail = line[m_re.end():]

            for m in pat.finditer(tail):
                try:
                    code = m.group('code') if ('code' in m.re.groupindex) else m.group(1)
                except IndexError:
                    code = m.group(0)
                norm = code.replace("-", "")
                hy = code.split("-",1)[1] if "-" in code else ""
                if mode == 2 and len(norm) == L + 2 and ((hy and hy in twos) or (not hy and norm[-2:] in twos)):
                    two_hits += 1
                elif mode == 1 and len(norm) == L + 1 and ((hy and hy in ones) or (not hy and norm[-1:] in ones)):
                    one_hits += 1

        return (one_hits + two_hits), one_hits, two_hits

    def _update_status_counts(self):
        """表示行数とハイライト件数 + RE統計 + 枝番統計（登録数＆ヒット数）をステータスへ反映"""
        hit_cnt   = len(self.hl.matches) if self.hl.regex else 0
        re_lines  = getattr(self.hl, "re_line_count", 0)
        re_none   = getattr(self.hl, "no_re_line_count", self.visible_count - re_lines)
        re_tokens = getattr(self.hl, "re_token_count", 0)

        status_parts = [
            f"表示 {self.visible_count} 行",
            f"ハイライト {hit_cnt} 件",
            f"REあり {re_lines} 行",
            f"REなし {re_none} 行",
            f"RE {re_tokens} 個",
        ]

        # 枝番モードがオフ以外のときだけ統計を追加
        if self.br_mode.get() != 0:
            try:
                ones_cnt = len(bm.list_suffixes(1))
                twos_cnt = len(bm.list_suffixes(2))
            except Exception:
                ones_cnt = twos_cnt = 0

            br_total, br_1hit, br_2hit = self._count_branch_hits()
            status_parts.append(f"枝番 登録: 1桁 {ones_cnt}・2桁 {twos_cnt}")
            status_parts.append(f"枝番ヒット: 合計 {br_total}（1桁 {br_1hit}・2桁 {br_2hit}）")
            status_parts.append(f"モード: {self._branch_mode_label()}")

        self.status.set(" / ".join(status_parts))

    def _refresh_suffix_panel(self):
        """branch_manager から取得して表示を更新"""
        ones = bm.list_suffixes(1)
        twos = bm.list_suffixes(2)

        # 長くなりすぎないよう、空白区切りで表示。多い場合は末尾に…を付与
        def _fmt(xs: list[str], limit_chars: int = 60) -> str:
            s = " ".join(xs)
            return (s[:limit_chars] + "…") if len(s) > limit_chars else s

        self.suffix_ones_var.set(_fmt(ones))
        self.suffix_twos_var.set(_fmt(twos))

    # --- Listbox フィルタ ---
    def filter_by_code(self, _evt):
        sel = self.row_lb.curselection()
        self.display_indices = (
            list(range(len(self.rows))) if not sel else
            [i for i, r in enumerate(self.rows)
            if r[DISPLAY_COL].startswith(self.row_lb.get(sel[0]))]
        )
        self._build_text()

    # ────────────────────────── ハイライト操作 ──────────────────────────
    def _setup_highlighter(self):
        base = self.patient_code_len
        mode = self.br_mode.get()
        self.hl.set_base_code_len(self.patient_code_len)

        # ★後方カンマのときだけ {N, N+枝番桁} を許容
        if self.detect_mode.get() == 0:
            allowed = {base}
            if mode == 1:
                allowed.add(base + 1)
            elif mode == 2:
                allowed.add(base + 2)
            self.hl.set_allowed_code_lengths(sorted(allowed))
        else:
            self.hl.set_allowed_code_lengths(None)  # 任意記号モードは従来通り

        # ノイズ記号は正規表現構築前に反映
        if hasattr(self.hl, "set_noise_marks"):
            self.hl.set_noise_marks(self.noise_marks)

        # ★許容桁セット後にパターンを構築する（順序が大事）
        pattern = self.hl._build_regex(
            n_digits=self.patient_code_len,
            trailing_commas=self.trailing_commas,
            detect_mode=self.detect_mode.get(),
            custom_sym=self.custom_sym.get()
        )
        self.hl.set_regex(pattern)
        self.highlight_pat = pattern
        self.hl.detect_mode_current = self.detect_mode.get()

        self.hl.set_branch_mode(
            self.br_mode.get(),
            bm.list_suffixes(1), bm.list_suffixes(2)
        )

    def highlight_all_matches(self):
        if not self.rows:
            messagebox.showwarning("警告", "まずファイルを読み込んでください"); return
        self._setup_highlighter()
        self.hl.scan(self.rows, self.display_indices, self.line_starts)
        self.hl.draw_all()
        self._update_status_counts() 

    def highlight_first_match(self):
        if not self.rows: return
        self._setup_highlighter()
        self.hl.scan(self.rows, self.display_indices, self.line_starts)
        if not self.hl.matches:
            messagebox.showinfo("検索結果", "該当する患者コードは見つかりませんでした。"); return
        self.hl.draw_single(0)
        self._update_status_counts() 
        self.status.set(
            f"表示 {self.visible_count} 行　/　ハイライト {len(self.hl.matches)} 件"
            f"　(1 / {len(self.hl.matches)})"
        )

    def highlight_next_match(self):
        if not self.hl.matches:
            self.highlight_first_match(); return
        self.hl.draw_single(self.hl.focus_idx + 1)
        self._update_status_counts() 
        self.status.set(
            f"表示 {self.visible_count} 行　/　ハイライト {len(self.hl.matches)} 件"
            f"　({self.hl.focus_idx+1} / {len(self.hl.matches)})"
        )

    def _apply_highlight(self):
        """スクロールやフィルター更新時に再描画"""
        if not self.hl.regex: return
        self._setup_highlighter()
        self.hl.scan(self.rows, self.display_indices, self.line_starts)
        if self.hl.focus_idx >= 0:
            self.hl.draw_single(self.hl.focus_idx)
        else:
            self.hl.draw_all()
        
        self._update_status_counts()

    def clear_highlight(self):
        self.hl.regex = None; self.hl.matches.clear(); self.hl.focus_idx = -1
        self.row_text.config(state="normal")
        self.row_text.tag_remove("hit", "1.0", "end")
        self.row_text.tag_remove("single", "1.0", "end")
        self.row_text.tag_remove("branch", "1.0", "end")
        self.row_text.tag_remove("prefix", "1.0", "end")   
        self.row_text.tag_remove("re", "1.0", "end") 
        self.row_text.config(state="disabled")
        self.status.set(f"表示 {self.visible_count} 行　/　ハイライト 0 件")

    # --- 枝番モード変更時に即時再描画 ---
    def _refresh_branch_mode(self):
        self._apply_highlight()
    
    def _branch_mode_label(self) -> str:
        return {0: "オフ", 1: "1桁除去", 2: "2桁除去"}.get(self.br_mode.get(), "オフ")

    # ────────────────────────── 枝番登録 / 確認 ──────────────────────────
    def register_branches(self):
        suffix = simpledialog.askstring("枝番登録", "枝番 (0〜99) または -0〜-99 を入力", parent=self)
        if not suffix: 
            return
        if not re.fullmatch(r"-?\d{1,2}", suffix):
            messagebox.showwarning("入力エラー", "枝番は 0〜99 または -0〜-99 で入力してください。"); return
        try:
            normalized = suffix.lstrip("-")          # ★ハイフンを落として保存
            bm.register_suffix(normalized)
            msg = f"枝番 {suffix} を登録しました（保存値: {normalized}）"
            messagebox.showinfo("登録完了", msg)
            self._refresh_suffix_panel()
            self._update_status_counts()
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    def show_branches(self):
        ones = bm.list_suffixes(1); twos = bm.list_suffixes(2)
        if not ones and not twos:
            messagebox.showinfo("枝番確認", "登録済み枝番はありません"); return
        body = ""
        if ones: body += "【1 桁】\n" + " ".join(ones) + "\n\n"
        if twos: body += "【2 桁】\n" + " ".join(twos)
        messagebox.showinfo("枝番一覧", body.strip())

    # ---------- 変換ユーティリティ ----------
    def _strip_branch(self, code: str) -> str:
        L = self.patient_code_len
        mode = self.br_mode.get()
        if mode == 1 and len(code) == L + 1 and code[-1:] in bm.list_suffixes(1):
            return code[:-1]
        elif mode == 2 and len(code) == L + 2 and code[-2:] in bm.list_suffixes(2):
            return code[:-2]
        return code
    
    def _format_code(self, raw: str) -> str:
        # ★ハイフン枝番：登録済みのときだけ左側採用
        if "-" in raw:
            left, right = raw.split("-", 1)
            if (self.br_mode.get() == 2 and right in bm.list_suffixes(2)) or \
            (self.br_mode.get() == 1 and right in bm.list_suffixes(1)):
                raw = left  # 枝番除去

        raw = self._strip_branch(raw)      # 連結型の枝番はここで除去（長さガード済み）
        return self._normalize_code(raw)
    
    def _normalize_code(self, code: str) -> str:
        """
        self.patient_code_conv_len で指定された桁数に変換
          - 短くする: 左（先頭）から切り落とす
          - 長くする: 左側に 0 を追加
        """
        L = self.patient_code_conv_len
        if len(code) > L:          # 長い → 左からカット
            return code[-L:]
        else:                      # 短い／同じ → 0 埋め
            return code.zfill(L)

    def _format_code_force_branch_general(self, raw: str, in_len: int, out_len: int) -> str:
        """
        フォールバック汎用版：
        - 枝番設定は無視
        - 入力桁 in_len を想定し、右端 out_len 桁を採用（足りなければ左0埋め）
        """
        s = (raw or "").strip()
        # in_len はマッチ側で保証されるが、念のため数字以外は触らない
        if not s.isdigit():
            return s
        return s[-out_len:].zfill(out_len)

    def convert_and_save(self):
        if not self.rows:
            messagebox.showwarning("警告", "まず CSV ファイルを読み込んでください。")
            return
        if self.hl.regex is None:
            messagebox.showinfo("情報", "ハイライトされた患者コードがありません。")
            return

        pat = self.hl.regex
        tc  = "," * self.trailing_commas
        RE_FIELD = re.compile(r'(^|,)\s*"?RE"?\s*(,|$)', re.IGNORECASE)

        out_lines: list[str] = []
        # [line_no, old_code, new_code, old_line, new_line, method]
        changes_rows: list[list[str]] = []

        # 集計カウンタ
        re_token_total = 0          # RE の出現回数（トークン数）
        target_total   = 0          # 変換対象（RE以降でパターンにヒット）件数
        converted_total= 0          # 実際に値が変わった件数（normal + fallback）
        fallback_total = 0          # フォールバックが発動した件数
        # 未変換理由の分類カウンタ
        unchanged_same_len_rows: list[tuple[int, str]] = []   # (line_no, original_line)
        unchanged_same_len_seen: set[int] = set()             # 重複登録防止
        no_re_rows: list[tuple[int, str]] = []                # (line_no, original_line)
        re_nomatch_rows: list[tuple[int, str]] = []           # (line_no, original_line)
        manual_converted_total = 0
        manual_skipped_total = 0

        # カンマ数検証用
        comma_mismatch_rows: list[tuple[int, int, int]] = []  # (line_no, before, after)

        # フォールバックで落とす桁（枝番モードに追随）
        fallback_drop = 2 if self.br_mode.get() == 2 else (1 if self.br_mode.get() == 1 else 0)

        for idx, row in enumerate(self.rows, 1):  # 行番号は1始まり
            line = ",".join(row)
            # 元行のカンマ個数（検証用）
            orig_commas = line.count(',')

            # 行内の RE を全件カウント（通常は1件想定だが念のため）
            re_all = list(RE_FIELD.finditer(line))
            re_token_total += len(re_all)

            # 変換は先頭の RE 以降のみ
            m_re = re_all[0] if re_all else None
            if not m_re:
                out_lines.append(line)
                no_re_rows.append((idx, line))
                continue

            head = line[:m_re.end()]         # REまで（含む）
            tail = line[m_re.end():]         # RE以降のみ置換対象

            # 置換対象のマッチを先に列挙して件数集計
            matches = list(pat.finditer(tail))
            target_total += len(matches)
            if not matches:
                out_lines.append(line)
                re_nomatch_rows.append((idx, line))
                continue

            # この行の変更記録（置換後に fixed_line を付けてCSVに書く）
            per_line_changes: list[tuple[str, str, str]] = []  # (old, new, method)

            def _repl(m: re.Match) -> str:
                nonlocal converted_total, fallback_total
                old = m.group('code') if ('code' in m.re.groupindex) else m.group(1)
                new = self._format_code(old)   # 通常処理
                method = "normal"

                L = self.patient_code_len
                drop = 2 if self.br_mode.get() == 2 else (1 if self.br_mode.get() == 1 else 0)

                # ★通常処理で不変 かつ 「枝番付き長さ」のときだけ発動
                if new == old and drop > 0 and old.isdigit() and len(old) == L + drop:
                    forced_core = old[:-drop]
                    forced_new  = self._normalize_code(forced_core)
                    if forced_new != old:
                        new = forced_new
                        method = "fallback"
                        fallback_total += 1

                if new != old:
                    converted_total += 1
                else:
                    # 旧→新が同一（normal時）。“元と変換後の桁数が一致”の代表ケースとして記録
                    try:
                        if old.isdigit() and len(old) == self.patient_code_conv_len and idx not in unchanged_same_len_seen:
                            unchanged_same_len_rows.append((idx, line))  # 行全体を保存
                            unchanged_same_len_seen.add(idx)
                    except Exception:
                        pass             

                per_line_changes.append((old, new, method))
                if self.detect_mode.get() == 1:
                    # 任意記号モード：named group 'sym' を優先してそのまま再挿入
                    try:
                        suffix = m.group('sym')
                    except Exception:
                        suffix = m.group(m.lastindex) if (m.lastindex and m.lastindex >= 2) else tc
                    return f",{new}{suffix}"
                else:
                    # 後方カンマモード：設定個数で正規化
                    return f",{new}{tc}"

            tail_fixed = pat.sub(_repl, tail)
            fixed_line = head + tail_fixed
            out_lines.append(fixed_line)

            # カンマ数検証（変更が入った行のみ対象）
            new_commas = fixed_line.count(',')
            if new_commas != orig_commas:
                comma_mismatch_rows.append((idx, orig_commas, new_commas))

            # 変更ログ（converted_line を確定させてからまとめて吐く）
            for old, new, method in per_line_changes:
                changes_rows.append([str(idx), old, new, line, fixed_line, method])

        unchanged_total = max(0, target_total - converted_total)
        
        # --- 必要なら手動変換ダイアログを起動 ---
        # 条件: (1) RE以降で検出した対象に未変換が残っている  or  (2) REはあるが正規表現にマッチしなかった行がある
        should_open_manual = (converted_total < target_total) or bool(re_nomatch_rows)

        if should_open_manual:
            messagebox.showinfo(
                "未変換データの検出",
                f"RE未検出: {len(no_re_rows)} 行 / REありマッチなし: {len(re_nomatch_rows)} 行 / 同桁未変換: {len(unchanged_same_len_rows)} 行\n"
                "手動桁数変換ダイアログを開きます。",
                parent=self
            )
            mc, ms = self._manual_convert_dialog(
                candidates_no_re=no_re_rows,              # NO_RE はダイアログ側デフォルト OFF のまま渡す
                candidates_re_nomatch=re_nomatch_rows,
                candidates_same_len=unchanged_same_len_rows,
                out_lines=out_lines,
                changes_rows=changes_rows
            )
            manual_converted_total += mc
            manual_skipped_total += ms
        # else: すべて変換済み（かつ RE無マッチなし）なのでダイアログは開かない

        
        comma_mismatch_total = len(comma_mismatch_rows)
        # ---- 変換後 UKE の保存先をユーザーに聞く（Save As）----
        base = self.file_path
        assert base is not None

        # デフォルト候補（元ファイル名の前に「修正後_」を付ける）
        default_name = f"修正後_{base.stem}.UKE"

        save_path = filedialog.asksaveasfilename(
            title="変換後UKEを保存",
            initialdir=str(base.parent),
            initialfile=default_name,
            defaultextension=".UKE",
            filetypes=[("UKE ファイル", "*.UKE"), ("すべてのファイル", "*.*")]
        )
        if not save_path:
            messagebox.showinfo("保存を中止", "保存がキャンセルされました。")
            return

        out_path = Path(save_path)

        # ---- UKE本体を書き出し（Shift-JIS/CRLF）----
        with out_path.open("w", encoding="cp932", newline="") as f:
            for L in out_lines:
                f.write(f"{L}\r\n")

        # ---- 変更ログCSV・集計ログは『選んだファイル名』基準で同じフォルダへ ----
        out_dir = out_path.parent
        out_stem = out_path.stem

        map_path = None
        try:
            if changes_rows:
                map_path = out_dir / f"{out_stem}_changes.csv"
                with map_path.open("w", encoding="cp932", newline="") as f:
                    writer = csv.writer(f, lineterminator="\r\n")
                    writer.writerow([
                        "line_no", "original_code", "converted_code",
                        "original_line", "converted_line", "method"
                    ])
                    writer.writerows(changes_rows)
        except Exception as e:
            messagebox.showwarning("警告", f"変更ログの保存に失敗しました: {e}")

        # 集計テキストログ
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_path = out_dir / f"{out_stem}_convert_{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.log.txt"
        try:
            with log_path.open("w", encoding="cp932", newline="") as f:
                # ===== ▼ ここから設定情報を追記 ▼ =====
                detect_mode = self.detect_mode.get()
                detect_label = "後方カンマ" if detect_mode == 0 else "任意の記号"
                branch_label = self._branch_mode_label()
                allowed_lens = getattr(self.hl, "allowed_code_lengths", None) or [self.patient_code_len]
                regex_pat = getattr(self.hl, "regex", None).pattern if getattr(self.hl, "regex", None) else "(none)"
                suf1 = " ".join(bm.list_suffixes(1)) or "(なし)"
                suf2 = " ".join(bm.list_suffixes(2)) or "(なし)"
                f.write(f"Noise Marks        : {getattr(self, 'noise_marks', '') or '(なし)'}\r\n")
                f.write("=== UKE CSV Editor Run Settings ===\r\n")
                f.write(f"Version            : {APP_VERSION}\r\n")
                f.write(f"Detect Mode        : {detect_label}\r\n")
                f.write(f"Highlight Base N   : {self.patient_code_len}\r\n")
                f.write(f"Allowed Lengths    : {', '.join(map(str, allowed_lens))}\r\n")
                if detect_mode == 0:
                    f.write(f"Trailing Commas    : {self.trailing_commas}\r\n")
                else:
                    f.write(f"Custom Symbol      : {self.custom_sym.get()}\r\n")
                f.write(f"Branch Mode        : {branch_label}\r\n")
                f.write(f"Registered Suffix1 : {suf1}\r\n")
                f.write(f"Registered Suffix2 : {suf2}\r\n")
                f.write(f"Regex Pattern      : {regex_pat}\r\n")
                f.write(f"Scope              : RE以降のみ（最初のRE以降）\r\n")
                f.write("===================================\r\n\r\n")
                # === Validation: Comma Count Consistency ===
                f.write("=== Validation (Comma Count Consistency) ===\r\n")
                f.write(f"Mismatches        : {comma_mismatch_total}\r\n")
                if comma_mismatch_total:
                    # 上位20件だけ詳細表示
                    for ln, before, after in comma_mismatch_rows[:20]:
                        f.write(f" - Line {ln}: commas before={before}, after={after}\r\n")
                f.write("\r\n")
                f.write("UKE CSV Editor Conversion Log\r\n")
                f.write(f"Timestamp           : {ts}\r\n")
                f.write(f"Source file         : {self.file_path.name}\r\n")
                f.write(f"RE件数              : {re_token_total}\r\n")
                f.write(f"変換対象件数        : {target_total}\r\n")
                f.write(f"変換した件数        : {converted_total}\r\n")
                f.write(f"フォールバック件数  : {fallback_total}\r\n")
                f.write(f"変換できなかった件数: {unchanged_total}\r\n")
                # 追加: 未変換理由と手動救済の内訳
                f.write("\r\n=== Unconverted Breakdown ===\r\n")
                f.write(f"UNCHANGED_SAME_LEN  : {len(unchanged_same_len_rows)}\r\n")
                f.write(f"NO_RE               : {len(no_re_rows)}\r\n")
                f.write(f"RE_BUT_NO_MATCH     : {len(re_nomatch_rows)}\r\n")
                if manual_converted_total or manual_skipped_total:
                    f.write("\r\n=== Manual Fix Summary ===\r\n")
                    f.write(f"Manual Converted    : {manual_converted_total}\r\n")
                    f.write(f"Manual Skipped      : {manual_skipped_total}\r\n")                

        except Exception as e:
            messagebox.showwarning("警告", f"テキストログの保存に失敗しました: {e}")

        # ---- 完了メッセージ ----
        msg = f"変換後ファイルを保存しました:\n{out_path}"
        if map_path:
            msg += f"\n変更ログ(CSV): {map_path}"
        msg += (
            f"\n\n患者コード 変換対象: {target_total} 件"
            f"\n患者コード 変換件数: {converted_total} 件"
            f"\nフォールバック件数: {fallback_total} 件"
            f"\n変換できなかった件数: {unchanged_total} 件"
            f"\nRE件数: {re_token_total} 件"
            f"\nログ: {log_path}"
        )
        extra = []
        if unchanged_total or no_re_rows or re_nomatch_rows or manual_converted_total:
            extra.append("\n―― 未変換/手動変換 内訳 ――")
            extra.append(f"  ・UNCHANGED_SAME_LEN（同桁無変化）: {len(unchanged_same_len_rows)} 件")
            extra.append(f"  ・NO_RE（RE未検出）               : {len(no_re_rows)} 行")
            extra.append(f"  ・RE_BUT_NO_MATCH（REあり無マッチ）: {len(re_nomatch_rows)} 行")
            if manual_converted_total:
                extra.append(f"  ・手動桁数変換で救済             : {manual_converted_total} 行（スキップ {manual_skipped_total}）")
        if extra:
            msg += "\n" + "\n".join(extra)        
        
        if comma_mismatch_total:
            msg += f"\n⚠ カンマ数不一致: {comma_mismatch_total} 件（ログ参照）"
        else:
            msg += "\nカンマ数検証: OK"
        messagebox.showinfo("完了", msg)
        self.status.set(f"保存完了: {out_path.name}（自動 {converted_total}/{target_total} 件, 手動 {manual_converted_total} 件, Fallback {fallback_total} 件）")

    def _manual_convert_dialog(self, *,
                            candidates_no_re: list[tuple[int, str]],
                            candidates_re_nomatch: list[tuple[int, str]] | None = None,
                            candidates_same_len: list[tuple[int, str]] | None = None,
                            out_lines: list[str],
                            changes_rows: list[list[str]]) -> tuple[int, int]:
        """
        返戻等でRE起因の未変換行を「レコード表示」し、列見出しクリック/セルダブルクリックで
        変換対象列を選んで一括変換する。
        - candidates_* は (line_no(1始まり), original_line) のリスト
        - out_lines に対して行単位で置換を反映
        - changes_rows に method='manual' で追記
        戻り値: (manual_converted, manual_skipped)
        """
        if candidates_re_nomatch is None:
            candidates_re_nomatch = []
        if candidates_same_len is None:
            candidates_same_len = []
            
        # 変換桁数は起動時スナップショット（他設定は引き継がない）
        conv_len = int(self.patient_code_conv_len)
        # 行別の対象列（0始まり for C1..）：{ line_no -> col_idx }
        overrides: dict[int, int] = {}
        # 複数回実行に備えて累計カウンタ
        total_converted = 0
        total_skipped = 0
            
        pool = [("NO_RE", ln, line) for ln, line in candidates_no_re] + \
            [("RE_BUT_NO_MATCH", ln, line) for ln, line in candidates_re_nomatch] + \
            [("UNCHANGED_SAME_LEN", ln, line) for ln, line in candidates_same_len]
        if not pool:
            return (0, 0)

        # ---- UI ----
        dlg = tk.Toplevel(self)
        dlg.title("手動桁数変換（RE未検出/マッチなし行）")
        dlg.transient(self); dlg.grab_set(); dlg.resizable(True, True)

        # --- 幅キャップ：メインと同程度に抑える ----------------------------
        try:
            main_w = int(self.winfo_width())
        except Exception:
            main_w = 900
        cap_w = max(860, min(main_w if main_w > 1 else 900, 1000))  # だいたいメイン幅（900）±少し
        dlg.minsize(720, 420)
        dlg.maxsize(cap_w, self.winfo_screenheight() - 80)
        # 初期サイズもここで縛る（高さは適宜）
        dlg.geometry(f"{cap_w}x{min(600, self.winfo_screenheight()-160)}+{self.winfo_rootx()+40}+{self.winfo_rooty()+40}")

        def _cap_dialog_width():
            """再描画等で広がりそうになっても、幅の上限に収める"""
            dlg.update_idletasks()
            cur_h = dlg.winfo_height() or 600
            if dlg.winfo_width() > cap_w:
                dlg.geometry(f"{cap_w}x{cur_h}")

        info = (
            f"対象行: NO_RE={len(candidates_no_re)} / RE_BUT_NO_MATCH={len(candidates_re_nomatch)} / UNCHANGED_SAME_LEN={len(candidates_same_len)}\n"
                "列見出しクリック＝全体の対象列、セルのダブルクリック＝行別の対象列を指定できます。"
            )
        ttk.Label(dlg, text=info, justify="left").pack(anchor="w", padx=12, pady=(12, 4))

        # オプション
        opts = ttk.Frame(dlg); opts.pack(fill="x", padx=12)
        use_no_re   = tk.BooleanVar(value=False)
        use_nomatch = tk.BooleanVar(value=bool(candidates_re_nomatch))
        use_same    = tk.BooleanVar(value=False)
        only_selected = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="NO_RE を含める", variable=use_no_re).grid(row=0, column=0, sticky="w", pady=2)
        ttk.Checkbutton(opts, text="RE_BUT_NO_MATCH を含める", variable=use_nomatch).grid(row=0, column=1, sticky="w", pady=2)
        ttk.Checkbutton(opts, text="UNCHANGED_SAME_LEN を含める", variable=use_same).grid(row=0, column=2, sticky="w", pady=2)
        ttk.Checkbutton(opts, text="選択行のみ変換", variable=only_selected).grid(row=0, column=3, sticky="w", pady=2)
        ttk.Label(opts, text=f"この手動変換は 変換桁数={conv_len} で実行します").grid(row=1, column=0, columnspan=4, sticky="w", pady=(4,2))
        status_var = tk.StringVar(value="未実行")
        ttk.Label(opts, textvariable=status_var).grid(row=2, column=0, columnspan=4, sticky="w", pady=(0,2))        

        # 表本体
        table_frame = ttk.Frame(dlg)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(6, 0))
        # 子ウィジェット（Treeview）の推奨サイズで親フレームが膨張しないように
        table_frame.pack_propagate(False)
        table_frame.configure(width=cap_w - 24)  # padding を差し引いて概ねダイアログ幅に合わせる        

        tree = ttk.Treeview(table_frame, show="headings")
        ysb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        xsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # プレビュー
        prev = tk.Text(dlg, height=10, wrap="none")
        prev.pack(fill="both", expand=False, padx=12, pady=(8, 0))
        prev.config(state="disabled")

        # 内部状態
        selected_col_idx: Optional[int] = None  # 0始まり（C1=0）
        visible_rows: list[tuple[str, int, str, list[str]]] = []  # (tag, ln, orig_line, fields)
        max_cols = 0
        selected_header_marker = "★"  # 視覚化用

        def _split_fields(line: str) -> list[str]:
            # 既存実装に合わせて単純 split。UKEは値内カンマを持たない想定。
            return line.split(",")

        def _rebuild_table():
            nonlocal visible_rows, max_cols, selected_col_idx
            # フィルタ
            filtered = []
            for tag, ln, orig in pool:
                if tag == "NO_RE" and not use_no_re.get():
                    continue
                if tag == "RE_BUT_NO_MATCH" and not use_nomatch.get():
                    continue
                if tag == "UNCHANGED_SAME_LEN" and not use_same.get():
                    continue
                fields = _split_fields(orig)
                filtered.append((tag, ln, orig, fields))

            visible_rows = filtered
            max_cols = max((len(r[3]) for r in visible_rows), default=0)

            # columns 定義（行番号/種別 + C1..Ck）
            cols = ["__line__", "__type__", "__target__"] + [f"C{i}" for i in range(1, max_cols + 1)]
            tree["columns"] = cols
            for c in cols:
                tree.heading(c, text="")  # リセット

            # 見出し
            tree.heading("__line__", text="行")
            tree.heading("__type__", text="種別")
            tree.heading("__target__", text="対象列")
            tree.column("__target__", width=80, stretch=False)            
            for i in range(1, max_cols + 1):
                col_id = f"C{i}"
                # 見出しクリックで選択列に設定
                tree.heading(col_id, text=f"{i}", command=lambda c=i: _select_column(c - 1))
                tree.column(col_id, width=90, stretch=True)
            tree.column("__line__", width=60, stretch=False)
            tree.column("__type__", width=130, stretch=False)

            # 既存データクリア
            for iid in tree.get_children():
                tree.delete(iid)

            # 行投入
            def _target_text(ln: int) -> str:
                return f"C{overrides[ln]+1}" if ln in overrides else "-"
            for tag, ln, orig, fields in visible_rows:
                row_vals = [ln, tag, _target_text(ln)] + [fields[i] if i < len(fields) else "" for i in range(max_cols)]

                tree.insert("", "end", iid=str(ln), values=row_vals)

            # 見出しの選択状態を再描画
            _refresh_heading_selected()

            # プレビュー更新
            _preview_topN()
            _cap_dialog_width()

        def _refresh_heading_selected():
            # 見出しの ★ 印を付け替え
            for i in range(1, max_cols + 1):
                label = f"{i}"
                if selected_col_idx is not None and i - 1 == selected_col_idx:
                    label = f"{selected_header_marker}{label}"
                tree.heading(f"C{i}", text=label)

        def _set_preview_text(lines: list[str]):
            prev.config(state="normal"); prev.delete("1.0", "end")
            prev.insert("1.0", "\n".join(lines) if lines else "（プレビュー対象なし）")
            prev.config(state="disabled")

        def _preview_topN():
            # 選択列に対して上位20件の before->after を出す
            if selected_col_idx is None:
                _set_preview_text(["変換対象列が未選択です。列見出しをクリック、またはセルをダブルクリックしてください。"])
                return
            lines = []
            target = _get_apply_rows()
            for tag, ln, orig, fields in target[:20]:
                tcol = _target_col_for_row(ln)
                if tcol is None or tcol < 0 or tcol >= len(fields):
                    lines.append(f"[{tag}] 行{ln}: 対象列未指定のためスキップ")
                    continue
                old = fields[tcol]
                digits = "".join(ch for ch in old if ch.isdigit())
                new = digits[-conv_len:].zfill(conv_len) if digits else ""
                lines.append(f"[{tag}] 行{ln} (C{tcol+1}): [{old}] -> [{new}]")
            _set_preview_text(lines)

        def _get_apply_rows():
            # 変換対象の行（「選択行のみ変換」の場合はTreeview選択行）
            if not only_selected.get():
                return visible_rows
            sel_ids = set(tree.selection())
            return [row for row in visible_rows if str(row[1]) in sel_ids]

        def _select_column(col_idx_zero_based: int):
            nonlocal selected_col_idx
            selected_col_idx = col_idx_zero_based
            _refresh_heading_selected()
            _preview_topN()

        def _on_cell_double_click(event):
            # ダブルクリックしたセルの列から選択列を決定
            region = tree.identify("region", event.x, event.y)
            if region != "cell" and region != "tree":
                return
            col = tree.identify_column(event.x)  # e.g. '#1', '#2', ...
            row_iid = tree.identify_row(event.y)  # 行の iid（= line_no 文字列）
            try:
                col_index = int(col.lstrip("#")) - 1  # 0始まり
            except Exception:
                return
            if not row_iid:
                return
            # columns: __line__(0), __type__(1), __target__(2), C1.. が 3 以降
            if col_index >= 3:
                # 行別の対象列を設定（0始まり for C1..）
                ln = int(row_iid)
                overrides[ln] = col_index - 3
                tree.set(row_iid, "__target__", f"C{overrides[ln]+1}")
                _preview_topN()
            elif col_index >= 0:
                # ヘッダ相当のダブルクリックではなく行の __line__/__type__/__target__ を触った場合は何もしない
                return

        tree.bind("<Double-1>", _on_cell_double_click)

        def _apply():
            # 実変換（out_lines & changes_rows を更新）
            converted = skipped = 0
            for tag, ln, orig, fields in _get_apply_rows():
                tcol = _target_col_for_row(ln)
                if tcol is None or tcol < 0 or tcol >= len(fields):
                    skipped += 1
                    continue
                old = fields[tcol]
                digits = "".join(ch for ch in old if ch.isdigit())
                if not digits:
                    skipped += 1
                    continue
                new_code = digits[-conv_len:].zfill(conv_len)
                if new_code != old:
                    fields[tcol] = new_code
                    new_line = ",".join(fields)
                    out_lines[ln - 1] = new_line  # 1始まり→0始まり
                    changes_rows.append([str(ln), old, new_code, orig, new_line, f"manual(C{tcol+1})"])
                    converted += 1
            # 累計更新＆表示。ダイアログは閉じずに続けて操作できる
            nonlocal total_converted, total_skipped
            total_converted += converted
            total_skipped   += skipped
            status_var.set(f"直近: 変換 {converted} / スキップ {skipped}   累計: 変換 {total_converted} / スキップ {total_skipped}")
            _rebuild_table()   # __target__ 等の表示更新
            _cap_dialog_width()

        def _target_col_for_row(ln: int) -> Optional[int]:
            # 行別指定があれば優先、なければ全体選択列、どちらも無ければ None
            if ln in overrides:
                return overrides[ln]
            return selected_col_idx

        # 再描画とプレビュー
        def _on_filter_change(*_):
            _rebuild_table()
            _cap_dialog_width()

        use_no_re.trace_add("write", _on_filter_change)
        use_nomatch.trace_add("write", _on_filter_change)
        use_same.trace_add("write", _on_filter_change)

        # ボタン
        btns = ttk.Frame(dlg); btns.pack(fill="x", padx=12, pady=8)
        def _reset_overrides():
            overrides.clear()
            status_var.set("行別指定をリセットしました")
            _rebuild_table()

        def _finish():
            dlg.result = (total_converted, total_skipped)
            dlg.grab_release(); dlg.destroy()

        ttk.Button(btns, text="プレビュー更新", command=_preview_topN).pack(side="left")
        ttk.Button(btns, text="行別指定リセット", command=_reset_overrides).pack(side="left", padx=(8,0))
        ttk.Button(btns, text="実行", command=_apply).pack(side="right")
        ttk.Button(btns, text="閉じる", command=_finish).pack(side="right", padx=(8,0))

        # 初期構築
        _rebuild_table()
        dlg.wait_window()
        return getattr(dlg, "result", (0, 0))

    # ---------- ファイルリネーム ----------
    def rename_files(self):
        # ……元の rename_files 実装をそのまま残す……
        fps = filedialog.askopenfilenames(
            title="リネームする UKE ファイルを選択 (複数可)",
            filetypes=[("すべてのファイル", "*")],
        )
        if not fps:
            return
        renamed: List[str] = []
        skipped: List[str] = []
        for fp in self.tk.splitlist(fps):
            path = Path(fp)
            m = re.match(r"^(.*?)(\.UKE)(.*)$", path.name, flags=re.IGNORECASE)
            if not m:
                skipped.append(path.name)
                continue
            base_name, ext, suffix_raw = m.group(1), m.group(2), m.group(3)
            suffix_clean = suffix_raw.replace("\u3000", " ").strip()
            if not suffix_clean:
                skipped.append(path.name)
                continue
            new_name = f"{suffix_clean}_ {base_name}{ext.upper()}"
            try:
                path.rename(path.with_name(new_name))
                renamed.append(f"{path.name} → {new_name}")
            except Exception as e:
                skipped.append(f"{path.name} (失敗: {e})")
        summary = []
        if renamed:
            summary.append("★リネーム完了:\n" + "\n".join(renamed))
        if skipped:
            summary.append("★変更不要/不可:\n" + "\n".join(skipped))
        msg = "\n\n".join(summary) if summary else "対象ファイルがありませんでした。"
        messagebox.showinfo("リネーム結果", msg)

    # ---------- 設定ダイアログ ----------
    def _apply_settings(self, len_v, conv_v, comma_v, noise_v, dlg):
        self.patient_code_len      = len_v.get()
        self.patient_code_conv_len = conv_v.get()

        # ★ 後方カンマを 1..MAX_TRAILING_COMMAS にクランプ
        try:
            tc = int(comma_v.get())
        except Exception:
            tc = self.trailing_commas
        self.trailing_commas = max(1, min(MAX_TRAILING_COMMAS, tc))
        
        # ノイズ記号を反映
        try:
            self.noise_marks = str(noise_v.get())
        except Exception:
            self.noise_marks = getattr(self, "noise_marks", "*＊※★")

        self.status.set(
            f"設定変更: ハイライト桁数={self.patient_code_len} / "
            f"変換桁数={self.patient_code_conv_len} / "
            f"後方カンマ数={self.trailing_commas} / 枝番モード={self.br_mode.get()}"
        )
        self._apply_highlight()
        dlg.destroy()
    
    def open_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title("設定")
        dialog.geometry("+{}+{}".format(
            self.winfo_rootx() + 100,   # メイン窓から少し右
            self.winfo_rooty() + 80))   # 少し下に配置

        # 伸縮レイアウト設定（入力欄が横に広がるように）
        dialog.grid_columnconfigure(1, weight=1)
        dialog.grid_columnconfigure(2, weight=1)
        dialog.grid_columnconfigure(3, weight=1)

        # ── 患者コード設定 ──────────────────
        tk.Label(dialog, text="患者コード桁数（ハイライト用）").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        tk.Label(dialog, text="患者コード変換桁数").grid(        row=1, column=0, sticky="w", padx=4, pady=4)
        tk.Label(dialog, text="後方カンマ数").grid(            row=2, column=0, sticky="w", padx=4, pady=4)

        len_var  = tk.IntVar(value=self.patient_code_len)
        conv_var = tk.IntVar(value=self.patient_code_conv_len)
        comma_var= tk.IntVar(value=self.trailing_commas)

        tk.Spinbox(dialog, from_=1, to=20, textvariable=len_var,  width=5).grid(row=0, column=1, padx=4)
        tk.Spinbox(dialog, from_=1, to=20, textvariable=conv_var, width=5).grid(row=1, column=1, padx=4)
        tk.Spinbox(dialog, from_=1, to=MAX_TRAILING_COMMAS, textvariable=comma_var, width=5).grid(row=2, column=1, padx=4)

        # ── ★ 枝番関連 UI をここに内包 ★ ─────────
        sep = tk.Frame(dialog, height=2, bd=1, relief="sunken")
        sep.grid(row=3, column=0, columnspan=3, pady=6, sticky="ew")

        # 枝番登録 / 確認ボタン
        br_btn_frame = tk.Frame(dialog); br_btn_frame.grid(row=4, column=0, columnspan=3, pady=2)
        tk.Button(br_btn_frame, text="枝番登録", width=10,
                command=self.register_branches).pack(side="left", padx=4)
        tk.Button(br_btn_frame, text="枝番確認", width=10,
                command=self.show_branches).pack(side="left", padx=4)

        # 枝番処理ラジオ (オフ / 1桁 / 2桁)
        tk.Label(dialog, text="枝番処理").grid(row=5, column=0, sticky="w", padx=(4,0))
        tk.Radiobutton(dialog, text="オフ",  value=0, variable=self.br_mode,
                    command=self._refresh_branch_mode).grid(row=5, column=1, sticky="w")
        tk.Radiobutton(dialog, text="1 桁", value=1, variable=self.br_mode,
                    command=self._refresh_branch_mode).grid(row=5, column=2, sticky="w")
        tk.Radiobutton(dialog, text="2 桁", value=2, variable=self.br_mode,
                    command=self._refresh_branch_mode).grid(row=5, column=3, sticky="w")
        
        # ── 患者コード判定ロジック ──────────────────────────
        row_base = 6  # すでに3行使っているので 3 から
        tk.Label(dialog, text="判定ロジック").grid(row=row_base, column=0,
                                                sticky="w", padx=4, pady=(12,4))

        # ラジオボタン
        entry_sym = tk.Entry(dialog, textvariable=self.custom_sym, width=4)
        entry_sym.grid(row=row_base, column=3, sticky="w", padx=(4,0))

        tk.Radiobutton(dialog, text="後方カンマ数", value=0, variable=self.detect_mode,
                    command=lambda e=entry_sym: e.config(state="disabled")
                    ).grid(row=row_base, column=1, sticky="w")
        tk.Radiobutton(dialog, text="任意の記号", value=1, variable=self.detect_mode,
                    command=lambda e=entry_sym: e.config(state="normal")
                    ).grid(row=row_base, column=2, sticky="w")

        # ── ノイズ（捨てるマーク）設定 ─────────────────────
        noise_row = row_base + 1
        tk.Label(dialog, text="捨てるマーク（ノイズ）").grid(row=noise_row, column=0, sticky="w", padx=4, pady=(8,4))
        noise_var = tk.StringVar(value=getattr(self, "noise_marks", "*＊※★"))
        tk.Entry(dialog, textvariable=noise_var, width=20).grid(row=noise_row, column=1, columnspan=3, sticky="we", padx=4)

        # スペーサー行（OKボタンとノイズ入力の重なり防止）
        spacer_row = noise_row + 1
        tk.Frame(dialog, height=4).grid(row=spacer_row, column=0, columnspan=4)

        # ── ボタン行（右寄せ） ───────────────────────────
        btn_row = spacer_row + 1
        btn_frame = tk.Frame(dialog)
        btn_frame.grid(row=btn_row, column=0, columnspan=4, pady=8, sticky="w")
        tk.Button(btn_frame, text="OK", width=8,
                command=lambda: self._apply_settings(len_var, conv_var, comma_var, noise_var, dialog)
                ).pack(side="right")

        dialog.grab_set()

    # ────────────────────────── ウィンドウサイズ保存/復元 ──────────────────────────
    def _restore_geometry(self):
        """前回終了時のウィンドウサイズ・位置を復元"""
        try:
            p = Path.home() / ".uke_editor_ui.json"
            if p.exists():
                g = json.loads(p.read_text(encoding="utf-8"))
                geo = g.get("geometry")
                if geo:
                    self.geometry(geo)
        except Exception:
            # 読み込み失敗時は無視（初回や壊れたファイル想定）
            pass

    def _save_geometry_and_quit(self):
        """現在のウィンドウサイズ・位置を保存して終了"""
        try:
            p = Path.home() / ".uke_editor_ui.json"
            p.write_text(json.dumps({"geometry": self.geometry()}), encoding="utf-8")
        except Exception:
            # 保存失敗しても終了は継続
            pass
        self.destroy()

    def _insert_help_text(self):
        """起動時にテキストボックスへ簡易ヘルプを表示（v2.1系仕様）"""
        HELP_TEXT = (
            f"UKE CSV Editor {APP_VERSION} - 使い方ガイド\n"
            "============================================\n"
            "★ TIPS（先に読む）\n"
            "  1) 長い桁から順に変換： 5桁 → 4桁 → 3桁 → 2桁（誤ヒット最小化）\n"
            "  2) yyyymmdd 回避： 後方カンマ数を十分大きく設定（例: 8, 10, 15 など）\n"
            "  3) ハイフン枝番： ‘-02’ 入力→保存は ‘02’ に正規化。登録済みなら左側を採用\n"
            "  4) 変換対象は「行内の最初の RE 以降」×「ハイライト一致のみ」（画面の黄色＝置換対象）\n"
            "  5) 枝番は N+枝番桁のときだけ扱う（N桁末尾一致は枝番とみなさない）\n"
            "  6) 任意記号モード：記号列は保持／後方カンマモード：カンマ個数で正規化\n"
            "  7) 捨てるマーク（ノイズ）：設定で ‘*＊※★’ 等を指定。コード直後のノイズは自動除去\n"
            "  8) 保存名：『名前を付けて保存』で出力名を指定（変更ログ/テキストログも同じファイル名stem）\n"
            "  9) カンマ数検証：変換前後で行ごとのカンマ個数を自動チェック。結果はダイアログと *.log.txt に出力\n"
            " 10) 手動桁数変換：自動処理後に未処理がある場合のみ起動（詳細は下記）\n"
            "--------------------------------------------\n"
            "\n"
            "■ ハイライトの基準（N=ハイライト用桁数）\n"
            "  - N は『枝番を除いた基準桁』です。\n"
            "  - 後方カンマモードでは検出時に {N, N+枝番桁} を許容\n"
            "    （例：N=8/枝番2桁 → {8,10}。ハイフン形 8桁-2桁 もヒット）。\n"
            "  - 枝番の赤塗り／枝番除去／フォールバックは、長さが N+枝番桁 の時だけ適用。\n"
            "\n"
            "■ 基本の流れ\n"
            "  1) 読み込みファイルをリネーム：選んだ .UKE のファイル名を整えます。\n"
            "  2) ファイル読み込み          ：UKE/CSV を読み込みます。\n"
            "  3) 患者コード・全行ハイライト：RE 以降の患者コードを検出して色付け。\n"
            "  4) コード変換して保存        ：変換して UKE を出力（変更ログ/テキストログも保存）。\n"
            "\n"
            "■ 枝番（サフィックス）管理\n"
            "  - 上部パネルで『登録済み枝番（1桁/2桁）』を常時表示。\n"
            "  - 枝番登録   ：Ctrl+B または『設定→枝番登録』。入力は 0〜99 または -0〜-99。\n"
            "                 ※ 保存は数値のみ（-02 → 02 に正規化）。\n"
            "  - 枝番処理   ：オフ / 1桁除去 / 2桁除去（設定で切替）。\n"
            "\n"
            "■ 保存時の自動変換ロジック\n"
            "  - 第1段（通常）：登録枝番を考慮して枝番を除去 → 指定桁数（変換桁数）に整形。\n"
            "  - 第2段（フォールバック）：第1段で不変かつ『数字のみ・長さ=N+枝番桁』の場合、\n"
            "     末尾の枝番桁を落としてから桁揃え（ハイフン付きは対象外）。\n"
            "  - カンマ数検証：置換後に行ごとのカンマ個数一致を検証し、異常はログへ警告。\n"
            "\n"
            "■ 手動桁数変換ダイアログ（未処理がある場合のみ自動起動）\n"
            "  - 起動条件：\n"
            "     (a) 自動処理の『変換対象件数 > 変換件数』、または\n"
            "     (b) RE はあるが正規表現にヒットしなかった行（RE_BUT_NO_MATCH）が存在。\n"
            "     ※ NO_RE（行内に RE 自体が無い）『だけ』の場合は自動起動しません。\n"
            "  - 初期状態：RE_BUT_NO_MATCH=ON／NO_RE=OFF／UNCHANGED_SAME_LEN=OFF。\n"
            "  - 操作：\n"
            "     ・見出しクリック…全体の対象列を設定（C1, C2 …）\n"
            "     ・セルをダブルクリック…その行だけの対象列を上書き指定（行別指定）\n"
            "     ・『選択行のみ変換』…Treeで選択した行だけを対象に実行\n"
            "     ・『行別指定リセット』…行別の列指定を全クリア\n"
            "     ・ダイアログは閉じずに何度でも『実行』可能（直近/累計件数を表示）\n"
            "  - 仕様：手動変換は『数字抽出→右端 変換桁数 → 左0埋め』のみを行い、\n"
            "          枝番モード・検出モード・後方カンマ数・ノイズ設定の影響は受けません。\n"
            "  - ログ：変更ログCSVの method は『manual(Cx)』形式で列を記録。\n"
            "\n"
            "■ 参考：ステータスバー\n"
            "  - RE統計（REあり/なし/個数）と、枝番統計（登録数/ヒット/モード）を表示します。\n"
            "\n"
            "■ 例：N=8, 枝番2桁, 変換桁数=6, 後方カンマ数=8\n"
            "  - ',00071843-02,,'         → 登録『02』あり → 左側 00071843 → 071843（6桁）\n"
            "  - ',0007184302,,'          → 登録『02』あり → 00071843 → 071843（6桁）\n"
            "  - ',00071843-02****,,,,,'  → ノイズ ‘****’ は除去、カンマ列は保持\n"
            "  - ',20250131,,'            → 後方カンマ数が合わなければヒットせず変換対象外\n"
        )
        self.row_text.config(state="normal")
        self.row_text.delete("1.0", "end")
        self.row_text.insert("1.0", HELP_TEXT)
        self.row_text.config(state="disabled")


if __name__ == "__main__":
    app = UKEEditorGUI()
    app.mainloop()