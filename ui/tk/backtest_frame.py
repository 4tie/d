import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath(os.curdir))

from utils.backtest_runner import run_backtest
from config.settings import BOT_CONFIG_PATH

class BacktestFrame(tk.Frame):
    def __init__(self, parent, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color
        
        self.setup_ui()

    def setup_ui(self):
        container = tk.Frame(self, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Controls Group
        ctrl_group = tk.LabelFrame(container, text="Configuration", bg=self.bg_color, fg=self.fg_color)
        ctrl_group.pack(fill="x", pady=5)
        
        # Row 1: Timeframe and Timerange
        row1 = tk.Frame(ctrl_group, bg=self.bg_color)
        row1.pack(fill="x", padx=5, pady=2)

        tk.Label(row1, text="Timeframe:", bg=self.bg_color, fg=self.fg_color).pack(side="left", padx=5)
        self.tf_var = tk.StringVar(value="5m")
        self.tf_combo = ttk.Combobox(row1, textvariable=self.tf_var, width=8, values=["1m", "5m", "15m", "30m", "1h", "4h", "1d"])
        self.tf_combo.pack(side="left", padx=5)

        tk.Label(row1, text="Timerange:", bg=self.bg_color, fg=self.fg_color).pack(side="left", padx=5)
        self.tr_var = tk.StringVar(value="")
        self.tr_combo = ttk.Combobox(row1, textvariable=self.tr_var, width=15)
        self._add_tr_presets()
        self.tr_combo.pack(side="left", padx=5)
        
        # Row 2: Pairs Selection
        row2 = tk.Frame(ctrl_group, bg=self.bg_color)
        row2.pack(fill="x", padx=5, pady=2)

        tk.Label(row2, text="Pairs (comma separated):", bg=self.bg_color, fg=self.fg_color).pack(side="left", padx=5)
        self.pairs_var = tk.StringVar(value="BTC/USDT,ETH/USDT,SOL/USDT")
        tk.Entry(row2, textvariable=self.pairs_var, width=50).pack(side="left", padx=5, fill="x", expand=True)

        # Action Buttons
        btn_frame = tk.Frame(container, bg=self.bg_color)
        btn_frame.pack(fill="x", pady=5)

        self.btn_run = tk.Button(btn_frame, text="Run Backtest", command=self.on_run,
                               bg=self.accent_color, fg="white", font=("Arial", 10, "bold"))
        self.btn_run.pack(side="right", padx=5)

        self.btn_download = tk.Button(btn_frame, text="Download Data", command=self.on_download,
                                    bg="#6366f1", fg="white")
        self.btn_download.pack(side="right", padx=5)
        
        # Code and Results
        tk.Label(container, text="Strategy Code:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=5)
        self.txt_code = scrolledtext.ScrolledText(container, height=10, bg="#1e293b", fg=self.fg_color)
        self.txt_code.pack(fill="x", padx=5, pady=5)
        
        tk.Label(container, text="Results:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=5)
        self.txt_results = scrolledtext.ScrolledText(container, bg="#1e293b", fg=self.fg_color, state="disabled")
        self.txt_results.pack(fill="both", expand=True, padx=5, pady=5)

    def on_download(self):
        from utils.backtest_runner import download_data
        threading.Thread(target=lambda: download_data(BOT_CONFIG_PATH, self.tr_var.get(), self.tf_var.get(), self.pairs_var.get()), daemon=True).start()
        messagebox.showinfo("Download", "Download started in background for selected pairs")

    def on_run(self):
        code = self.txt_code.get("1.0", "end-1c").strip()
        if not code:
            messagebox.showwarning("Warning", "Please paste strategy code.")
            return
            
        self.btn_run.config(state="disabled", text="Running...")
        self.txt_results.config(state="normal")
        self.txt_results.delete("1.0", "end")
        self.txt_results.insert("1.0", "Backtest started...")
        self.txt_results.config(state="disabled")
        
        def _task():
            try:
                res = run_backtest(
                    strategy_code=code, 
                    config_path=BOT_CONFIG_PATH, 
                    timeframe=self.tf_var.get(), 
                    timerange=self.tr_var.get(),
                    pairs=self.pairs_var.get()
                )
                self.after(0, lambda: self._apply_results(res))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self.btn_run.config(state="normal", text="Run Backtest"))
        
        threading.Thread(target=_task, daemon=True).start()

    def _apply_results(self, res):
        self.txt_results.config(state="normal")
        self.txt_results.delete("1.0", "end")
        if isinstance(res, dict):
            summary = f"Strategy: {res.get('strategy_class')}\nFile: {res.get('result_file')}\n\nSTDOUT:\n{res.get('stdout')}"
            self.txt_results.insert("1.0", summary)
        else:
            self.txt_results.insert("1.0", str(res))
        self.txt_results.config(state="disabled")
