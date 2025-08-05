#!/usr/bin/env python3
# src/gui.py — フィルター機能付き
import re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from pathlib import Path
from typing import List, Optional

from editor import load_csv, replace_cell, save_csv

# どの列を “コード列” として表示・フィルター対象にするか
DISPLAY_COL = 0   # 先頭列

class UKEEditorGUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("UKE CSV Editor")
        self.geometry("780x520")
        self.resizable(False, False)

        # データ保持
        self.file_path: Optional[Path] = None
        self.rows: List[List[str]] = []
        self.display_indices: List[int] = []  # フィルター適用後の行インデックス

        # === 上部ボタン ===
        btn_frame = tk.Frame(self)
        btn_frame.pack(pady=6)
        tk.Button(btn_frame, text="リネーム", width=10,
                  command=self.rename_files).grid(row=0, column=0, padx=6)
        tk.Button(btn_frame, text="ファイル読み込み", width=14,
                  command=self.load_file).grid(row=0, column=1, padx=6)
        tk.Button(btn_frame, text="患者コード検索", width=14,
                  command=self.search_patient_code).grid(row=0, column=2, padx=6)
        tk.Button(btn_frame, text="全行表示", width=10,
          command=lambda: (self.row_lb.selection_clear(0, tk.END),
                           self.filter_by_code(None))).grid(row=0, column=3, padx=6)

        # === リスト表示 ===
        list_frame = tk.Frame(self)
        list_frame.pack(pady=4, fill=tk.BOTH, expand=True)
        self.row_lb = tk.Listbox(list_frame, width=6)
        self.row_lb.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))
        tk.Label(list_frame, text="コード").pack(side=tk.LEFT, anchor=tk.NW)
        self.row_lb.bind("<<ListboxSelect>>", self.filter_by_code)
        # Text へ置換（行単位の開始オフセットを保存）
        self.row_text = tk.Text(list_frame, wrap="none", width=120, height=25)
        self.row_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.row_text.tag_configure("hit",background="#ffff66",foreground="#000000")
        self.row_text.tag_configure("sel_line", background="#ddeeff")
        self.row_text.config(state=tk.DISABLED)
        tk.Label(list_frame, text="内容").pack(side=tk.LEFT, anchor=tk.NW)

        # 行頭インデックス（"1.0", "2.0", …）を保持
        self.line_starts: list[str] = []

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

    # ---------- セル置換 ----------
    def run_replace(self):
        if not self.file_path:
            messagebox.showwarning("警告", "まず CSV ファイルを読み込んでください。")
            return
        row_sel = self.row_lb.curselection()
        if not row_sel:
            messagebox.showwarning("警告", "まずコード列を選択してください。")
            return
        row_i = self.display_indices[row_sel[0]]  # 実際の行番号

        col_i = simpledialog.askinteger("列番号入力", "置換したい列番号を入力（0 始まり）")
        if col_i is None:
            return
        new_val = simpledialog.askstring("新しい値", f"行 {row_i}, 列 {col_i} を何に置換しますか？")
        if new_val is None:
            return

        try:
            replace_cell(self.rows, row_i, col_i, new_val)
            if col_i == DISPLAY_COL:  # 表示列が変わった場合はリストも更新
                self.refresh_lists()
            out_path = save_csv(self.file_path, self.rows)
            messagebox.showinfo("完了", f"編集後ファイルを保存しました：\n{out_path}")
            self.status.set(f"保存完了: {out_path.name}")
        except Exception as e:
            messagebox.showerror("エラー", str(e))

    # ---------- 患者コード検索（全マッチをハイライト） ----------
    def search_patient_code(self):
        """
        ,XXXXXXXXXX, 形式 (10桁数値) を含むすべての箇所を
        Text ウィジェット上で黄色ハイライト。
        既存ハイライトがあればまず除去する。
        """
        if not self.rows:
            messagebox.showwarning("警告", "まず CSV ファイルを読み込んでください。")
            return
        
        if self.row_text.tag_ranges("hit"):
            self.row_text.config(state=tk.NORMAL)
            self.row_text.tag_remove("hit", "1.0", tk.END)
            self.row_text.tag_remove("sel_line", "1.0", tk.END)
            self.row_text.config(state=tk.DISABLED)
            self.status.set("ハイライトを解除しました")
            return

        pat = re.compile(r",[0-9]{10},")
        hits = 0
        first_disp_idx: int | None = None

        # 旧ハイライト除去
        self.row_text.config(state=tk.NORMAL)
        self.row_text.tag_remove("hit", "1.0", tk.END)
        self.row_text.tag_remove("sel_line", "1.0", tk.END)
        self.row_text.config(state=tk.DISABLED)

        # 検索してタグ付け
        self.row_text.config(state=tk.NORMAL)
        for disp_idx, row_idx in enumerate(self.display_indices):
            row_string = "|".join(self.rows[row_idx])
            for m in pat.finditer(row_string):
                line_num = int(float(self.line_starts[disp_idx]))    # 1-indexed
                start_idx = f"{line_num}.{m.start()}"
                end_idx   = f"{line_num}.{m.end()}"
                self.row_text.tag_add("hit", start_idx, end_idx)
                hits += 1
            if first_disp_idx is None and pat.search(row_string):
                first_disp_idx = disp_idx   # スクロール用
        self.row_text.config(state=tk.DISABLED)

        if first_disp_idx is not None:
            self.row_lb.selection_clear(0, tk.END)
            self.row_lb.selection_set(first_disp_idx)

        if hits:
            self.status.set(f"{hits} 件ハイライトしました")
        else:
            messagebox.showinfo("検索結果", "該当する患者コードは見つかりませんでした。")
            self.status.set("ヒットなし")

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


if __name__ == "__main__":
    app = UKEEditorGUI()
    app.mainloop()
