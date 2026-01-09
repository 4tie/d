import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import html
from datetime import datetime

class ChatFrame(tk.Frame):
    def __init__(self, parent, main_app, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.main_app = main_app
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color
        
        self._history = []
        self._running = False
        
        self.setup_ui()
        
    def setup_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        
        # Chat display area
        self.chat_view = scrolledtext.ScrolledText(
            self, bg="#121212", fg="#e0e0e0", 
            font=("Segoe UI", 10), wrap=tk.WORD,
            padx=10, pady=10, state="disabled"
        )
        self.chat_view.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # Tags for styling
        self.chat_view.tag_configure("user", foreground="#4a8cff", font=("Segoe UI", 10, "bold"))
        self.chat_view.tag_configure("assistant", foreground="#4caf50", font=("Segoe UI", 10, "bold"))
        self.chat_view.tag_configure("system", foreground="#888888", font=("Segoe UI", 10, "italic"))
        self.chat_view.tag_configure("timestamp", foreground="#666666", font=("Segoe UI", 8))
        self.chat_view.tag_configure("content", foreground="#e0e0e0", font=("Segoe UI", 10))
        
        # Input area
        input_frame = tk.Frame(self, bg=self.bg_color)
        input_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)
        
        btn_action_frame = tk.Frame(input_frame, bg=self.bg_color)
        btn_action_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        
        self.btn_include = tk.Button(
            btn_action_frame, text="Include Last Results", command=self.include_last_results,
            bg="#5c6bc0", fg="white", font=("Segoe UI", 9),
            relief="flat", padx=10
        )
        self.btn_include.pack(side="left")
        
        self.input_entry = tk.Entry(
            input_frame, bg="#1e1e1e", fg="#ffffff",
            insertbackground="white", font=("Segoe UI", 10),
            relief="flat", highlightthickness=1, highlightbackground="#444444"
        )
        self.input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5), ipady=8)
        self.input_entry.bind("<Return>", lambda e: self.send())
        
        self.btn_send = tk.Button(
            input_frame, text="Send", command=self.send,
            bg=self.accent_color, fg="white", font=("Segoe UI", 10, "bold"),
            relief="flat", padx=15, pady=5
        )
        self.btn_send.grid(row=0, column=1, sticky="e")
        
        self._append_message("system", "Chat is ready. Ask questions about strategy logic, backtests, or improvements.")

    def _append_message(self, role, text):
        ts = datetime.now().strftime("%H:%M")
        self.chat_view.config(state="normal")
        
        # Add spacing between messages
        if self.chat_view.get("1.0", "end-1c"):
            self.chat_view.insert("end", "\n\n")
            
        if role == "user":
            self.chat_view.insert("end", f"You · {ts}\n", ("user", "timestamp"))
        elif role == "assistant":
            self.chat_view.insert("end", f"AI · {ts}\n", ("assistant", "timestamp"))
        else:
            self.chat_view.insert("end", f"System · {ts}\n", ("system", "timestamp"))
            
        self.chat_view.insert("end", text, "content")
        self.chat_view.see("end")
        self.chat_view.config(state="disabled")
        
        self._history.append({"role": role, "content": text})

    def send(self):
        if self._running:
            return
            
        text = self.input_entry.get().strip()
        if not text:
            return
            
        self.input_entry.delete(0, tk.END)
        self._append_message("user", text)
        
        ollama = self.main_app.get_ollama_client()
        if not ollama or not ollama.is_available():
            self._append_message("system", "Error: Ollama is not available.")
            return
            
        self._set_running(True)
        
        def _task():
            try:
                # Simple prompt build similar to PyQt6 implementation
                prompt = f"SYSTEM: You are a Freqtrade expert assistant.\n\nUSER: {text}\n\nASSISTANT:"
                response = ollama.generate_text(prompt)
                self.after(0, lambda: self._append_message("assistant", response))
            except Exception as e:
                self.after(0, lambda: self._append_message("system", f"Error: {e}"))
            finally:
                self.after(0, lambda: self._set_running(False))
                
        threading.Thread(target=_task, daemon=True).start()

    def include_last_results(self):
        strategy = getattr(self.main_app, 'last_backtest_strategy', None)
        results = getattr(self.main_app, 'last_backtest_results', None)
        
        if not strategy:
            self._append_message("system", "No recent backtest found to include.")
            return
            
        context = f"\n\n[CONTEXT: Last Backtest Results]\n"
        if isinstance(results, dict):
            context += f"Strategy: {results.get('strategy_class')}\n"
            context += f"Stats: {results.get('stdout', '')[:500]}...\n"
        
        context += f"\n[STRATEGY CODE]\n{strategy}\n"
        
        self.input_entry.insert(tk.END, "Analyze this strategy and results: " + context)
        self._append_message("system", "Included strategy and backtest results in input.")

    def _set_running(self, running):
        self._running = running
        self.btn_send.config(state="disabled" if running else "normal")
        self.input_entry.config(state="disabled" if running else "normal")
