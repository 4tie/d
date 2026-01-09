import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import os
import json
import difflib

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath(os.curdir))

class ComparingFrame(tk.Frame):
    def __init__(self, parent, main_app, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.main_app = main_app
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color
        
        self.setup_ui()
        
    def setup_ui(self):
        # Header
        header = tk.Label(self, text="Strategy Comparison & Version Control", 
                         font=("Arial", 16, "bold"), bg=self.bg_color, fg=self.accent_color)
        header.pack(pady=10)

        # Paned Window for split view
        self.paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        self.paned.pack(expand=True, fill="both", padx=10, pady=5)
        
        # Table Frame
        table_frame = tk.Frame(self.paned, bg=self.bg_color)
        self.paned.add(table_frame, weight=1)
        
        columns = ("ID", "Type", "Strategy", "Profit %", "Trades")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=100)
            
        self.tree.pack(expand=True, fill="both")
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_changed)
        
        # Diff Preview Frame
        preview_frame = tk.Frame(self.paned, bg=self.bg_color)
        self.paned.add(preview_frame, weight=1)
        
        tk.Label(preview_frame, text="Visual Diff (Current AIStrategy.py vs Selected):", bg=self.bg_color, fg=self.fg_color).pack(anchor="w")
        self.diff_view = scrolledtext.ScrolledText(preview_frame, bg="#1e293b", fg=self.fg_color, font=("Courier", 10))
        self.diff_view.pack(expand=True, fill="both")
        self.diff_view.tag_configure("plus", background="#166534", foreground="#f1f5f9")
        self.diff_view.tag_configure("minus", background="#991b1b", foreground="#f1f5f9")
        self.diff_view.tag_configure("normal", foreground="#94a3b8")
        self.diff_view.config(state="disabled")
        
        # Action Buttons
        btn_frame = tk.Frame(self, bg=self.bg_color)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        self.btn_refresh = tk.Button(btn_frame, text="Refresh Results", command=self.load_results,
                                   bg="#475569", fg="white", padx=10)
        self.btn_refresh.pack(side="left")
        
        self.btn_restore = tk.Button(btn_frame, text="Restore to this Strategy", command=self.on_restore_clicked,
                                   bg="#ef4444", fg="white", font=("Arial", 10, "bold"), padx=20)
        self.btn_restore.pack(side="right")
        self.btn_restore.config(state="disabled")
        
        self.load_results()

    def load_results(self):
        def _task():
            try:
                if not hasattr(self.main_app, 'strategy_service'):
                    return
                
                runs = self.main_app.strategy_service.performance_store.get_recent_runs(limit=20)
                self.after(0, lambda: self._apply_results(runs))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", f"Failed to load results: {e}"))
        
        threading.Thread(target=_task, daemon=True).start()

    def _apply_results(self, runs):
        self.tree.delete(*self.tree.get_children())
        self.results_data = {}
        
        for run in runs:
            run_id = str(run.get("id", ""))
            self.results_data[run_id] = run
            
            summary = run.get("backtest_summary", {})
            profit = summary.get("total_profit_pct", 0)
            trades = summary.get("total_trades", 0)
            
            self.tree.insert("", "end", iid=run_id, values=(
                run_id,
                run.get("run_type", ""),
                run.get("strategy_class", "N/A"),
                f"{profit:.2f}%",
                str(trades)
            ))

    def _on_selection_changed(self, event):
        selected = self.tree.selection()
        if not selected:
            self.btn_restore.config(state="disabled")
            self.diff_view.config(state="normal")
            self.diff_view.delete("1.0", "end")
            self.diff_view.config(state="disabled")
            return
            
        run_id = selected[0]
        run = self.results_data.get(run_id)
        
        if run:
            self._show_diff(run.get("strategy_code", ""))
            self.btn_restore.config(state="normal")

    def _show_diff(self, new_code):
        self.diff_view.config(state="normal")
        self.diff_view.delete("1.0", "end")
        
        current_code = ""
        path = "user_data/strategies/AIStrategy.py"
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    current_code = f.read()
            except Exception:
                pass
        
        diff = difflib.ndiff(current_code.splitlines(), new_code.splitlines())
        
        for line in diff:
            if line.startswith('+'):
                self.diff_view.insert("end", line + "\n", "plus")
            elif line.startswith('-'):
                self.diff_view.insert("end", line + "\n", "minus")
            elif line.startswith('?'):
                continue
            else:
                self.diff_view.insert("end", line + "\n", "normal")
        
        self.diff_view.config(state="disabled")

    def on_restore_clicked(self):
        selected = self.tree.selection()
        if not selected:
            return
            
        run_id = selected[0]
        run = self.results_data.get(run_id)
        
        if not run:
            return
            
        code = run.get("strategy_code")
        if not code:
            messagebox.showwarning("Error", "No code found for this record.")
            return
            
        if messagebox.askyesno("Confirm Restore", "This will overwrite AIStrategy.py and create a git commit. Continue?"):
            try:
                self.main_app.strategy_service.save_strategy_code(code, "AIStrategy.py")
                import subprocess
                subprocess.run(["git", "add", "user_data/strategies/AIStrategy.py"], capture_output=True)
                subprocess.run(["git", "commit", "-m", f"Restored strategy from run {run_id}"], capture_output=True)
                messagebox.showinfo("Success", "Strategy restored and committed.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to restore: {e}")
