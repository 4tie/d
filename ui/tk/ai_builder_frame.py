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

        template_frame = tk.Frame(self, bg=self.bg_color)
        template_frame.pack(fill="x", padx=10, pady=5)
        tk.Label(template_frame, text="Templates:", bg=self.bg_color, fg=self.fg_color).pack(side="left")
        self.template_var = tk.StringVar(value="Select a template...")
        self.template_combo = ttk.Combobox(template_frame, textvariable=self.template_var, state="readonly", width=40)
        self.template_combo['values'] = [
            "Select a template...",
            "Simple RSI Strategy",
            "EMA Crossover",
            "Bollinger Bands Mean Reversion",
            "MACD with Volume Confirmation"
        ]
        self.template_combo.bind("<<ComboboxSelected>>", self._on_template_selected)
        self.template_combo.pack(side="left", padx=5)
        
        btn_frame = tk.Frame(self, bg=self.bg_color)
        btn_frame.pack(fill="x", padx=10)

    def _on_template_selected(self, event):
        text = self.template_var.get()
        templates = {
            "Simple RSI Strategy": "Create a strategy that buys when RSI is below 30 and sells when RSI is above 70. Use 5m timeframe.",
            "EMA Crossover": "Buy when the 20-period EMA crosses above the 50-period EMA. Sell when it crosses below.",
            "Bollinger Bands Mean Reversion": "Buy when price touches the lower Bollinger Band. Sell when it touches the upper band.",
            "MACD with Volume Confirmation": "Buy when MACD line crosses above the signal line and volume is above the 20-period average."
        }
        if text in templates:
            self.txt_prompt.delete("1.0", "end")
            self.txt_prompt.insert("1.0", templates[text])
        
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
                code = self.main_app.strategy_service.generate_strategy(prompt)
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
        
        try:
            path = self.main_app.strategy_service.save_strategy_code(code)
            messagebox.showinfo("Success", f"Strategy saved to {path}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
