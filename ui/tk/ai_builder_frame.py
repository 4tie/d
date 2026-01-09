import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import sys
import os

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath(os.curdir))

class AIBuilderFrame(tk.Frame):
    def __init__(self, parent, main_app, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.main_app = main_app
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color
        
        self.setup_ui()

    def setup_ui(self):
        tk.Label(self, text="Describe your strategy (e.g., 'Buy when RSI is < 30'):", 
                 bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=10, pady=(10, 0))
        
        self.txt_prompt = tk.Text(self, height=4, bg="#1e293b", fg=self.fg_color, insertbackground="white")
        self.txt_prompt.pack(fill="x", padx=10, pady=5)
        
        btn_frame = tk.Frame(self, bg=self.bg_color)
        btn_frame.pack(fill="x", padx=10)
        
        self.btn_generate = tk.Button(btn_frame, text="Generate Strategy", command=self.on_generate,
                                    bg="#6200ea", fg="white", font=("Arial", 10, "bold"))
        self.btn_generate.pack(side="left", pady=5)
        
        tk.Label(self, text="Code Preview:", bg=self.bg_color, fg=self.fg_color).pack(anchor="w", padx=10, pady=(10, 0))
        self.txt_code = scrolledtext.ScrolledText(self, bg="#1e293b", fg=self.fg_color, insertbackground="white")
        self.txt_code.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.btn_save = tk.Button(self, text="Save Strategy", command=self.on_save,
                                bg=self.accent_color, fg="white")
        self.btn_save.pack(pady=10)

    def on_generate(self):
        prompt = self.txt_prompt.get("1.0", "end-1c").strip()
        if not prompt:
            messagebox.showwarning("Warning", "Please enter a description.")
            return
            
        self.btn_generate.config(state="disabled", text="Generating...")
        
        def _task():
            try:
                # Mocking AI call for now as we'd need to link with StrategyService properly
                # In real app, we'd call strategy_service.generate_strategy(prompt)
                code = f"# Generated strategy based on: {prompt}\n# [Mock Code]\nfrom freqtrade.strategy import IStrategy\nclass AIStrategy(IStrategy):\n    pass"
                self.after(0, lambda: self._apply_code(code))
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Error", str(e)))
            finally:
                self.after(0, lambda: self.btn_generate.config(state="normal", text="Generate Strategy"))
        
        threading.Thread(target=_task, daemon=True).start()

    def _apply_code(self, code):
        self.txt_code.delete("1.0", "end")
        self.txt_code.insert("1.0", code)

    def on_save(self):
        code = self.txt_code.get("1.0", "end-1c").strip()
        if not code:
            messagebox.showwarning("Warning", "No code to save.")
            return
        
        # In real app, call main_app.strategy_service.save_strategy_code(code)
        messagebox.showinfo("Success", "Strategy saved to strategies folder (Mock).")
