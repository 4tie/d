import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.abspath(os.curdir))

from config.settings import APP_CONFIG_PATH, load_app_config

class SettingsFrame(tk.Frame):
    def __init__(self, parent, main_app, bg_color, fg_color, accent_color):
        super().__init__(parent, bg=bg_color)
        self.main_app = main_app
        self.bg_color = bg_color
        self.fg_color = fg_color
        self.accent_color = accent_color
        
        self.setup_ui()
        self.load_from_disk()

    def setup_ui(self):
        container = tk.Frame(self, bg=self.bg_color)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        # Freqtrade Settings
        ft_group = tk.LabelFrame(container, text="Freqtrade API", bg=self.bg_color, fg=self.fg_color)
        ft_group.pack(fill="x", pady=10)
        
        tk.Label(ft_group, text="URL:", bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, padx=5, pady=5)
        self.url_var = tk.StringVar()
        tk.Entry(ft_group, textvariable=self.url_var, width=40).grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(ft_group, text="User:", bg=self.bg_color, fg=self.fg_color).grid(row=1, column=0, padx=5, pady=5)
        self.user_var = tk.StringVar()
        tk.Entry(ft_group, textvariable=self.user_var, width=40).grid(row=1, column=1, padx=5, pady=5)
        
        tk.Label(ft_group, text="Pass:", bg=self.bg_color, fg=self.fg_color).grid(row=2, column=0, padx=5, pady=5)
        self.pass_var = tk.StringVar()
        tk.Entry(ft_group, textvariable=self.pass_var, width=40, show="*").grid(row=2, column=1, padx=5, pady=5)

        # Ollama Settings
        ol_group = tk.LabelFrame(container, text="Ollama AI", bg=self.bg_color, fg=self.fg_color)
        ol_group.pack(fill="x", pady=10)
        
        tk.Label(ol_group, text="URL:", bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, padx=5, pady=5)
        self.ol_url_var = tk.StringVar()
        tk.Entry(ol_group, textvariable=self.ol_url_var, width=40).grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(ol_group, text="Model:", bg=self.bg_color, fg=self.fg_color).grid(row=1, column=0, padx=5, pady=5)
        self.ol_model_var = tk.StringVar()
        tk.Entry(ol_group, textvariable=self.ol_model_var, width=40).grid(row=1, column=1, padx=5, pady=5)

        btn_save = tk.Button(container, text="Save & Apply Settings", command=self.save_settings,
                           bg=self.accent_color, fg="white", font=("Arial", 10, "bold"))
        btn_save.pack(pady=20)

    def load_from_disk(self):
        try:
            cfg = load_app_config()
            api = cfg.get("api", {})
            ollama = cfg.get("ollama", {})
            self.url_var.set(api.get("freqtrade_url", ""))
            self.user_var.set(api.get("user", ""))
            self.pass_var.set(api.get("password", ""))
            self.ol_url_var.set(ollama.get("base_url", "http://localhost:11434"))
            self.ol_model_var.set(ollama.get("model", "llama3"))
        except Exception as e:
            print(f"Error loading settings: {e}")

    def save_settings(self):
        try:
            cfg = load_app_config()
            cfg["api"] = {
                "freqtrade_url": self.url_var.get(),
                "user": self.user_var.get(),
                "password": self.pass_var.get()
            }
            cfg["ollama"]["base_url"] = self.ol_url_var.get()
            cfg["ollama"]["model"] = self.ol_model_var.get()
            
            with open(APP_CONFIG_PATH, 'w') as f:
                json.dump(cfg, f, indent=2)
            
            messagebox.showinfo("Success", "Settings saved successfully.")
            # Update main app components
            self.main_app.client.update_settings(cfg["api"]["freqtrade_url"], cfg["api"]["user"], cfg["api"]["password"])
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
