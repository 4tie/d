import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath(os.curdir))

try:
    from config.settings import (FREQTRADE_URL, API_USER, API_PASS, 
                               WINDOW_TITLE, OLLAMA_BASE_URL, OLLAMA_MODEL, 
                               OLLAMA_OPTIONS, OLLAMA_TASK_MODELS, UPDATE_INTERVAL)
    from api.client import FreqtradeClient
    from core.strategy_service import StrategyService
    from utils.logging_setup import setup_logging
    from ui.tk.bot_control_frame import BotControlFrame
    from ui.tk.ai_builder_frame import AIBuilderFrame
    from ui.tk.backtest_frame import BacktestFrame
    from ui.tk.chat_frame import ChatFrame
    from ui.tk.settings_frame import SettingsFrame
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
        self.surface_color = "#1e293b"
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
        style.configure("TNotebook.Tab", background=self.surface_color, foreground="#94a3b8", padding=[12, 6], font=("Segoe UI", 10))
        style.map("TNotebook.Tab", 
                 background=[("selected", "#334155")], 
                 foreground=[("selected", "#ffffff")],
                 font=[("selected", ("Segoe UI", 10, "bold"))])
        
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both", padx=15, pady=15)
        
        # Create Tabs
        self.dashboard_frame = tk.Frame(self.notebook, bg=self.bg_color)
        self.builder_frame = AIBuilderFrame(self.notebook, self, self.bg_color, self.fg_color, self.accent_color)
        self.control_frame = BotControlFrame(self.notebook, self.client, self.strategy_service, self.bg_color, self.fg_color, self.accent_color)
        self.backtest_frame = BacktestFrame(self.notebook, self, self.bg_color, self.fg_color, self.accent_color)
        self.chat_frame = ChatFrame(self.notebook, self, self.bg_color, self.fg_color, self.accent_color)
        self.settings_frame = SettingsFrame(self.notebook, self, self.bg_color, self.fg_color, self.accent_color)
        
        self.notebook.add(self.dashboard_frame, text="Dashboard")
        self.notebook.add(self.builder_frame, text="AI Builder")
        self.notebook.add(self.control_frame, text="Control")
        self.notebook.add(self.backtest_frame, text="Backtest")
        self.notebook.add(self.chat_frame, text="AI Chat")
        self.notebook.add(self.settings_frame, text="Settings")
        
        self.setup_dashboard()
        self.setup_status_bar()

    def setup_dashboard(self):
        lbl_title = tk.Label(self.dashboard_frame, text="Bot Status", font=("Segoe UI", 20, "bold"), 
                           bg=self.bg_color, fg=self.fg_color)
        lbl_title.pack(pady=(40, 20))
        
        self.status_var = tk.StringVar(value="Checking...")
        self.lbl_status = tk.Label(self.dashboard_frame, textvariable=self.status_var, 
                                 bg=self.bg_color, fg=self.accent_color, font=("Segoe UI", 16))
        self.lbl_status.pack()
        
        self.profit_var = tk.StringVar(value="Profit: ---")
        self.lbl_profit = tk.Label(self.dashboard_frame, textvariable=self.profit_var, 
                                 bg=self.bg_color, fg="#22c55e", font=("Segoe UI", 16, "bold"))
        self.lbl_profit.pack(pady=20)
        
        btn_refresh = tk.Button(self.dashboard_frame, text="Refresh Data", command=self.update_stats,
                              bg=self.accent_color, fg="white", font=("Segoe UI", 11, "bold"),
                              relief="flat", padx=30, pady=12, cursor="hand2")
        btn_refresh.pack(pady=30)

    def setup_status_bar(self):
        self.status_bar_var = tk.StringVar(value="Initializing...")
        status_bar = tk.Label(self.root, textvariable=self.status_bar_var, bd=0, relief="flat", anchor="w",
                            bg=self.surface_color, fg="#94a3b8", font=("Segoe UI", 9), padx=10, pady=5)
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
        elif status == "Disconnected":
            self.status_bar_var.set("Bot: Disconnected")
        else:
            self.status_bar_var.set(f"Bot: {status}")
            
        if isinstance(profit, dict) and ('profit_all_percent' in profit or 'profit_all_pct' in profit):
            p = profit.get('profit_all_percent', profit.get('profit_all_pct', 0))
            self.profit_var.set(f"Total Profit: {float(p):.2f}%")
        else:
            self.profit_var.set("Total Profit: ---")

    def get_ollama_client(self):
        return self.strategy_service.ollama_client

    def start_update_loop(self):
        self.update_stats()
        # Tkinter after uses ms, UPDATE_INTERVAL is in ms from settings
        self.root.after(UPDATE_INTERVAL, self.start_update_loop)

if __name__ == "__main__":
    setup_logging()
    root = tk.Tk()
    app = SmartBotAppTK(root)
    root.mainloop()
