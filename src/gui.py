#!/usr/bin/env python3
# src/gui.py — フィルター機能付き
import datetime, re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
from typing import List, Optional

from editor import load_csv, save_csv

# どの列を “コード列” として表示・フィルター対象にするか
DISPLAY_COL = 0   # 先頭列

class UKEEditorGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("UKE CSV Editor")
        self.geometry("900x540")
        self.resizable(False, False)

        # データ保持
        self.file_path: Optional[Path] = None
        self.rows: List[List[str]] = []
        self.display_indices: List[int] = []  # フィルター適用後の行インデックス

        # ----------------------------  UI  ----------------------------
        btn_frame1 = tk.Frame(self)
        btn_frame1.pack(pady=4)

        # 1 段目（ファイル操作系）
        btn_frame1 = tk.Frame(self)
        btn_frame1.pack(pady=4, anchor="w")

        tk.Button(btn_frame1, text="読み込みファイルをリネーム",         width=20,
                command=self.rename_files).grid(row=0, column=0, padx=4, sticky="w")

        tk.Button(btn_frame1, text="ファイル読み込み", width=18,
                command=self.load_file).grid(row=0, column=1, padx=4, sticky="w")

        tk.Button(btn_frame1, text="全行表示",         width=18,
                command=lambda: (self.row_lb.selection_clear(0, tk.END),self.filter_by_code(None))
        ).grid(row=0, column=2, padx=4, sticky="w")

        tk.Button(btn_frame1, text="設定",             width=18,
                command=self.open_settings).grid(row=0, column=3, padx=4, sticky="w")


        # 2 段目（ハイライト系）
        btn_frame2 = tk.Frame(self)
        btn_frame2.pack(pady=2, anchor="w")

        tk.Button(btn_frame2, text="患者コード・全行ハイライト", width=20,
                command=self.highlight_all_matches).grid(row=0, column=0, padx=4, sticky="w")

        tk.Button(btn_frame2, text="先頭 1 件ハイライト", width=18,
                command=self.highlight_first_match).grid(row=0, column=1, padx=4, sticky="w")

        tk.Button(btn_frame2, text="次の行へ", width=18,
                command=self.highlight_next_match).grid(row=0, column=2, padx=4, sticky="w")

        tk.Button(btn_frame2, text="ハイライト解除", width=18,
                command=self.clear_highlight).grid(row=0, column=3, padx=4, sticky="w")

        # === リスト表示 ===
        list_frame = tk.Frame(self)
        list_frame.pack(pady=4, fill=tk.BOTH, expand=True)
        self.row_lb = tk.Listbox(list_frame, width=6)
        self.row_lb.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))
        tk.Label(list_frame, text="コード").pack(side=tk.LEFT, anchor=tk.NW)
        self.row_lb.bind("<<ListboxSelect>>", self.filter_by_code)

        self.row_text = tk.Text(list_frame, wrap="none", width=120, height=25)
        self.row_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.row_text.tag_configure("hit",    background="#ffff66", foreground="#000000")  # 全体ハイライト
        self.row_text.tag_configure("single", background="#a0ffa0", foreground="#000000")  # 単一ハイライト
        self.row_text.config(state=tk.DISABLED)
        tk.Label(list_frame, text="内容").pack(side=tk.LEFT, anchor=tk.NW)

        # 行頭インデックス（"1.0", "2.0", …）を保持
        self.line_starts: list[str] = []

        # ハイライト関連状態
        self.patient_code_len: int  = 10
        self.patient_code_conv_len: int = 10
        self.trailing_commas: int   = 2
        self.highlight_pat: re.Pattern | None = None
        self.match_spans: list[tuple[str, str]] = []  # Text index の (start,end)
        self.cur_match_idx: int = -1  # -1 = 未選択

        bottom_frame = tk.Frame(self)
        bottom_frame.pack(side=tk.BOTTOM, pady=8)

        tk.Button(
            bottom_frame, text="コード変換して保存",
            width=18, command=self.convert_and_save
        ).pack()

        # === ステータスバー ===
        self.status = tk.StringVar(value="ファイル未選択")
        tk.Label(self, textvariable=self.status, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)

    # ---------- ファイル読み込み ----------
    def load_file(self):
        fp = filedialog.askopenfilename(
            title="UKE/CSV ファイル選択",
            filetypes=[
                ("すべてのファイル", "*"),
                ("UKE Files", "*.UKE"),
                ("UKE Files (lower)", "*.uke"),
                ("UKE Files (派生)", "*.UKE*"),
                ("CSV Files", "*.csv"),
            ],
        )
        if not fp:
            return
        try:
            self.file_path = Path(fp)
            _, self.rows = load_csv(self.file_path, has_header=False)
            self.display_indices = list(range(len(self.rows)))  # 全行表示
            self.refresh_lists()
            self.status.set(f"読み込み完了: {self.file_path.name}")
        except Exception as e:
            messagebox.showerror("読み込み失敗", f"{type(e).__name__}: {e}")
            self.status.set("読み込みエラー")

    # ---------- 左リストでフィルター ----------
    def filter_by_code(self, _event):
        """
        左 Listbox で頭 2 桁コードを選択したら
        右側 Text をそのコード行だけに絞り込む。
        空選択 (クリック外し) で全行に戻す。
        """
        sel = self.row_lb.curselection()
        if not sel:
            # 何も選んでいなければ全行を表示
            self.display_indices = list(range(len(self.rows)))
            self.refresh_text_only()
            self.status.set("すべて表示")
            return

        code = self.row_lb.get(sel[0])
        self.display_indices = [
            i for i, row in enumerate(self.rows)
            if DISPLAY_COL < len(row) and row[DISPLAY_COL].startswith(code)
        ]
        self.refresh_text_only()
        self.status.set(f"フィルター: {code} ({len(self.display_indices)} 行)")

    def refresh_text_only(self):
        self.row_text.config(state=tk.NORMAL)
        self.row_text.delete("1.0", tk.END)
        self.line_starts.clear()
        for idx in self.display_indices:
            row_string = "|".join(self.rows[idx])
            self.line_starts.append(self.row_text.index(tk.INSERT))
            self.row_text.insert(tk.END, row_string + "\n")
        self.row_text.config(state=tk.DISABLED)
        self._apply_highlight_to_current_view()

    def refresh_lists(self):
        if not self.display_indices:
            self.display_indices = list(range(len(self.rows)))
        # ---------- 左 Listbox ----------
        self.row_lb.delete(0, tk.END)

        seen = set()
        for idx in self.display_indices:
            row = self.rows[idx]
            code = row[DISPLAY_COL][:2] if DISPLAY_COL < len(row) else ""
            if code not in seen:
                self.row_lb.insert(tk.END, code)
                seen.add(code)

        # ---------- 右 Text ----------
        self.row_text.config(state=tk.NORMAL)
        self.row_text.delete("1.0", tk.END)
        self.line_starts.clear()
        for idx in self.display_indices:
            row_string = "|".join(self.rows[idx])
            self.line_starts.append(self.row_text.index(tk.INSERT))
            self.row_text.insert(tk.END, row_string + "\n")
        self.row_text.config(state=tk.DISABLED)
        self._apply_highlight_to_current_view()

    # ----------------------------  ハイライト関連 ----------------------------
    def _build_regex(self):
        return re.compile(rf",([0-9]{{{self.patient_code_len}}}){','*self.trailing_commas}")

    def _collect_matches(self):
        """現在の表示行に対して self.match_spans を更新"""
        self.match_spans.clear()
        pat = self.highlight_pat
        if pat is None:
            return
        for disp_idx, row_idx in enumerate(self.display_indices):
            row_string = "|".join(self.rows[row_idx])
            for m in pat.finditer(row_string):
                line_num = int(float(self.line_starts[disp_idx]))  # 1-indexed
                start_idx = f"{line_num}.{m.start()}"
                end_idx   = f"{line_num}.{m.end()}"
                self.match_spans.append((start_idx, end_idx))

    def highlight_all_matches(self):
        """既存の search_patient_code と同義。"""
        if not self.rows:
            messagebox.showwarning("警告", "まず CSV ファイルを読み込んでください。")
            return
        self.highlight_pat = self._build_regex()
        self._collect_matches()
        self.row_text.config(state=tk.NORMAL)
        self.row_text.tag_remove("hit", "1.0", tk.END)
        self.row_text.tag_remove("single", "1.0", tk.END)
        for s, e in self.match_spans:
            self.row_text.tag_add("hit", s, e)
        self.row_text.config(state=tk.DISABLED)
        self.cur_match_idx = -1
        self.status.set(f"{len(self.match_spans)} 件ハイライトしました")

    def highlight_first_match(self):
        """マッチの 1 件目だけをハイライト"""
        if not self.rows:
            messagebox.showwarning("警告", "まず CSV ファイルを読み込んでください。")
            return
        self.highlight_pat = self._build_regex()
        self._collect_matches()
        if not self.match_spans:
            messagebox.showinfo("検索結果", "該当する患者コードは見つかりませんでした。")
            return
        self.cur_match_idx = 0
        self._render_single_highlight()
        self.status.set("先頭をハイライトしました (1 / %d)" % len(self.match_spans))

    def highlight_next_match(self):
        if not self.match_spans:
            self.highlight_first_match()
            return
        self.cur_match_idx = (self.cur_match_idx + 1) % len(self.match_spans)
        self._render_single_highlight()
        self.status.set("ハイライトを移動 (%d / %d)" % (self.cur_match_idx+1, len(self.match_spans)))

    def _render_single_highlight(self):
        """self.cur_match_idx を single タグで表示"""
        self.row_text.config(state=tk.NORMAL)
        self.row_text.tag_remove("hit", "1.0", tk.END)
        self.row_text.tag_remove("single", "1.0", tk.END)
        if 0 <= self.cur_match_idx < len(self.match_spans):
            s, e = self.match_spans[self.cur_match_idx]
            self.row_text.tag_add("single", s, e)
            self.row_text.see(s)  
        self.row_text.config(state=tk.DISABLED)

    def _apply_highlight_to_current_view(self) -> None:
        """
        表示内容を基にハイライトを再描画する  
        ・self.highlight_pat が無い → 何もしない  
        ・self.cur_match_idx >=0    → 単一ハイライト（緑）  
        ・上記以外                → 全体ハイライト（黄）
        """
        if self.highlight_pat is None:
            return  # 解除済み

        # 再スキャン（フィルタ変更／設定変更時に必要）
        self._collect_matches()

        self.row_text.config(state=tk.NORMAL)
        self.row_text.tag_remove("hit",    "1.0", tk.END)
        self.row_text.tag_remove("single", "1.0", tk.END)

        if 0 <= self.cur_match_idx < len(self.match_spans):
            # 1 行だけハイライト
            s, e = self.match_spans[self.cur_match_idx]
            self.row_text.tag_add("single", s, e)
        else:
            # 全行ハイライト
            for s, e in self.match_spans:
                self.row_text.tag_add("hit", s, e)

        self.row_text.config(state=tk.DISABLED)

    def clear_highlight(self):
        self.highlight_pat = None
        self.match_spans.clear()
        self.cur_match_idx = -1
        self.row_text.config(state=tk.NORMAL)
        self.row_text.tag_remove("hit", "1.0", tk.END)
        self.row_text.tag_remove("single", "1.0", tk.END)
        self.row_text.config(state=tk.DISABLED)
        self.status.set("ハイライトを解除しました")

    # ---------- 変換ユーティリティ ----------
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
        if self.highlight_pat is None:
            messagebox.showinfo("情報", "ハイライトされた患者コードがありません。")
            return

        pat = self.highlight_pat               # ,(\d{N}),,, の形
        tc  = "," * self.trailing_commas       # 後方カンマ

        # ---- 行全体を文字列に戻して一括置換 ----
        out_lines: list[str] = []
        for row in self.rows:
            line = ",".join(row)               # 1 行をそのままカンマ連結
            fixed = pat.sub(
                lambda m: f",{self._normalize_code(m.group(1))}{tc}",
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
    def open_settings(self):
        """患者コード関連の設定をまとめて入力"""
        dialog = tk.Toplevel(self)
        dialog.title("設定")
        dialog.resizable(False, False)
        tk.Label(dialog, text="患者コード桁数（ハイライト用）").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        tk.Label(dialog, text="患者コード変換桁数").grid(        row=1, column=0, sticky="w", padx=4, pady=4)
        tk.Label(dialog, text="後方カンマ数").grid(row=2, column=0, sticky="w", padx=4, pady=4)

        len_var  = tk.IntVar(value=self.patient_code_len)
        conv_var = tk.IntVar(value=self.patient_code_conv_len)
        comma_var = tk.IntVar(value=self.trailing_commas)

        tk.Spinbox(dialog, from_=1, to=20, textvariable=len_var,  width=5).grid(row=0, column=1, padx=4)
        tk.Spinbox(dialog, from_=1, to=20, textvariable=conv_var, width=5).grid(row=1, column=1, padx=4)
        tk.Spinbox(dialog, from_=1, to=5, textvariable=comma_var, width=5).grid(row=2, column=1, padx=4)

        def on_ok():
            self.patient_code_len      = len_var.get()
            self.patient_code_conv_len = conv_var.get()
            self.trailing_commas       = comma_var.get()

            self.status.set(
                f"設定変更: ハイライト桁数={self.patient_code_len} / "
                f"変換桁数={self.patient_code_conv_len} / "
                f"後方カンマ数={self.trailing_commas}"
            )
            # ハイライト正規表現を作り直す
            if self.highlight_pat is not None:
                self.highlight_pat = re.compile(
                    rf",([0-9]{{{self.patient_code_len}}}){','*self.trailing_commas}"
                )
                self._apply_highlight_to_current_view()
            dialog.destroy()

        tk.Button(dialog, text="OK", width=8, command=on_ok).grid(row=3, column=0, columnspan=2, pady=6)
        dialog.grab_set()   # モーダル化

if __name__ == "__main__":
    app = UKEEditorGUI()
    app.mainloop()