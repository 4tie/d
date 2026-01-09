import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import os
import json

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath(os.curdir))

from utils.ollama_client import OllamaClient
from config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL_ANALYSIS, OLLAMA_OPTIONS

class AIAnalysisFrame(tk.Frame):
    def __init__(self, parent, client, threadpool, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.client = client
        self.threadpool = threadpool
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color
        
        self.ollama_client = OllamaClient(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL_ANALYSIS, options=OLLAMA_OPTIONS)
        
        self.setup_ui()

    def setup_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)
        
        self.strategy_tab = tk.Frame(self.notebook, bg=self.bg_color)
        self.loss_tab = tk.Frame(self.notebook, bg=self.bg_color)
        
        self.notebook.add(self.strategy_tab, text="Strategy Analysis")
        self.notebook.add(self.loss_tab, text="Loss Analysis")
        
        self.setup_strategy_tab()
        self.setup_loss_tab()

    def setup_strategy_tab(self):
        tk.Label(self.strategy_tab, text="Strategy Code:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=10, pady=5)
        self.txt_input = scrolledtext.ScrolledText(self.strategy_tab, height=10, bg="#1e293b", fg=self.fg_color)
        self.txt_input.pack(fill="x", padx=10, pady=5)
        
        self.btn_analyze = tk.Button(self.strategy_tab, text="Analyze Strategy", command=self.on_analyze,
                                   bg=self.accent_color, fg="white", font=("Arial", 10, "bold"))
        self.btn_analyze.pack(pady=5)
        
        tk.Label(self.strategy_tab, text="Results:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=10, pady=5)
        self.txt_results = scrolledtext.ScrolledText(self.strategy_tab, bg="#1e293b", fg=self.fg_color, state="disabled")
        self.txt_results.pack(fill="both", expand=True, padx=10, pady=5)

    def setup_loss_tab(self):
        btn_frame = tk.Frame(self.loss_tab, bg=self.bg_color)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Button(btn_frame, text="Fetch Recent Trades", command=self.on_fetch_trades, bg="#FF9800", fg="white").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Analyze Losses", command=self.on_analyze_losses, bg="#F44336", fg="white").pack(side="left", padx=5)
        
        self.txt_loss_results = scrolledtext.ScrolledText(self.loss_tab, bg="#1e293b", fg=self.fg_color, state="disabled")
        self.txt_loss_results.pack(fill="both", expand=True, padx=10, pady=5)

    def on_analyze(self):
        code = self.txt_input.get("1.0", "end-1c").strip()
        if not code:
            messagebox.showwarning("Warning", "Please paste strategy code.")
            return
        
        self.btn_analyze.config(state="disabled", text="Analyzing...")
        
        def _task():
            try:
                prompt = f"Analyze this Freqtrade strategy code and provide insights:\n\n{code}"
                res = self.ollama_client.generate_text(prompt)
                self.after(0, lambda: self._apply_results(res))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self.btn_analyze.config(state="normal", text="Analyze Strategy"))
        
        threading.Thread(target=_task, daemon=True).start()

    def _apply_results(self, text):
        self.txt_results.config(state="normal")
        self.txt_results.delete("1.0", "end")
        self.txt_results.insert("1.0", text)
        self.txt_results.config(state="disabled")

    def on_fetch_trades(self):
        messagebox.showinfo("Info", "Fetching trades... (Mock)")

    def on_analyze_losses(self):
        messagebox.showinfo("Info", "Analyzing losses... (Mock)")
