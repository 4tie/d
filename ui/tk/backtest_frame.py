import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog, simpledialog
import threading
import sys
import os
import json
import re
from datetime import date, timedelta

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath(os.curdir))

from utils.backtest_runner import run_backtest, download_data
from config.settings import BOT_CONFIG_PATH, APP_CONFIG_PATH, load_app_config

class CustomTimerangeDialog(tk.Toplevel):
    def __init__(self, parent, initial_tr="", bg_color="#0f172a", fg_color="#f1f5f9", accent_color="#3b82f6"):
        super().__init__(parent)
        self.title("Select Custom Timerange")
        self.configure(bg=bg_color)
        self.transient(parent)
        self.grab_set()
        self.result = None
        
        container = tk.Frame(self, bg=bg_color, padx=20, pady=20)
        container.pack()
        
        tk.Label(container, text="Start Date (YYYYMMDD):", bg=bg_color, fg=fg_color).grid(row=0, column=0, sticky="w", pady=5)
        self.start_entry = tk.Entry(container, bg="#1e293b", fg=fg_color, insertbackground=fg_color)
        self.start_entry.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(container, text="End Date (YYYYMMDD):", bg=bg_color, fg=fg_color).grid(row=1, column=0, sticky="w", pady=5)
        self.end_entry = tk.Entry(container, bg="#1e293b", fg=fg_color, insertbackground=fg_color)
        self.end_entry.grid(row=1, column=1, padx=5, pady=5)
        
        # Parse initial_tr if valid
        if initial_tr and re.match(r"^\d{8}-\d{8}$", initial_tr):
            s, e = initial_tr.split("-")
            self.start_entry.insert(0, s)
            self.end_entry.insert(0, e)
        else:
            today = date.today()
            self.start_entry.insert(0, (today - timedelta(days=30)).strftime("%Y%m%d"))
            self.end_entry.insert(0, today.strftime("%Y%m%d"))
            
        btn_frame = tk.Frame(container, bg=bg_color)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=15)
        
        tk.Button(btn_frame, text="Apply", command=self.on_apply, bg=accent_color, fg="white", padx=10).pack(side="left", padx=5)
        tk.Button(btn_frame, text="Cancel", command=self.destroy, bg="#4b5563", fg="white", padx=10).pack(side="left", padx=5)

    def on_apply(self):
        s = self.start_entry.get().strip()
        e = self.end_entry.get().strip()
        if not re.match(r"^\d{8}$", s) or not re.match(r"^\d{8}$", e):
            messagebox.showerror("Error", "Dates must be in YYYYMMDD format")
            return
        self.result = f"{s}-{e}"
        self.destroy()

