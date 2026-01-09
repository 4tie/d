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
        top_frame = tk.Frame(self, bg=self.bg_color)
        top_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(top_frame, text="Timeframe:", bg=self.bg_color, fg=self.fg_color).pack(side="left", padx=5)
        self.tf_var = tk.StringVar(value="5m")
        tk.Entry(top_frame, textvariable=self.tf_var, width=10).pack(side="left", padx=5)
        
        self.btn_run = tk.Button(top_frame, text="Run Backtest", command=self.on_run,
                               bg=self.accent_color, fg="white", font=("Arial", 10, "bold"))
        self.btn_run.pack(side="right", padx=5)
        
        tk.Label(self, text="Strategy Code:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=10)
        self.txt_code = scrolledtext.ScrolledText(self, height=12, bg="#1e293b", fg=self.fg_color)
        self.txt_code.pack(fill="x", padx=10, pady=5)
        
        tk.Label(self, text="Results:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=10)
        self.txt_results = scrolledtext.ScrolledText(self, bg="#1e293b", fg=self.fg_color, state="disabled")
        self.txt_results.pack(fill="both", expand=True, padx=10, pady=5)

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
                res = run_backtest(strategy_code=code, config_path=BOT_CONFIG_PATH, timeframe=self.tf_var.get())
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
