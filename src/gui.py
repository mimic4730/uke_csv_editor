#!/usr/bin/env python3
# src/gui.py
import datetime, re, tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
from typing import List, Optional
import json
import csv

import branch_manager as bm
import highlighter
from editor import load_csv, build_output_path_from_input, save_csv_like_excel

DISPLAY_COL = 0   # フィルタ用列（先頭列）

class UKEEditorGUI(tk.Tk):
    # ────────────────────────── 初期化 ──────────────────────────
    def __init__(self) -> None:
        super().__init__()
        self.title("UKE CSV Editor")
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

        # Highlighter インスタンス
        self.detect_mode = tk.IntVar(value=0)   # 0=後方カンマ, 1=任意記号
        self.custom_sym  = tk.StringVar(value=",")
        self.hl = highlighter.Highlighter(self.row_text)
        self.hl.detect_mode_current = self.detect_mode.get()
        self.highlight_pat = None
        
        # 前回サイズを復元・終了時に保存
        self._restore_geometry()
        self.protocol("WM_DELETE_WINDOW", self._save_geometry_and_quit)        

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

    def _update_status_counts(self):
        """表示行数と現在のハイライト件数 + RE統計をステータスへ反映"""
        hit_cnt = len(self.hl.matches) if self.hl.regex else 0
        re_lines = getattr(self.hl, "re_line_count", 0)
        re_none  = getattr(self.hl, "no_re_line_count", self.visible_count - re_lines)
        re_tokens = getattr(self.hl, "re_token_count", 0)
        self.status.set(
            f"表示 {self.visible_count} 行　/　ハイライト {hit_cnt} 件　"
            f"/　REあり {re_lines} 行　/　REなし {re_none} 行　/　RE {re_tokens} 個"
        )

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
        """regex と枝番モードを Highlighter へ反映"""
        pattern = self.hl._build_regex(
            n_digits=self.patient_code_len,
            trailing_commas=self.trailing_commas,
            detect_mode=self.detect_mode.get(),
            custom_sym=self.custom_sym.get()
        )
        self.hl.set_regex(pattern)      # ← これだけで OK
        self.highlight_pat = pattern    # 変換用にも保持
        self.hl.detect_mode_current = self.detect_mode.get()

        # ❷ 枝番モード
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
        self.row_text.config(state="disabled")
        self.status.set(f"表示 {self.visible_count} 行　/　ハイライト 0 件")

    # --- 枝番モード変更時に即時再描画 ---
    def _refresh_branch_mode(self):
        self._apply_highlight()

    # ────────────────────────── 枝番登録 / 確認 ──────────────────────────
    def register_branches(self):
        suffix = simpledialog.askstring("枝番登録", "枝番 (1〜2 桁) を入力", parent=self)
        if not suffix: return
        if not re.fullmatch(r"\d{1,2}", suffix):
            messagebox.showwarning("入力エラー", "枝番は 0〜99 の数字で入力してください。"); return
        try:
            bm.register_suffix(suffix)
            messagebox.showinfo("登録完了", f"枝番 {suffix} を登録しました")
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
    # ────────── 枝番を除去してから桁揃え ──────────
    def _strip_branch(self, code: str) -> str:
        """
        self.br_mode:
            0 … 何もしない
            1 … 登録済み 1 桁枝番が付いていれば取り除く
            2 … 登録済み 2 桁枝番が付いていれば取り除く
        """
        mode = self.br_mode.get()
        if mode == 1 and len(code) > 1:
            if code[-1:] in bm.list_suffixes(1):
                return code[:-1]
        elif mode == 2 and len(code) > 2:
            if code[-2:] in bm.list_suffixes(2):
                return code[:-2]
        return code  # オフ or 不一致 → そのまま
    
    def _format_code(self, raw: str) -> str:
        """枝番を除去してから桁固定"""
        if self.detect_mode.get() == 1 and "-" in raw:
            raw = raw.split("-", 1)[0]          # 例: "12603-0002" → "12603"

        # ★枝番処理（オフならそのまま）
        raw = self._strip_branch(raw)

        # ★桁数 Fix
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
        changes_rows: list[list[str]] = []   # [line_no, old_code, new_code, original_line, converted_line]
        error_rows: list[list[str]] = []     # [line_no, codes_joined, reason, original_line]

        for idx, row in enumerate(self.rows, 1):
            line = ",".join(row)

            # --- RE が無い行はそのまま ---
            m_re = RE_FIELD.search(line)
            if not m_re:
                out_lines.append(line)
                continue

            head = line[:m_re.end()]        # RE まで（含む）
            tail = line[m_re.end():]        # RE 以降のみ置換対象

            # --- RE はあるがコード未検出 → エラー(no_code_detected) ---
            matches = list(pat.finditer(tail))
            if not matches:
                error_rows.append([str(idx), "", "no_code_detected", line])
                out_lines.append(line)  # そのまま出力
                continue

            # --- 置換実行（1文字でも変わったかを later に判定する） ---
            changed_any = False
            matched_codes = []

            def _repl(m: re.Match) -> str:
                nonlocal changed_any
                old = m.group(1)
                new = self._format_code(old)  # 枝番除去→桁揃え（既存ロジック）
                matched_codes.append(old)
                if new != old:
                    changed_any = True
                    changes_rows.append([str(idx), old, new, line, None])
                return f",{new}{tc}"

            tail_fixed = pat.sub(_repl, tail)
            fixed_line = head + tail_fixed
            out_lines.append(fixed_line)

            # changes_rows の converted_line を埋める
            if changed_any:
                for r in changes_rows:
                    if r[0] == str(idx) and r[4] is None:
                        r[4] = fixed_line

            # --- 置換は試みたが、結果が全く変わっていない → エラー(no_change) ---
            if not changed_any and fixed_line == line:
                # 行内に複数コードがあってもまとめて出す（見やすさ優先）
                joined = " ".join(dict.fromkeys(matched_codes))  # 重複除去して順序保持
                error_rows.append([str(idx), joined, "no_change", line])

        # ---- 出力名：修正後_元のファイル名（重複時は (2)…）----
        base = self.file_path; assert base is not None
        out_path = build_output_path_from_input(base)

        with open(out_path, "w", encoding="cp932", newline="") as f:
            for line in out_lines:
                f.write(f"{line}\r\n")

        # ---- 変更ログCSV ----
        map_path = None
        if changes_rows:
            map_path = out_path.with_name(f"{out_path.stem}_changes.csv")
            with open(map_path, "w", encoding="cp932", newline="") as f:
                import csv
                writer = csv.writer(f, lineterminator="\r\n")
                writer.writerow(["line_no", "original_code", "converted_code", "original_line", "converted_line"])
                writer.writerows(changes_rows)

        # ---- エラー行CSV（REあり＆未変換）----
        err_path = None
        if error_rows:
            err_path = out_path.with_name(f"{out_path.stem}_エラー行.csv")
            with open(err_path, "w", encoding="cp932", newline="") as f:
                import csv
                writer = csv.writer(f, lineterminator="\r\n")
                writer.writerow(["line_no", "matched_codes", "error_reason", "original_line"])
                writer.writerows(error_rows)

        # ---- 完了表示 ----
        msg = f"変換後ファイルを保存しました:\n{out_path}"
        if map_path:
            msg += f"\n\n変更ログ(CSV)を保存しました:\n{map_path}"
        if err_path:
            msg += f"\n\nエラー行(CSV)を保存しました:\n{err_path}"
        messagebox.showinfo("完了", msg)
        self.status.set(f"保存完了: {out_path.name}")
        
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
    def _apply_settings(self, len_v, conv_v, comma_v, dlg):
        self.patient_code_len      = len_v.get()
        self.patient_code_conv_len = conv_v.get()
        self.trailing_commas       = comma_v.get()

        self.status.set(f"設定変更: "
                        f"ハイライト桁数={self.patient_code_len} / "
                        f"変換桁数={self.patient_code_conv_len} / "
                        f"後方カンマ数={self.trailing_commas} / "
                        f"枝番モード={self.br_mode.get()}")
        self._apply_highlight()   # 再描画
        dlg.destroy()
    
    def open_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title("設定")
        dialog.geometry("+{}+{}".format(
            self.winfo_rootx() + 100,   # メイン窓から少し右
            self.winfo_rooty() + 80))   # 少し下に配置

        # ── 患者コード設定 ──────────────────
        tk.Label(dialog, text="患者コード桁数（ハイライト用）").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        tk.Label(dialog, text="患者コード変換桁数").grid(        row=1, column=0, sticky="w", padx=4, pady=4)
        tk.Label(dialog, text="後方カンマ数").grid(            row=2, column=0, sticky="w", padx=4, pady=4)

        len_var  = tk.IntVar(value=self.patient_code_len)
        conv_var = tk.IntVar(value=self.patient_code_conv_len)
        comma_var= tk.IntVar(value=self.trailing_commas)

        tk.Spinbox(dialog, from_=1, to=20, textvariable=len_var,  width=5).grid(row=0, column=1, padx=4)
        tk.Spinbox(dialog, from_=1, to=20, textvariable=conv_var, width=5).grid(row=1, column=1, padx=4)
        tk.Spinbox(dialog, from_=1, to=5,  textvariable=comma_var,width=5).grid(row=2, column=1, padx=4)

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

        # ── OK ボタン ────────────────────────
        tk.Button(dialog, text="OK", width=8,
                command=lambda: self._apply_settings(len_var, conv_var, comma_var, dialog)
                ).grid(row=7, column=0, columnspan=4, pady=8)

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
        """起動時にテキストボックスへ簡易ヘルプを表示"""
        HELP_TEXT = (
            "UKE CSV Editor - 使い方ガイド\n"
            "================================\n"
            "1) 読み込みファイルをリネーム: 選んだ .UKE のファイル名を整えます。\n"
            "2) ファイル読み込み: UKE/CSV を読み込みます。\n"
            "3) 全行表示: フィルタを解除して全行を再表示します。\n"
            "4) 設定: ハイライト桁数/変換桁数/後方カンマ/枝番処理/判定ロジックを変更。\n"
            "\n"
            "【ハイライト】\n"
            "- 患者コード・全行ハイライト: RE 以降の患者コードを検出して色付け。\n"
            "    ・コード全体: 黄, 枝番: 赤, ハイフン前まで: 水色\n"
            "    ・ステータスバーに RE 統計（REあり/なし行数・RE個数）を表示\n"
            "- 先頭 1 件ハイライト / 次の行へ: 一致箇所を順送り表示\n"
            "- ハイライト解除: すべてのハイライトを消去\n"
            "\n"
            "【出力】\n"
            "- コード変換して保存: 枝番除去→桁揃え後、RE 以降のみ置換して .UKE を保存\n"
            "\n"
            "【設定のポイント】\n"
            "・患者コード桁数（ハイライト用）: 検出時の桁数。後方カンマ=ちょうどN桁／任意記号=1〜N桁。\n"
            "・患者コード変換桁数: 保存時の桁数。長い→左をカット／短い→左0埋め（例: 123→0000000123）。\n"
            "・後方カンマ数: コード直後に続くカンマの個数。入力フォーマットに合わせて設定。\n"
            "・枝番処理: 「枝番登録」で指定した1桁/2桁を変換時に末尾から除去。ハイライトでは該当部分を赤表示。\n"
            "・判定ロジック: 「後方カンマ数」はフォーマット固定向け／「任意の記号」は 12603-0002 のような記号区切り向け。\n"
            "\n"
            "※『枝番登録』で登録した枝番は保存され、次回起動後も有効です。\n"
            "（保存先: モジュールと同じフォルダの branches.json。配布形態によりホーム配下に切替えることがあります）"
            "\n"
            "ヒント: まず『ファイル読み込み』→『患者コード・全行ハイライト』の順で試すと流れが掴みやすいです。\n"
        )
        self.row_text.config(state="normal")
        self.row_text.delete("1.0", "end")
        self.row_text.insert("1.0", HELP_TEXT)
        self.row_text.config(state="disabled")


if __name__ == "__main__":
    app = UKEEditorGUI()
    app.mainloop()