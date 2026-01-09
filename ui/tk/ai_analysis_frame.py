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
    def __init__(self, parent, client, strategy_service, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.client = client
        self.strategy_service = strategy_service
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
        self.txt_input = scrolledtext.ScrolledText(self.strategy_tab, height=8, bg="#1e293b", fg=self.fg_color)
        self.txt_input.pack(fill="x", padx=10, pady=5)
        
        opt_frame = tk.Frame(self.strategy_tab, bg=self.bg_color)
        opt_frame.pack(fill="x", padx=10)
        
        self.refine_var = tk.BooleanVar(value=False)
        tk.Checkbutton(opt_frame, text="Refine Strategy", variable=self.refine_var, bg=self.bg_color, fg=self.fg_color, selectcolor="#1e293b").pack(side="left")
        
        self.btn_analyze = tk.Button(opt_frame, text="Analyze Strategy", command=self.on_analyze,
                                   bg=self.accent_color, fg="white", font=("Arial", 10, "bold"))
        self.btn_analyze.pack(side="right", padx=5)
        
        tk.Label(self.strategy_tab, text="Results:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=10, pady=5)
        self.txt_results = scrolledtext.ScrolledText(self.strategy_tab, bg="#1e293b", fg=self.fg_color, state="disabled")
        self.txt_results.pack(fill="both", expand=True, padx=10, pady=5)

        action_frame = tk.Frame(self.strategy_tab, bg=self.bg_color)
        action_frame.pack(fill="x", padx=10, pady=5)
        tk.Button(action_frame, text="Apply Code", command=self.on_apply).pack(side="left", padx=2)
        tk.Button(action_frame, text="Save Code", command=self.on_save).pack(side="left", padx=2)

    def on_apply(self):
        code = self._extract_code(self.txt_results.get("1.0", "end"))
        if code:
            self.txt_input.delete("1.0", "end")
            self.txt_input.insert("1.0", code)

    def on_save(self):
        code = self._extract_code(self.txt_results.get("1.0", "end"))
        if code: 
            threading.Thread(target=lambda: self.strategy_service.save_strategy_code(code), daemon=True).start()
            messagebox.showinfo("Success", "Saved as AIStrategy.py")

    def _extract_code(self, text):
        import re
        m = re.search(r"CODE_CHANGE:(.*)", text, re.DOTALL)
        if m: return m.group(1).strip().replace("```python", "").replace("```", "").strip()
        return None

    def on_load_last_backtest(self):
        app = self.master.master.master
        strategy = getattr(app, 'last_backtest_strategy', None)
        results = getattr(app, 'last_backtest_results', None)
        
        if not strategy:
            messagebox.showinfo("Info", "No recent backtest strategy found. Run a backtest first.")
            return
            
        self.txt_input.delete("1.0", "end")
        self.txt_input.insert("1.0", strategy)
        
        if results:
            self.txt_results.config(state="normal")
            self.txt_results.delete("1.0", "end")
            
            summary = ""
            if isinstance(results, dict):
                summary = f"Backtest Results for Analysis:\n"
                summary += f"Strategy: {results.get('strategy_class')}\n"
                summary += f"Stats: {results.get('stdout', '')[:500]}...\n"
            else:
                summary = str(results)
                
            self.txt_results.insert("1.0", f"--- LOADED BACKTEST RESULTS ---\n{summary}\n--- END RESULTS ---\n\n")
            self.txt_results.config(state="disabled")
            
        messagebox.showinfo("Success", "Loaded strategy and results from last backtest.")

    def on_analyze(self):
        code = self.txt_input.get("1.0", "end-1c").strip()
        if not code:
            messagebox.showwarning("Warning", "Please paste strategy code.")
            return
        
        self.btn_analyze.config(state="disabled", text="Analyzing...")
        
        def _task():
            try:
                if self.refine_var.get():
                    res = self.strategy_service.refine_strategy(code)
                else:
                    prompt = f"Analyze this Freqtrade strategy code and provide insights. Use CODE_CHANGE: marker for improvements.\n\n{code}"
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

    def setup_loss_tab(self):
        btn_frame = tk.Frame(self.loss_tab, bg=self.bg_color)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Button(btn_frame, text="Fetch Recent Trades", command=self.on_fetch_trades, bg="#FF9800", fg="white").pack(side="left", padx=5)
        tk.Button(btn_frame, text="Analyze Losses", command=self.on_analyze_losses, bg="#F44336", fg="white").pack(side="left", padx=5)
        
        self.txt_loss_results = scrolledtext.ScrolledText(self.loss_tab, bg="#1e293b", fg=self.fg_color, state="disabled")
        self.txt_loss_results.pack(fill="both", expand=True, padx=10, pady=5)

    def on_fetch_trades(self):
        def _task():
            try:
                trades = self.client.get_trades()
                self.after(0, lambda: messagebox.showinfo("Trades", f"Fetched {len(trades)} trades"))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=_task, daemon=True).start()

    def on_analyze_losses(self):
        def _task():
            try:
                trades = self.client.get_trades()
                loss_trades = [t for t in trades if t.get('profit_ratio', 0) < 0]
                if not loss_trades:
                    self.after(0, lambda: messagebox.showinfo("Analysis", "No loss trades found to analyze"))
                    return
                
                from utils.backtest_runner import build_trade_forensics
                forensics = build_trade_forensics(loss_trades)
                prompt = f"Analyze these losing trades and provide insights for strategy improvement:\n\n{json.dumps(forensics)}"
                res = self.ollama_client.generate_text(prompt)
                self.after(0, lambda: self._apply_loss_results(res))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
        threading.Thread(target=_task, daemon=True).start()

    def _apply_loss_results(self, text):
        self.txt_loss_results.config(state="normal")
        self.txt_loss_results.delete("1.0", "end")
        self.txt_loss_results.insert("1.0", text)
        self.txt_loss_results.config(state="disabled")
