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

        # Advanced AI Settings
        adv_group = tk.LabelFrame(container, text="Advanced AI Settings", bg=self.bg_color, fg=self.fg_color)
        adv_group.pack(fill="x", pady=10)

        tk.Label(adv_group, text="Temperature:", bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, padx=5, pady=5)
        self.temp_var = tk.DoubleVar(value=0.7)
        tk.Spinbox(adv_group, from_=0.0, to=2.0, increment=0.05, textvariable=self.temp_var, width=10).grid(row=0, column=1, sticky="w", padx=5, pady=5)

        tk.Label(adv_group, text="Top_p:", bg=self.bg_color, fg=self.fg_color).grid(row=1, column=0, padx=5, pady=5)
        self.top_p_var = tk.DoubleVar(value=0.9)
        tk.Spinbox(adv_group, from_=0.0, to=1.0, increment=0.05, textvariable=self.top_p_var, width=10).grid(row=1, column=1, sticky="w", padx=5, pady=5)

        tk.Label(adv_group, text="Num_predict:", bg=self.bg_color, fg=self.fg_color).grid(row=2, column=0, padx=5, pady=5)
        self.num_predict_var = tk.IntVar(value=2048)
        tk.Spinbox(adv_group, from_=16, to=8192, textvariable=self.num_predict_var, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Task Models
        task_group = tk.LabelFrame(container, text="Task Models (Ensemble)", bg=self.bg_color, fg=self.fg_color)
        task_group.pack(fill="x", pady=10)

        self.task_vars = {}
        tasks = [
            ("Strategy Gen:", "strategy_generation"),
            ("Strategy Analysis:", "strategy_analysis"),
            ("Risk Assessment:", "risk_assessment"),
            ("Chat:", "chat")
        ]
        for i, (lbl_txt, key) in enumerate(tasks):
            tk.Label(task_group, text=lbl_txt, bg=self.bg_color, fg=self.fg_color).grid(row=i, column=0, padx=5, pady=2)
            var = tk.StringVar()
            self.task_vars[key] = var
            tk.Entry(task_group, textvariable=var, width=40).grid(row=i, column=1, padx=5, pady=2)

        # Performance Stats
        perf_group = tk.LabelFrame(container, text="AI Performance", bg=self.bg_color, fg=self.fg_color)
        perf_group.pack(fill="x", pady=10)

        tk.Button(perf_group, text="Show Stats", command=self.show_perf_stats, bg="#007BFF", fg="white").pack(side="left", padx=10, pady=5)
        tk.Button(perf_group, text="Clear Cache", command=self.clear_cache, bg="#FF6B6B", fg="white").pack(side="left", padx=10, pady=5)

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

            opts = ollama.get("options", {})
            self.temp_var.set(opts.get("temperature", 0.7))
            self.top_p_var.set(opts.get("top_p", 0.9))
            self.num_predict_var.set(opts.get("num_predict", 2048))

            tasks = ollama.get("task_models", {})
            for key, var in self.task_vars.items():
                var.set(tasks.get(key, ""))
        except Exception as e:
            print(f"Error loading settings: {e}")

    def show_perf_stats(self):
        try:
            oc = self.main_app.strategy_service.ollama_client
            metrics = oc.get_performance_metrics()
            stats = f"AI Stats:\n{json.dumps(metrics, indent=2)}"
            messagebox.showinfo("AI Performance", stats)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def clear_cache(self):
        try:
            self.main_app.strategy_service.ollama_client.clear_cache()
            messagebox.showinfo("Success", "Cache cleared")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def save_settings(self):
        try:
            cfg = load_app_config()
            cfg["api"] = {
                "freqtrade_url": self.url_var.get(),
                "user": self.user_var.get(),
                "password": self.pass_var.get()
            }
            if "ollama" not in cfg: cfg["ollama"] = {}
            cfg["ollama"]["base_url"] = self.ol_url_var.get()
            cfg["ollama"]["model"] = self.ol_model_var.get()
            cfg["ollama"]["options"] = {
                "temperature": self.temp_var.get(),
                "top_p": self.top_p_var.get(),
                "num_predict": self.num_predict_var.get()
            }
            cfg["ollama"]["task_models"] = {k: v.get() for k, v in self.task_vars.items()}
            
            with open(APP_CONFIG_PATH, 'w') as f:
                json.dump(cfg, f, indent=2)
            
            messagebox.showinfo("Success", "Settings saved successfully.")
            self.main_app.client.update_settings(cfg["api"]["freqtrade_url"], cfg["api"]["user"], cfg["api"]["password"])
            self.main_app.strategy_service.update_ollama_settings(
                base_url=cfg["ollama"]["base_url"],
                model=cfg["ollama"]["model"],
                options=cfg["ollama"]["options"],
                task_models=cfg["ollama"]["task_models"]
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
