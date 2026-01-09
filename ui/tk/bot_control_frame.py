import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import json
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath(os.curdir))

from config.settings import BOT_CONFIG_PATH

class BotControlFrame(tk.Frame):
    def __init__(self, parent, client, threadpool, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.client = client
        self.threadpool = threadpool
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color
        
        self.setup_ui()
        self.load_current_config_async()

    def setup_ui(self):
        # Configuration Section
        config_frame = tk.LabelFrame(self, text="Bot Configuration", bg=self.bg_color, fg=self.fg_color, font=("Arial", 12, "bold"))
        config_frame.pack(fill="x", padx=10, pady=10)

        # Labels and Entries
        fields = [
            ("Strategy:", "strategy_var"),
            ("Timeframe:", "timeframe_var"),
            ("Pairs:", "pairs_var")
        ]
        
        for i, (label_text, var_name) in enumerate(fields):
            lbl = tk.Label(config_frame, text=label_text, bg=self.bg_color, fg=self.fg_color)
            lbl.grid(row=i, column=0, sticky="e", padx=5, pady=5)
            var = tk.StringVar()
            setattr(self, var_name, var)
            ent = tk.Entry(config_frame, textvariable=var, width=50)
            ent.grid(row=i, column=1, sticky="w", padx=5, pady=5)

        lbl_max = tk.Label(config_frame, text="Max open trades:", bg=self.bg_color, fg=self.fg_color)
        lbl_max.grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.max_trades_var = tk.IntVar(value=0)
        self.max_trades_spin = tk.Spinbox(config_frame, from_=0, to=999, textvariable=self.max_trades_var)
        self.max_trades_spin.grid(row=3, column=1, sticky="w", padx=5, pady=5)

        btn_frame = tk.Frame(config_frame, bg=self.bg_color)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)

        self.btn_reload = tk.Button(btn_frame, text="Reload Config", command=self.reload_bot_config_async,
                                  bg=self.accent_color, fg="white")
        self.btn_reload.pack(side="left", padx=5)
        
        self.btn_save = tk.Button(btn_frame, text="Save & Reload", command=self.save_and_reload_async,
                                bg="#22c55e", fg="white")
        self.btn_save.pack(side="left", padx=5)

        # Trades Table Section
        trades_frame = tk.LabelFrame(self, text="Open Trades", bg=self.bg_color, fg=self.fg_color, font=("Arial", 12, "bold"))
        trades_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.btn_refresh_trades = tk.Button(trades_frame, text="Refresh Open Trades", command=self.refresh_open_trades_async,
                                          bg=self.accent_color, fg="white")
        self.btn_refresh_trades.pack(pady=5)

        columns = ("Pair", "Type", "Amount", "Open Rate", "Current Rate", "Profit %")
        self.tree = ttk.Treeview(trades_frame, columns=columns, show="headings")
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)
        self.tree.pack(fill="both", expand=True)

    def load_current_config_async(self):
        def _task():
            try:
                with open(BOT_CONFIG_PATH, 'r') as f:
                    cfg = json.load(f)
                self.after(0, lambda: self._apply_config(cfg))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to load config: {err_msg}"))
        threading.Thread(target=_task, daemon=True).start()

    def _apply_config(self, cfg):
        self.strategy_var.set(cfg.get('strategy', ''))
        self.timeframe_var.set(cfg.get('timeframe', ''))
        ex = cfg.get('exchange', {})
        self.pairs_var.set(", ".join(ex.get('pair_whitelist', [])))
        self.max_trades_var.set(cfg.get('max_open_trades', 0))

    def save_and_reload_async(self):
        strategy = self.strategy_var.get()
        timeframe = self.timeframe_var.get()
        pairs = [p.strip() for p in self.pairs_var.get().split(',') if p.strip()]
        max_trades = self.max_trades_var.get()

        def _task():
            try:
                with open(BOT_CONFIG_PATH, 'r') as f:
                    cfg = json.load(f)
                cfg['strategy'] = strategy
                cfg['timeframe'] = timeframe
                cfg['max_open_trades'] = max_trades
                if 'exchange' not in cfg: cfg['exchange'] = {}
                cfg['exchange']['pair_whitelist'] = pairs
                with open(BOT_CONFIG_PATH, 'w') as f:
                    json.dump(cfg, f, indent=4)
                self.after(0, lambda: messagebox.showinfo("Success", "Config saved. Reloading bot..."))
                self.reload_bot_config_async()
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to save config: {err_msg}"))
        threading.Thread(target=_task, daemon=True).start()

    def reload_bot_config_async(self):
        def _task():
            try:
                res = self.client.reload_config()
                self.after(0, lambda: messagebox.showinfo("Reload", f"Bot reload triggered: {res}"))
            except Exception as e:
                err_msg = str(e)
                self.after(0, lambda: messagebox.showerror("Error", f"Reload failed: {err_msg}"))
        threading.Thread(target=_task, daemon=True).start()

    def refresh_open_trades_async(self):
        def _task():
            try:
                trades = self.client.get_open_trades()
                self.after(0, lambda: self._apply_trades(trades))
            except Exception as e:
                print(f"Failed to fetch trades: {e}")
        threading.Thread(target=_task, daemon=True).start()

    def _apply_trades(self, trades):
        for item in self.tree.get_children():
            self.tree.delete(item)
        if isinstance(trades, list):
            for t in trades:
                self.tree.insert("", "end", values=(
                    t.get('pair'), t.get('trade_type'), t.get('amount'),
                    t.get('open_rate'), t.get('current_rate'), f"{t.get('profit_pct', 0):.4f}"
                ))