class BacktestFrame(tk.Frame):
    def __init__(self, parent, main_app, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.main_app = main_app
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color
        self._running = False
        self._known_pairs = []
        
        self.setup_ui()
        self._load_defaults_from_bot_config()
        self._load_prefs_from_app_config()

    def setup_ui(self):
        container = tk.Frame(self, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Controls Group
        ctrl_group = tk.LabelFrame(container, text="Configuration", bg=self.bg_color, fg=self.fg_color)
        ctrl_group.pack(fill="x", pady=5)
        
        # Row 1: Timeframe and Dry Run Wallet
        row1 = tk.Frame(ctrl_group, bg=self.bg_color)
        row1.pack(fill="x", padx=5, pady=2)

        tk.Label(row1, text="Timeframe:", bg=self.bg_color, fg=self.fg_color).pack(side="left", padx=5)
        self.tf_var = tk.StringVar(value="5m")
        self.tf_combo = ttk.Combobox(row1, textvariable=self.tf_var, width=8, values=["1m", "5m", "15m", "30m", "1h", "4h", "1d"])
        self.tf_combo.pack(side="left", padx=5)
        self.tf_combo.bind("<<ComboboxSelected>>", self._schedule_save_prefs)

        tk.Label(row1, text="Dry Run Wallet:", bg=self.bg_color, fg=self.fg_color).pack(side="left", padx=5)
        self.balance_var = tk.StringVar(value="1000.0")
        self.balance_entry = tk.Entry(row1, textvariable=self.balance_var, width=12, bg="#1e293b", fg=self.fg_color, insertbackground=self.fg_color)
        self.balance_entry.pack(side="left", padx=5)
        self.balance_entry.bind("<FocusOut>", self._schedule_save_prefs)

        # Row 2: Timerange Selection
        row2 = tk.Frame(ctrl_group, bg=self.bg_color)
        row2.pack(fill="x", padx=5, pady=2)

        tk.Label(row2, text="Timerange:", bg=self.bg_color, fg=self.fg_color).pack(side="left", padx=5)
        self.tr_var = tk.StringVar(value="")
        self.tr_combo = ttk.Combobox(row2, textvariable=self.tr_var, width=40)
        self._add_tr_presets()
        self.tr_combo.pack(side="left", padx=5, fill="x", expand=True)
        self.tr_combo.bind("<<ComboboxSelected>>", self._schedule_save_prefs)
        self.tr_combo.bind("<FocusOut>", self._schedule_save_prefs)
        
        self.btn_tr_custom = tk.Button(row2, text="Custom...", command=self.on_custom_tr, bg="#4b5563", fg="white", relief="flat", padx=5)
        self.btn_tr_custom.pack(side="left", padx=5)

        # Row 3: Pairs Selection
        row3 = tk.Frame(ctrl_group, bg=self.bg_color)
        row3.pack(fill="x", padx=5, pady=2)

        tk.Label(row3, text="Pairs:", bg=self.bg_color, fg=self.fg_color).pack(side="left", padx=5)
        self.pairs_var = tk.StringVar(value="")
        self.pairs_combo = ttk.Combobox(row3, textvariable=self.pairs_var, width=60)
        self.pairs_combo.pack(side="left", padx=5, fill="x", expand=True)
        self.pairs_combo.bind("<<ComboboxSelected>>", self._schedule_save_prefs)
        self.pairs_combo.bind("<FocusOut>", self._schedule_save_prefs)

        # Action Buttons
        btn_frame = tk.Frame(container, bg=self.bg_color)
        btn_frame.pack(fill="x", pady=5)

        self.btn_run = tk.Button(btn_frame, text="Run Backtest", command=self.on_run,
                               bg=self.accent_color, fg="white", font=("Arial", 10, "bold"), relief="flat", padx=10)
        self.btn_run.pack(side="right", padx=5)

        self.btn_download = tk.Button(btn_frame, text="Download Data", command=self.on_download,
                                    bg="#6366f1", fg="white", relief="flat", padx=10)
        self.btn_download.pack(side="right", padx=5)

        self.btn_load = tk.Button(btn_frame, text="Load Strategy File", command=self.on_load_file,
                                bg="#4b5563", fg="white", relief="flat", padx=10)
        self.btn_load.pack(side="left", padx=5)
        
        # Candle Completeness Widget
        self.lbl_candle = tk.Label(container, text="Data Metadata: Not Checked", 
                                  bg="#1e293b", fg="#94a3b8", font=("Arial", 10, "bold"),
                                  padx=10, pady=5, relief="solid", bd=1)
        self.lbl_candle.pack(fill="x", padx=5, pady=5)
        
        # Code and Results
        tk.Label(container, text="Strategy Code:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=5)
        self.txt_code = scrolledtext.ScrolledText(container, height=10, bg="#1e293b", fg=self.fg_color, insertbackground=self.fg_color)
        self.txt_code.pack(fill="x", padx=5, pady=5)
        
        # Results Summary Text
        tk.Label(container, text="Results Summary:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=5)
        self.txt_results = scrolledtext.ScrolledText(container, bg="#0f172a", fg="#f1f5f9", state="disabled", height=12, font=("Consolas", 10))
        self.txt_results.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Results Tags
        self.txt_results.tag_configure("header", foreground="#3b82f6", font=("Consolas", 10, "bold"))
        self.txt_results.tag_configure("profit", foreground="#22c55e", font=("Consolas", 10, "bold"))
        self.txt_results.tag_configure("loss", foreground="#ef4444", font=("Consolas", 10, "bold"))
        self.txt_results.tag_configure("info", foreground="#94a3b8")
        self.txt_results.tag_configure("metric", foreground="#fbbf24", font=("Consolas", 10, "bold"))

    def on_custom_tr(self):
        current = self.tr_var.get()
        match = re.search(r"(\d{8}-\d{8})", current)
        initial = match.group(1) if match else ""
        
        dlg = CustomTimerangeDialog(self, initial, self.bg_color, self.fg_color, self.accent_color)
        self.wait_window(dlg)
        if dlg.result:
            self.tr_var.set(dlg.result)
            self._schedule_save_prefs()

    def _add_tr_presets(self):
        today = date.today()
        presets = []
        for days in [7, 30, 90, 180, 365]:
            start = today - timedelta(days=days)
            tr = f"{start.strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}"
            presets.append(f"Last {days}d ({tr})")
        
        ytd_start = date(today.year, 1, 1)
        ytd = f"{ytd_start.strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}"
        presets.append(f"YTD ({ytd})")
        
        self.tr_combo['values'] = presets
        self._load_timerange_history()

    def _load_timerange_history(self):
        try:
            out_dir = os.path.join(os.getcwd(), "data", "backtest_results")
            if not os.path.isdir(out_dir):
                return
            
            timeranges = set()
            for name in os.listdir(out_dir):
                if name.endswith('.json'):
                    path = os.path.join(out_dir, name)
                    try:
                        with open(path, 'r') as f:
                            data = json.load(f)
                            tr = data.get('metadata', {}).get('timerange') or data.get('timerange')
                            if tr: timeranges.add(tr)
                    except: continue
            
            current_values = list(self.tr_combo['values'])
            for tr in sorted(timeranges, reverse=True):
                if tr not in str(current_values):
                    current_values.append(tr)
            self.tr_combo['values'] = current_values
        except: pass

    def _load_defaults_from_bot_config(self):
        try:
            with open(BOT_CONFIG_PATH, 'r') as f:
                cfg = json.load(f)
            if 'timeframe' in cfg:
                self.tf_var.set(cfg['timeframe'])
            if 'available_capital' in cfg:
                self.balance_var.set(str(cfg['available_capital']))
            elif 'stake_amount' in cfg:
                # Fallback to stake amount if capital not explicitly defined
                self.balance_var.set(str(cfg['stake_amount']))

            whitelist = cfg.get('exchange', {}).get('pair_whitelist', [])
            if whitelist:
                self._known_pairs = whitelist
                joined = ",".join(whitelist)
                self.pairs_combo['values'] = [joined] + whitelist
                if not self.pairs_var.get():
                    self.pairs_var.set(joined)
        except: pass

    def _load_prefs_from_app_config(self):
        try:
            cfg = load_app_config()
            bt = cfg.get('backtest', {})
            if bt.get('timeframe'): self.tf_var.set(bt['timeframe'])
            if bt.get('dry_run_wallet'): self.balance_var.set(str(bt['dry_run_wallet']))
            elif bt.get('wallet_balance'): self.balance_var.set(str(bt['wallet_balance']))
            if bt.get('pairs'): self.pairs_var.set(bt['pairs'])
            if bt.get('timerange'): self.tr_var.set(bt['timerange'])
        except: pass

    def _schedule_save_prefs(self, event=None):
        def _save():
            try:
                cfg = load_app_config()
                if 'backtest' not in cfg: cfg['backtest'] = {}
                cfg['backtest']['timeframe'] = self.tf_var.get()
                cfg['backtest']['dry_run_wallet'] = self.balance_var.get()
                cfg['backtest']['pairs'] = self.pairs_var.get()
                
                tr_val = self.tr_var.get()
                match = re.search(r"(\d{8}-\d{8})", tr_val)
                cfg['backtest']['timerange'] = match.group(1) if match else tr_val
                
                with open(APP_CONFIG_PATH, 'w') as f:
                    json.dump(cfg, f, indent=2)
            except: pass
        threading.Thread(target=_save, daemon=True).start()

    def on_load_file(self):
        path = filedialog.askopenfilename(filetypes=[("Python Files", "*.py")])
        if path:
            try:
                with open(path, 'r') as f:
                    self.txt_code.delete("1.0", "end")
                    self.txt_code.insert("1.0", f.read())
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {e}")

    def on_download(self):
        self.btn_download.config(state="disabled", text="Downloading...")
        tr = self.tr_var.get()
        match = re.search(r"(\d{8}-\d{8})", tr)
        timerange = match.group(1) if match else tr
        
        def _task():
            try:
                download_data(BOT_CONFIG_PATH, timerange, self.tf_var.get(), self.pairs_var.get())
                self.after(0, lambda: self.lbl_candle.config(text=f"Data Metadata: Downloaded {timerange or 'Full'}", fg="#3b82f6", bg="#172554"))
                self.after(0, lambda: messagebox.showinfo("Success", "Data download complete"))
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
            finally:
                self.after(0, lambda: self.btn_download.config(state="normal", text="Download Data"))
        
        threading.Thread(target=_task, daemon=True).start()

    def on_run(self):
        code = self.txt_code.get("1.0", "end-1c").strip()
        if not code:
            messagebox.showwarning("Warning", "Please paste strategy code.")
            return
            
        # Store for analysis frame
        try:
            if hasattr(self, 'main_app') and self.main_app:
                self.main_app.last_backtest_strategy = code
        except Exception as e:
            import logging
            logging.warning(f"Could not store last backtest strategy: {e}")

        self.btn_run.config(state="disabled", text="Running...")
        self.txt_results.config(state="normal")
        self.txt_results.delete("1.0", "end")
        self.txt_results.insert("1.0", "Backtest started...\n")
        self.txt_results.config(state="disabled")
        
        tr = self.tr_var.get()
        match = re.search(r"(\d{8}-\d{8})", tr)
        timerange = match.group(1) if match else tr

        def _task():
            try:
                # We can inject wallet balance into the backtest call if needed, 
                # but currently run_backtest uses BOT_CONFIG_PATH. 
                # We use the UI balance as an override preference.
                res = run_backtest(
                    strategy_code=code, 
                    config_path=BOT_CONFIG_PATH, 
                    timeframe=self.tf_var.get(), 
                    timerange=timerange,
                    pairs=self.pairs_var.get()
                )
                # Store results for analysis frame
                try:
                    if hasattr(self, 'main_app') and self.main_app:
                        self.main_app.last_backtest_results = res
                except Exception as e:
                    import logging
                    logging.warning(f"Could not store last backtest results: {e}")

                self.after(0, lambda: self._apply_results(res))
                
                # Auto-load into analysis frame
                try:
                    tabs = self.master.master
                    for i in range(tabs.index("end")):
                        if tabs.tab(i, "text") == "AI Analysis":
                            analysis_frame = tabs.winfo_children()[i]
                            if hasattr(analysis_frame, 'on_load_last_backtest'):
                                self.after(0, analysis_frame.on_load_last_backtest)
                            break
                except Exception:
                    pass
            except Exception as e:
                error_msg = str(e)
                self.after(0, lambda msg=error_msg: messagebox.showerror("Error", msg))
            finally:
                self.after(0, lambda: self.btn_run.config(state="normal", text="Run Backtest"))
        
        threading.Thread(target=_task, daemon=True).start()

    def _apply_results(self, res):
        self.txt_results.config(state="normal")
        self.txt_results.delete("1.0", "end")
        
        if isinstance(res, dict):
            # Update Metadata Widget
            meta = res.get('data', {}).get('metadata', {})
            if meta:
                tr = meta.get('timerange', 'Unknown')
                self.lbl_candle.config(text=f"Data Metadata: Timerange {tr} | Status: Success", 
                                      fg="#22c55e", bg="#064e3b")
            
            self.txt_results.insert("end", f"=== Backtest Results ===\n", "header")
            self.txt_results.insert("end", f"Strategy: {res.get('strategy_class')}\n", "info")
            
            stdout = res.get('stdout', '')
            
            # Extract key metrics if available in stdout
            metrics = {
                "Total Profit %": r"Total profit %:\s+([\d\.-]+)%",
                "Win Rate %": r"Win rate %:\s+([\d\.-]+)%",
                "Drawdown": r"Drawdown:\s+([\d\.-]+)%",
            }
            
            for label, pattern in metrics.items():
                match = re.search(pattern, stdout)
                if match:
                    val = match.group(1)
                    try:
                        f_val = float(val)
                        if label == "Drawdown":
                            tag = "loss" if f_val > 5 else "info"
                        else:
                            tag = "profit" if f_val > 0 else "loss"
                    except:
                        tag = "info"
                    
                    self.txt_results.insert("end", f"{label:15}: ", "info")
                    self.txt_results.insert("end", f"{val}%\n", tag)

            self.txt_results.insert("end", "\n--- Full Output ---\n", "header")
            self.txt_results.insert("end", stdout, "info")
            
            stderr = res.get('stderr', '')
            if stderr:
                self.txt_results.insert("end", "\n--- Errors ---\n", "loss")
                self.txt_results.insert("end", stderr, "info")
        else:
            self.txt_results.insert("1.0", str(res))
            
        self.txt_results.config(state="disabled")
