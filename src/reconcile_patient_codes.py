# src/reconcile_patient_codes.py
from __future__ import annotations
import csv, re, sys
from pathlib import Path
from typing import Iterable, Tuple, List, Dict, Set, Optional

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk  # ← 追加（インジケータ用）

# =========================================
# 基本ユーティリティ
# =========================================

def _open_text(path: Path):
    """
    Shift-JIS(cp932) → UTF-8-SIG → UTF-8 の順で開く。
    """
    last_err = None
    for enc in ("cp932", "utf-8-sig", "utf-8"):
        try:
            f = path.open("r", encoding=enc, newline="")
            return f, enc
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError(f"Cannot open: {path}")

def _read_fieldnames_only(path: Path) -> Tuple[List[str], str]:
    """
    CSVのヘッダ（fieldnames）のみを読み取る。戻り値: (fieldnames, encoding)
    """
    f, enc = _open_text(path)
    with f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            raise RuntimeError(f"CSVが空です: {path.name}")
    # 空文字列が混じるケースのケア
    headers = [h if h is not None else "" for h in headers]
    return headers, enc

def _iter_dict_rows(path: Path) -> Iterable[Dict[str, str]]:
    """
    DictReader で行をイテレート。エンコーディングは自動判定。
    """
    f, enc = _open_text(path)
    with f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise RuntimeError(f"ヘッダ行がありません: {path.name}")
        for row in reader:
            yield row

def _norm_code_numeric(s: str) -> str:
    """
    照合用（数値一致）:
      - 数字以外を除去
      - 先頭0は落とす（空→""、全0→"0"）
    """
    if s is None:
        return ""
    digits = "".join(ch for ch in str(s) if ch.isdigit())
    if not digits:
        return ""
    stripped = digits.lstrip("0")
    return stripped if stripped else "0"

def _norm_code_exact(s: str) -> str:
    """
    厳密一致（トリムのみ）
    """
    return "" if s is None else str(s).strip()

# =========================================
# 簡易「処理中」ダイアログ
# =========================================

class BusyDialog:
    def __init__(self, parent: tk.Tk, text: str = "処理中…"):
        self.top = tk.Toplevel(parent)
        self.top.title(text)
        self.top.transient(parent)
        self.top.grab_set()
        self.top.resizable(False, False)

        # 位置を親の中央あたりに
        try:
            self.top.geometry(f"+{parent.winfo_rootx()+80}+{parent.winfo_rooty()+80}")
        except Exception:
            pass

        frm = ttk.Frame(self.top, padding=12)
        frm.pack(fill="both", expand=True)

        self.label_var = tk.StringVar(value=text)
        ttk.Label(frm, textvariable=self.label_var).pack(anchor="w", pady=(0,8))

        self.pbar = ttk.Progressbar(frm, mode="indeterminate")
        self.pbar.pack(fill="x")
        self.pbar.start(12)

        self.top.update_idletasks()

    def update(self, text: str):
        self.label_var.set(text)
        self.top.update_idletasks()

    def close(self):
        try:
            self.pbar.stop()
        except Exception:
            pass
        try:
            self.top.grab_release()
        except Exception:
            pass
        self.top.destroy()

# =========================================
# カラム選択ダイアログ
# =========================================

def _suggest(name_list: List[str], candidates: List[str]) -> str:
    """
    候補（優先順）から最初に一致するヘッダ名を返す。なければ先頭。
    """
    s = set(name_list)
    for c in candidates:
        if c in s:
            return c
    return name_list[0] if name_list else ""

