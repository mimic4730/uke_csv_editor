#!/usr/bin/env python3
# src/gui.py
import datetime, re, tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
from typing import List, Optional

import branch_manager as bm
import highlighter
from editor import load_csv

DISPLAY_COL = 0   # フィルタ用列（先頭列）

class UKEEditorGUI(tk.Tk):
    # ────────────────────────── 初期化 ──────────────────────────
    def __init__(self) -> None:
        super().__init__()
        self.title("UKE CSV Editor")
        self.geometry("900x540")
        self.resizable(False, False)

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
        self.highlight_pat = None 

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
        tk.Label(list_frame, text="内容").pack(side=tk.LEFT, anchor=tk.NW)

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
        """表示行数と現在のハイライト件数をステータスバーへ反映"""
        hit_cnt = len(self.hl.matches) if self.hl.regex else 0
        self.status.set(f"表示 {self.visible_count} 行　/　ハイライト {hit_cnt} 件")

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
        self.status.set(f"表示 {self.visible_count} 行　/　ハイライト {len(self.hl.matches)} 件")

    def highlight_first_match(self):
        if not self.rows: return
        self._setup_highlighter()
        self.hl.scan(self.rows, self.display_indices, self.line_starts)
        if not self.hl.matches:
            messagebox.showinfo("検索結果", "該当する患者コードは見つかりませんでした。"); return
        self.hl.draw_single(0)
        self.status.set(
            f"表示 {self.visible_count} 行　/　ハイライト {len(self.hl.matches)} 件"
            f"　(1 / {len(self.hl.matches)})"
        )

    def highlight_next_match(self):
        if not self.hl.matches:
            self.highlight_first_match(); return
        self.hl.draw_single(self.hl.focus_idx + 1)
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
        return self._normalize_code(self._strip_branch(raw))
    
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

        pat = self.hl.regex               # ,(\d{N}),,, の形
        tc  = "," * self.trailing_commas       # 後方カンマ

        # ---- 行全体を文字列に戻して一括置換 ----
        out_lines: list[str] = []
        for row in self.rows:
            line = ",".join(row)               # 1 行をそのままカンマ連結
            # 変更後
            fixed = pat.sub(
                lambda m: f",{self._format_code(m.group(1))}{tc}",
                line
            )
            out_lines.append(fixed)

        # ---- ファイル名：8.3 形式 + .UKE ----
        base = self.file_path
        assert base is not None
        stem = re.sub(r'[^A-Za-z0-9]', '', base.stem) or "F"
        stem = (stem[:1] + datetime.datetime.now().strftime("%y%m%d%H"))[:8]
        out_path = base.with_name(stem.upper() + ".UKE")

        # ---- Shift‑JIS・CRLF・各行を二重引用 ----
        with out_path.open("w", encoding="cp932", newline="") as f:
            for line in out_lines:
                f.write(f"{line}\r\n")   

        messagebox.showinfo("完了", f"変換後ファイルを保存しました:\n{out_path}")
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
        dialog.minsize(600, 1)          # 最小幅 480px に固定
        dialog.resizable(False, False)

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



if __name__ == "__main__":
    app = UKEEditorGUI()
    app.mainloop()