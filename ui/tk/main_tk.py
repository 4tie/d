import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from config.settings import (FREQTRADE_URL, API_USER, API_PASS, 
                               WINDOW_TITLE, OLLAMA_BASE_URL, OLLAMA_MODEL, 
                               OLLAMA_OPTIONS, OLLAMA_TASK_MODELS, UPDATE_INTERVAL)
    from api.client import FreqtradeClient
    from core.strategy_service import StrategyService
    from utils.logging_setup import setup_logging
except ImportError as e:
    print(f"Import error: {e}")
    sys.exit(1)

class SmartBotAppTK:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{WINDOW_TITLE} (Tkinter)")
        self.root.geometry("1024x768")
        
        # Configure dark theme colors
        self.bg_color = "#0f172a"
        self.fg_color = "#f1f5f9"
        self.accent_color = "#3b82f6"
        self.root.configure(bg=self.bg_color)
        
        # Initialize services
        self.client = FreqtradeClient(FREQTRADE_URL or "", API_USER or "", API_PASS or "")
        self.strategy_service = StrategyService()
        
        self.setup_ui()
        self.start_update_loop()

    def setup_ui(self):
        # Notebook (Tabs)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background=self.bg_color, borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e293b", foreground="#94a3b8", padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", "#334155")], foreground=[("selected", "#ffffff")])
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=10, pady=10)
        
        # Create Tabs
        self.dashboard_frame = tk.Frame(self.notebook, bg=self.bg_color)
        self.control_frame = tk.Frame(self.notebook, bg=self.bg_color)
        self.settings_frame = tk.Frame(self.notebook, bg=self.bg_color)
        
        self.notebook.add(self.dashboard_frame, text="Dashboard")
        self.notebook.add(self.control_frame, text="Control")
        self.notebook.add(self.settings_frame, text="Settings")
        
        self.setup_dashboard()
        self.setup_status_bar()

    def setup_dashboard(self):
        lbl_title = tk.Label(self.dashboard_frame, text="Bot Status", font=("Arial", 18, "bold"), 
                           bg=self.bg_color, fg=self.fg_color)
        lbl_title.pack(pady=20)
        
        self.status_var = tk.StringVar(value="Checking...")
        self.lbl_status = tk.Label(self.dashboard_frame, textvariable=self.status_var, 
                                 bg=self.bg_color, fg=self.accent_color, font=("Arial", 14))
        self.lbl_status.pack()
        
        self.profit_var = tk.StringVar(value="Profit: ---")
        self.lbl_profit = tk.Label(self.dashboard_frame, textvariable=self.profit_var, 
                                 bg=self.bg_color, fg="#22c55e", font=("Arial", 14))
        self.lbl_profit.pack(pady=10)
        
        btn_refresh = tk.Button(self.dashboard_frame, text="Refresh Data", command=self.update_stats,
                              bg=self.accent_color, fg="white", font=("Arial", 10, "bold"),
                              relief="flat", padx=20, pady=10)
        btn_refresh.pack(pady=20)

    def setup_status_bar(self):
        self.status_bar_var = tk.StringVar(value="Initializing...")
        status_bar = tk.Label(self.root, textvariable=self.status_bar_var, bd=1, relief="sunken", anchor="w",
                            bg="#1e293b", fg="#94a3b8")
        status_bar.pack(side="bottom", fill="x")

    def update_stats(self):
        def _fetch():
            try:
                status = self.client.get_status()
                profit = self.client.get_profit()
                self.root.after(0, lambda: self._apply_stats(status, profit))
            except Exception as e:
                self.root.after(0, lambda: self.status_bar_var.set(f"Error: {e}"))

        threading.Thread(target=_fetch, daemon=True).start()

    def _apply_stats(self, status, profit):
        self.status_var.set(f"Bot Status: {status}")
        if status == "Connected":
            self.status_bar_var.set("Bot: Connected")
        else:
            self.status_bar_var.set(f"Bot: {status}")
            
        if isinstance(profit, dict) and 'profit_all_percent' in profit:
            p = profit['profit_all_percent']
            self.profit_var.set(f"Total Profit: {p:.2f}%")
        else:
            self.profit_var.set("Total Profit: ---")

    def start_update_loop(self):
        self.update_stats()
        # Tkinter after uses ms, UPDATE_INTERVAL is in ms from settings
        self.root.after(UPDATE_INTERVAL, self.start_update_loop)

if __name__ == "__main__":
    setup_logging()
    root = tk.Tk()
    app = SmartBotAppTK(root)
    root.mainloop()