def _ask_columns_dialog(parent: tk.Tk, log_headers: List[str], ext_headers: List[str]) -> Tuple[str, str, str]:
    """
    2つのヘッダリストから、照合に使う「ログ側カラム」「外部側カラム」「モード」を選ばせる。
    戻り値: (log_col, ext_col, mode)  mode ∈ {"numeric", "exact"}
    """
    dlg = tk.Toplevel(parent)
    dlg.title("照合カラムの選択")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.resizable(True, False)
    try:
        dlg.geometry(f"+{parent.winfo_rootx()+100}+{parent.winfo_rooty()+100}")
    except Exception:
        pass

    frm = ttk.Frame(dlg, padding=12)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="変換ログCSVのカラム（患者コードに相当）").grid(row=0, column=0, sticky="w")
    log_var = tk.StringVar(value=_suggest(
        log_headers, ["converted_code", "患者コード", "patient_code", "code", "original_code", "患者番号", "患者ID", "patient_id"]
    ))
    log_cb = ttk.Combobox(frm, textvariable=log_var, values=log_headers, state="readonly", width=40)
    log_cb.grid(row=1, column=0, sticky="we", pady=(0,8))

    ttk.Label(frm, text="外部CSVのカラム（患者コードに相当）").grid(row=2, column=0, sticky="w")
    ext_var = tk.StringVar(value=_suggest(
        ext_headers, ["患者コード", "患者番号", "patient_code", "code", "患者ID", "patient_id", "ID"]
    ))
    ext_cb = ttk.Combobox(frm, textvariable=ext_var, values=ext_headers, state="readonly", width=40)
    ext_cb.grid(row=3, column=0, sticky="we", pady=(0,8))

    ttk.Label(frm, text="照合モード").grid(row=4, column=0, sticky="w")
    mode_var = tk.StringVar(value="numeric")  # 既定：数値一致（先頭ゼロ無視）
    mode_row = ttk.Frame(frm); mode_row.grid(row=5, column=0, sticky="w", pady=(0,8))
    ttk.Radiobutton(mode_row, text="数値一致（数字のみ・先頭ゼロ無視）", value="numeric", variable=mode_var).pack(anchor="w")
    ttk.Radiobutton(mode_row, text="厳密一致（そのまま）", value="exact", variable=mode_var).pack(anchor="w")

    btns = ttk.Frame(frm); btns.grid(row=6, column=0, sticky="e", pady=(10,0))
    ok = ttk.Button(btns, text="OK", command=dlg.destroy)
    ok.pack(side="right")

    dlg.columnconfigure(0, weight=1)
    frm.columnconfigure(0, weight=1)

    dlg.wait_window()
    log_col = log_var.get().strip()
    ext_col = ext_var.get().strip()
    mode    = mode_var.get().strip() or "numeric"
    if not log_col or not ext_col:
        raise RuntimeError("照合カラムの選択が完了していません。")
    return log_col, ext_col, mode

# =========================================
# 照合本体
# =========================================

def _get_normalizer(mode: str):
    return _norm_code_numeric if mode == "numeric" else _norm_code_exact

def reconcile_codes_with_columns(
    parent: tk.Tk,
    log_csv: Path,
    external_csv: Path,
    log_col: str,
    ext_col: str,
    mode: str = "numeric",
) -> Tuple[List[Dict[str, str]], Dict[str, int], List[str]]:
    """
    指定カラムで照合。外部に存在しない行だけを返す。
    戻り値: (not_found_rows, stats, log_fieldnames)
    """
    normalize = _get_normalizer(mode)

    # 外部CSV → セット化
    busy = BusyDialog(parent, "外部CSVを読み込み中…")
    try:
        ext_codes: Set[str] = set()
        ext_total_rows = 0
        for r in _iter_dict_rows(external_csv):
            ext_total_rows += 1
            key = normalize(r.get(ext_col, ""))
            if key:
                ext_codes.add(key)
        busy.update("外部CSVの患者コードをインデックス化中…")
    finally:
        busy.close()

    # 変換ログ → 不一致行を抽出
    busy = BusyDialog(parent, "変換ログを照合中…")
    not_found_rows: List[Dict[str, str]] = []
    stats = {
        "log_total_rows": 0,
        "ext_total_rows": ext_total_rows,
        "ext_unique_codes": len(ext_codes),
        "not_found": 0,
        "empty_in_log": 0,
    }
    log_fieldnames: List[str] = []
    try:
        # fieldnames を先に取得（出力時に使う）
        f, enc = _open_text(log_csv)
        with f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise RuntimeError("変換ログCSVのヘッダが読めません。")
            log_fieldnames = list(reader.fieldnames)
        # 実データ照合
        for r in _iter_dict_rows(log_csv):
            stats["log_total_rows"] += 1
            raw = r.get(log_col, "")
            key = normalize(raw)
            if not key:
                stats["empty_in_log"] += 1
                continue
            if key not in ext_codes:
                not_found_rows.append(r)
        stats["not_found"] = len(not_found_rows)
        busy.update("照合を集計中…")
    finally:
        busy.close()

    return not_found_rows, stats, log_fieldnames

# =========================================
# GUIエントリポイント
# =========================================

def run_reconcile_dialog(parent: tk.Tk) -> None:
    """
    読み込み順:
      1) 変換ログCSV（*_changes.csv）
      2) 外部CSV（患者情報）
      3) 両CSVのカラム選択ダイアログ
      4) 照合 → 不一致行のみCSV出力
    各フェーズで「処理中…」を表示。
    """
    # --- 1) 変換ログCSV ---
    log_fp = filedialog.askopenfilename(
        parent=parent,
        title="変換ログCSV（*_changes.csv）を選択",
        filetypes=[("CSV ファイル", "*.csv"), ("すべてのファイル", "*.*")]
    )
    if not log_fp:
        return
    log_path = Path(log_fp)

    # ヘッダだけ先に読む（列選択のため）
    try:
        busy = BusyDialog(parent, "変換ログのヘッダを読み込み中…")
        log_headers, _ = _read_fieldnames_only(log_path)
    except Exception as e:
        try:
            busy.close()
        except Exception:
            pass
        messagebox.showerror("読み込み失敗", f"変換ログCSVのヘッダ取得に失敗しました:\n{e}", parent=parent)
        return
    finally:
        try:
            busy.close()
        except Exception:
            pass

    # --- 2) 外部CSV ---
    ext_fp = filedialog.askopenfilename(
        parent=parent,
        title="外部CSV（患者情報など）を選択",
        filetypes=[("CSV ファイル", "*.csv"), ("すべてのファイル", "*.*")]
    )
    if not ext_fp:
        return
    ext_path = Path(ext_fp)

    # 外部CSVのヘッダも読む
    try:
        busy = BusyDialog(parent, "外部CSVのヘッダを読み込み中…")
        ext_headers, _ = _read_fieldnames_only(ext_path)
    except Exception as e:
        try:
            busy.close()
        except Exception:
            pass
        messagebox.showerror("読み込み失敗", f"外部CSVのヘッダ取得に失敗しました:\n{e}", parent=parent)
        return
    finally:
        try:
            busy.close()
        except Exception:
            pass

    # --- 3) カラム選択ダイアログ ---
    try:
        log_col, ext_col, mode = _ask_columns_dialog(parent, log_headers, ext_headers)
    except Exception as e:
        messagebox.showwarning("中止", str(e), parent=parent)
        return

    # --- 4) 照合実行 ---
    try:
        not_found_rows, stats, log_fieldnames = reconcile_codes_with_columns(
            parent=parent,
            log_csv=log_path,
            external_csv=ext_path,
            log_col=log_col,
            ext_col=ext_col,
            mode=mode,
        )
    except Exception as e:
        messagebox.showerror("照合失敗", str(e), parent=parent)
        return

    # --- 5) 結果の保存 ---
    default_name = f"{log_path.stem}_NOT_FOUND_by_{log_col}_vs_{ext_col}.csv"
    save_fp = filedialog.asksaveasfilename(
        parent=parent,
        title="未存在コード行をCSV出力",
        initialdir=str(log_path.parent),
        initialfile=default_name,
        defaultextension=".csv",
        filetypes=[("CSV ファイル", "*.csv"), ("すべてのファイル", "*.*")]
    )
    if not save_fp:
        return
    out_path = Path(save_fp)

    # 書き出し（Shift-JIS/CRLF）。元ログの全カラムを維持し、末尾にメタ情報を追記。
    busy = BusyDialog(parent, "CSVを書き出し中…")
    try:
        header = list(log_fieldnames) + ["__checked_log_column__", "__external_column__", "__match_mode__"]
        with out_path.open("w", encoding="cp932", newline="") as f:
            writer = csv.writer(f, lineterminator="\r\n")
            writer.writerow(header)
            for r in not_found_rows:
                row = [r.get(k, "") for k in log_fieldnames] + [log_col, ext_col, mode]
                writer.writerow(row)
        busy.update("完了に向けて後処理中…")
    except Exception as e:
        messagebox.showerror("保存失敗", f"CSV書き出しに失敗しました:\n{e}", parent=parent)
        return
    finally:
        busy.close()

    # --- 6) サマリ ---
    msg = (
        "患者コード照合が完了しました。\n\n"
        f"[照合モード]              : {'数値一致' if mode=='numeric' else '厳密一致'}\n"
        f"[ログ行数]                : {stats['log_total_rows']}\n"
        f"[外部CSV 行数]            : {stats['ext_total_rows']}\n"
        f"[外部ユニーク件数]        : {stats['ext_unique_codes']}（列: {ext_col}）\n"
        f"[未存在（出力件数）]      : {stats['not_found']}\n"
        f"[ログ側コード空欄件数]    : {stats['empty_in_log']}\n\n"
        f"出力: {out_path.name}"
    )
    messagebox.showinfo("完了", msg, parent=parent)