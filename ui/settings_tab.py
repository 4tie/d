import json
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QMessageBox, QDoubleSpinBox, QSpinBox, QGroupBox
)
from PyQt6.QtCore import QThreadPool

from api.client import FreqtradeClient
from config.settings import APP_CONFIG_PATH, load_app_config
from utils.ollama_client import OllamaClient
from utils.ai_feedback import AIFeedbackCollector
from utils.qt_worker import Worker


class SettingsTab(QWidget):
    def __init__(self, main_app, threadpool: QThreadPool, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.threadpool = threadpool

        self._models_fetch_running = False
        self._save_running = False
        self._freqtrade_test_running = False
        self._ollama_test_running = False

        self._ollama_probe_client = OllamaClient()
        self._feedback_collector = AIFeedbackCollector()

        self.setup_ui()
        self.load_from_disk()

    def setup_ui(self):
        layout = QVBoxLayout()

        self.status_label = QLabel("")
        layout.addWidget(self.status_label)

        form = QFormLayout()

        self.freqtrade_url_input = QLineEdit()
        self.freqtrade_url_input.setPlaceholderText("http://127.0.0.1:8080/")
        self.api_user_input = QLineEdit()
        self.api_pass_input = QLineEdit()
        self.api_pass_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.ollama_url_input = QLineEdit()
        self.ollama_url_input.setPlaceholderText("http://localhost:11434")

        self.ollama_model_combo = QComboBox()
        self.ollama_model_combo.setEditable(True)

        self.ollama_model_generation = QComboBox()
        self.ollama_model_generation.setEditable(True)

        self.ollama_model_analysis = QComboBox()
        self.ollama_model_analysis.setEditable(True)

        self.ollama_model_risk = QComboBox()
        self.ollama_model_risk.setEditable(True)

        self.ollama_model_chat = QComboBox()
        self.ollama_model_chat.setEditable(True)

        self.ollama_temperature_input = QDoubleSpinBox()
        self.ollama_temperature_input.setMinimum(0.0)
        self.ollama_temperature_input.setMaximum(2.0)
        self.ollama_temperature_input.setSingleStep(0.05)

        self.ollama_top_p_input = QDoubleSpinBox()
        self.ollama_top_p_input.setMinimum(0.0)
        self.ollama_top_p_input.setMaximum(1.0)
        self.ollama_top_p_input.setSingleStep(0.05)

        self.ollama_num_predict_input = QSpinBox()
        self.ollama_num_predict_input.setMinimum(16)
        self.ollama_num_predict_input.setMaximum(8192)

        form.addRow("Freqtrade URL", self.freqtrade_url_input)
        form.addRow("API User", self.api_user_input)
        form.addRow("API Password", self.api_pass_input)
        form.addRow("Ollama URL", self.ollama_url_input)
        form.addRow("Ollama Model", self.ollama_model_combo)

        layout.addLayout(form)

        tests_box = QGroupBox("Connection tests")
        tests_layout = QVBoxLayout()

        ft_row = QHBoxLayout()
        self.btn_test_freqtrade = QPushButton("Test freqtrade")
        self.btn_test_freqtrade.clicked.connect(self.test_freqtrade_async)
        self.lbl_test_freqtrade = QLabel("")
        ft_row.addWidget(self.btn_test_freqtrade)
        ft_row.addWidget(self.lbl_test_freqtrade, 1)

        ol_row = QHBoxLayout()
        self.btn_test_ollama = QPushButton("Test ollama")
        self.btn_test_ollama.clicked.connect(self.test_ollama_async)
        self.lbl_test_ollama = QLabel("")
        ol_row.addWidget(self.btn_test_ollama)
        ol_row.addWidget(self.lbl_test_ollama, 1)

        tests_layout.addLayout(ft_row)
        tests_layout.addLayout(ol_row)
        tests_box.setLayout(tests_layout)
        layout.addWidget(tests_box)

        advanced_box = QGroupBox("Advanced AI options")
        advanced_box.setCheckable(True)
        advanced_box.setChecked(False)
        advanced_box.setFlat(True)

        adv_form = QFormLayout()
        adv_form.addRow("Temperature", self.ollama_temperature_input)
        adv_form.addRow("Top_p", self.ollama_top_p_input)
        adv_form.addRow("Num_predict", self.ollama_num_predict_input)
        advanced_box.setLayout(adv_form)
        layout.addWidget(advanced_box)

        task_box = QGroupBox("Task Models (Ensemble)")
        task_box.setCheckable(True)
        task_box.setChecked(False)
        task_box.setFlat(True)

        task_form = QFormLayout()
        task_form.addRow("Strategy generation", self.ollama_model_generation)
        task_form.addRow("Strategy analysis", self.ollama_model_analysis)
        task_form.addRow("Risk assessment", self.ollama_model_risk)
        task_form.addRow("Chat", self.ollama_model_chat)
        task_box.setLayout(task_form)
        layout.addWidget(task_box)

        btns = QHBoxLayout()
        self.btn_refresh_models = QPushButton("Refresh models")
        self.btn_refresh_models.clicked.connect(self.refresh_models_async)

        self.btn_save_apply = QPushButton("Save & apply")
        self.btn_save_apply.clicked.connect(self.save_and_apply_async)

        btns.addWidget(self.btn_refresh_models)
        btns.addWidget(self.btn_save_apply)
        layout.addLayout(btns)

        # AI Performance Monitoring Section
        perf_group = QGroupBox("AI Performance Monitoring")
        perf_group.setCheckable(True)
        perf_group.setChecked(False)
        perf_group.setFlat(True)
        
        perf_layout = QVBoxLayout()
        
        self.lbl_perf_status = QLabel("Performance monitoring not active")
        self.lbl_perf_status.setStyleSheet("font-weight: bold; color: orange;")
        
        self.btn_show_perf = QPushButton("Show performance stats")
        self.btn_show_perf.clicked.connect(self.show_performance_stats)
        self.btn_show_perf.setStyleSheet("background-color: #007BFF; color: white; padding: 8px;")
        
        self.btn_clear_cache = QPushButton("Clear AI cache")
        self.btn_clear_cache.clicked.connect(self.clear_ai_cache)
        self.btn_clear_cache.setStyleSheet("background-color: #FF6B6B; color: white; padding: 8px;")
        
        perf_layout.addWidget(self.lbl_perf_status)
        perf_layout.addWidget(self.btn_show_perf)
        perf_layout.addWidget(self.btn_clear_cache)
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)
        
        self.setLayout(layout)

    def _set_test_label(self, label: QLabel, status: str) -> None:
        s = str(status or "").strip()
        label.setText(s)
        if s == "Connected":
            label.setStyleSheet("font-weight: bold; color: green;")
        elif s == "Disconnected":
            label.setStyleSheet("font-weight: bold; color: red;")
        elif s == "Not configured":
            label.setStyleSheet("font-weight: bold; color: #888888;")
        else:
            label.setStyleSheet("")

    def test_freqtrade_async(self):
        if self._freqtrade_test_running:
            return

        freqtrade_url = self.freqtrade_url_input.text().strip()
        api_user = self.api_user_input.text().strip()
        api_pass = self.api_pass_input.text().strip()

        self._freqtrade_test_running = True
        self.btn_test_freqtrade.setEnabled(False)
        self._set_test_label(self.lbl_test_freqtrade, "Checking...")

        def _check():
            tmp = FreqtradeClient(freqtrade_url, api_user, api_pass)
            s = tmp.get_status()
            if s == "Not configured":
                return "Not configured"
            if s == "Error":
                return "Disconnected"
            return "Connected"

        worker = Worker(_check)

        def _on_result(result: str):
            self._set_test_label(self.lbl_test_freqtrade, result)

        def _on_error(_msg: str):
            self._set_test_label(self.lbl_test_freqtrade, "Disconnected")

        def _on_finished():
            self._freqtrade_test_running = False
            self.btn_test_freqtrade.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

    def test_ollama_async(self):
        if self._ollama_test_running:
            return

        base_url = self.ollama_url_input.text().strip()

        self._ollama_test_running = True
        self.btn_test_ollama.setEnabled(False)
        self._set_test_label(self.lbl_test_ollama, "Checking...")

        def _check():
            if not base_url:
                return "Not configured"
            self._ollama_probe_client.update_settings(
                base_url=base_url,
                model=self.ollama_model_combo.currentText().strip() or "llama2",
                options={},
            )
            ok = self._ollama_probe_client.is_available()
            return "Connected" if ok else "Disconnected"

        worker = Worker(_check)

        def _on_result(result: str):
            self._set_test_label(self.lbl_test_ollama, result)

        def _on_error(_msg: str):
            self._set_test_label(self.lbl_test_ollama, "Disconnected")

        def _on_finished():
            self._ollama_test_running = False
            self.btn_test_ollama.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

    def load_from_disk(self):
        try:
            cfg = load_app_config()
            if not isinstance(cfg, dict):
                cfg = {}

            api_cfg = cfg.get("api")
            ollama_cfg = cfg.get("ollama")

            if not isinstance(api_cfg, dict):
                api_cfg = {}
            if ollama_cfg is None or not isinstance(ollama_cfg, dict):
                ollama_cfg = {}

            self.freqtrade_url_input.setText(str(api_cfg.get("freqtrade_url", "")))
            self.api_user_input.setText(str(api_cfg.get("user", "")))
            self.api_pass_input.setText(str(api_cfg.get("password", "")))

            self.ollama_url_input.setText(str(ollama_cfg.get("base_url", "http://localhost:11434")))

            model = str(ollama_cfg.get("model", ""))
            if model:
                if self.ollama_model_combo.findText(model) == -1:
                    self.ollama_model_combo.addItem(model)
                self.ollama_model_combo.setCurrentText(model)

            task_models = ollama_cfg.get("task_models", {})
            if task_models is None:
                task_models = {}
            if not isinstance(task_models, dict):
                raise RuntimeError("Invalid ollama.task_models (expected object)")

            def _set_task(combo: QComboBox, key: str):
                v = str(task_models.get(key, "")).strip()
                if v:
                    if combo.findText(v) == -1:
                        combo.addItem(v)
                    combo.setCurrentText(v)

            _set_task(self.ollama_model_generation, "strategy_generation")
            _set_task(self.ollama_model_analysis, "strategy_analysis")
            _set_task(self.ollama_model_risk, "risk_assessment")
            _set_task(self.ollama_model_chat, "chat")

            opts = ollama_cfg.get("options", {})
            if opts is None:
                opts = {}
            if not isinstance(opts, dict):
                raise RuntimeError("Invalid ollama.options (expected object)")

            try:
                self.ollama_temperature_input.setValue(float(opts.get("temperature", 0.7)))
            except Exception:
                self.ollama_temperature_input.setValue(0.7)

            try:
                self.ollama_top_p_input.setValue(float(opts.get("top_p", 0.9)))
            except Exception:
                self.ollama_top_p_input.setValue(0.9)

            try:
                self.ollama_num_predict_input.setValue(int(opts.get("num_predict", 2048)))
            except Exception:
                self.ollama_num_predict_input.setValue(2048)

            self.status_label.setText(f"Loaded: {APP_CONFIG_PATH}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load app config: {e}")
            self.status_label.setText("Failed to load config")

    def refresh_models_async(self):
        if self._models_fetch_running:
            return

        base_url = self.ollama_url_input.text().strip()
        if not base_url:
            QMessageBox.warning(self, "Warning", "Please enter Ollama URL first.")
            return

        self._models_fetch_running = True
        self.btn_refresh_models.setEnabled(False)
        self.status_label.setText("Fetching models from Ollama...")

        def _fetch():
            opts = {
                "temperature": float(self.ollama_temperature_input.value()),
                "top_p": float(self.ollama_top_p_input.value()),
                "num_predict": int(self.ollama_num_predict_input.value()),
            }
            self._ollama_probe_client.update_settings(
                base_url=base_url,
                model=self.ollama_model_combo.currentText().strip() or "llama2",
                options=opts,
            )
            return self._ollama_probe_client.list_models()

        worker = Worker(_fetch)

        def _on_result(models):
            if not isinstance(models, list):
                QMessageBox.critical(self, "Error", "Unexpected Ollama model list response")
                self.status_label.setText("Failed to fetch models.")
                return

            current = self.ollama_model_combo.currentText().strip()
            current_gen = self.ollama_model_generation.currentText().strip()
            current_analysis = self.ollama_model_analysis.currentText().strip()
            current_risk = self.ollama_model_risk.currentText().strip()
            current_chat = self.ollama_model_chat.currentText().strip()
            self.ollama_model_combo.clear()
            self.ollama_model_generation.clear()
            self.ollama_model_analysis.clear()
            self.ollama_model_risk.clear()
            self.ollama_model_chat.clear()
            for m in models:
                if isinstance(m, str) and m.strip():
                    mm = m.strip()
                    self.ollama_model_combo.addItem(mm)
                    self.ollama_model_generation.addItem(mm)
                    self.ollama_model_analysis.addItem(mm)
                    self.ollama_model_risk.addItem(mm)
                    self.ollama_model_chat.addItem(mm)

            if current:
                self.ollama_model_combo.setCurrentText(current)
            if current_gen:
                self.ollama_model_generation.setCurrentText(current_gen)
            if current_analysis:
                self.ollama_model_analysis.setCurrentText(current_analysis)
            if current_risk:
                self.ollama_model_risk.setCurrentText(current_risk)
            if current_chat:
                self.ollama_model_chat.setCurrentText(current_chat)
            self.status_label.setText("Models loaded from Ollama.")

        def _on_error(msg: str):
            QMessageBox.critical(self, "Error", f"Failed to fetch Ollama models: {msg}")
            self.status_label.setText("Failed to fetch models.")

        def _on_finished():
            self._models_fetch_running = False
            self.btn_refresh_models.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)
    
    def show_performance_stats(self):
        """Show AI performance statistics"""
        try:
            # Get performance stats from the main app's Ollama client
            ollama_client = self.main_app.get_ollama_client()
            if ollama_client:
                metrics = ollama_client.get_performance_metrics()
                queue_status = ollama_client.get_queue_status()
                
                stats_text = "AI Performance Statistics:\n\n"
                stats_text += f"Queue Status:\n"
                stats_text += f"  Active Requests: {queue_status['active_requests']}/{queue_status['max_concurrent']}\n"
                stats_text += f"  Queued Requests: {queue_status['queued_requests']}/{queue_status['max_queue_size']}\n\n"
                
                stats_text += "Performance Metrics:\n"
                if metrics:
                    for method, data in metrics.items():
                        success_rate = (data['successful_requests'] / data['total_requests'] * 100) if data['total_requests'] > 0 else 0
                        avg_duration = (data['total_duration'] / data['total_requests']) if data['total_requests'] > 0 else 0
                        stats_text += f"  {method}:\n"
                        stats_text += f"    Total Requests: {data['total_requests']}\n"
                        stats_text += f"    Success Rate: {success_rate:.1f}%\n"
                        stats_text += f"    Avg Duration: {avg_duration:.2f}s\n"
                        stats_text += f"    Avg Prompt Length: {data['total_prompt_length'] / data['total_requests'] if data['total_requests'] > 0 else 0:.0f} chars\n"
                else:
                    stats_text += "  No performance data available yet.\n"
                
                # Add feedback stats
                feedback_stats = self._feedback_collector.get_feedback_stats()
                stats_text += f"\nFeedback Statistics:\n"
                stats_text += f"  Total Feedback: {feedback_stats['total_feedback']}\n"
                stats_text += f"  Average Rating: {feedback_stats['average_rating']}/5\n"
                stats_text += f"  Feedback with Comments: {feedback_stats['feedback_with_comments']}\n"

                # Add persistent performance store stats
                store_stats = None
                try:
                    if hasattr(self.main_app, "strategy_service") and hasattr(self.main_app.strategy_service, "performance_store"):
                        store_stats = self.main_app.strategy_service.performance_store.get_run_stats()
                except Exception as e:
                    store_stats = {"error": str(e)}

                stats_text += "\nPersistent Strategy Run Store (SQLite):\n"
                if isinstance(store_stats, dict) and store_stats.get("error"):
                    stats_text += f"  Error: {store_stats.get('error')}\n"
                elif isinstance(store_stats, dict):
                    stats_text += f"  Total Runs: {store_stats.get('total_runs')}\n"
                    stats_text += f"  Last Timestamp: {store_stats.get('last_ts')}\n"
                    by_type = store_stats.get("by_type")
                    if isinstance(by_type, dict) and by_type:
                        stats_text += "  By Type:\n"
                        for k, v in by_type.items():
                            stats_text += f"    {k}: {v}\n"
                    else:
                        stats_text += "  By Type: (none)\n"

                fb_stats = None
                try:
                    if hasattr(self.main_app, "strategy_service") and hasattr(self.main_app.strategy_service, "performance_store"):
                        fb_stats = self.main_app.strategy_service.performance_store.get_feedback_stats()
                except Exception as e:
                    fb_stats = {"error": str(e)}

                stats_text += "\nRun Feedback (SQLite):\n"
                if isinstance(fb_stats, dict) and fb_stats.get("error"):
                    stats_text += f"  Error: {fb_stats.get('error')}\n"
                elif isinstance(fb_stats, dict):
                    stats_text += f"  Total Feedback: {fb_stats.get('total_feedback')}\n"
                    stats_text += f"  Average Rating: {fb_stats.get('average_rating')}/5\n"
                    stats_text += f"  Feedback with Comments: {fb_stats.get('feedback_with_comments')}\n"
                
                QMessageBox.information(self, "AI Performance Stats", stats_text)
            else:
                QMessageBox.warning(self, "Warning", "Ollama client not available")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to retrieve performance stats: {e}")
    
    def clear_ai_cache(self):
        """Clear the AI response cache"""
        try:
            ollama_client = self.main_app.get_ollama_client()
            if ollama_client:
                cache_size = len(ollama_client._cache) if hasattr(ollama_client, '_cache') else 0
                ollama_client.clear_cache()
                QMessageBox.information(self, "Cache Cleared", f"Cleared {cache_size} cached responses")
                self.lbl_perf_status.setText("AI cache cleared")
                self.lbl_perf_status.setStyleSheet("font-weight: bold; color: green;")
            else:
                QMessageBox.warning(self, "Warning", "Ollama client not available")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear cache: {e}")

    def save_and_apply_async(self):
        if self._save_running:
            return

        freqtrade_url = self.freqtrade_url_input.text().strip()
        api_user = self.api_user_input.text().strip()
        api_pass = self.api_pass_input.text().strip()
        ollama_url = self.ollama_url_input.text().strip()
        ollama_model = self.ollama_model_combo.currentText().strip()

        task_models = {
            "strategy_generation": self.ollama_model_generation.currentText().strip(),
            "strategy_analysis": self.ollama_model_analysis.currentText().strip(),
            "risk_assessment": self.ollama_model_risk.currentText().strip(),
            "chat": self.ollama_model_chat.currentText().strip(),
        }
        task_models = {k: v for k, v in task_models.items() if isinstance(v, str) and v.strip()}

        ollama_options = {
            "temperature": float(self.ollama_temperature_input.value()),
            "top_p": float(self.ollama_top_p_input.value()),
            "num_predict": int(self.ollama_num_predict_input.value()),
        }

        if not freqtrade_url or not api_user or not api_pass:
            QMessageBox.warning(self, "Warning", "Freqtrade URL, API User, and API Password are required.")
            return

        if not ollama_url or not ollama_model:
            QMessageBox.warning(self, "Warning", "Ollama URL and Model are required.")
            return

        self._save_running = True
        self.btn_save_apply.setEnabled(False)
        self.btn_refresh_models.setEnabled(False)
        self.status_label.setText("Saving settings...")

        def _write():
            if os.path.exists(APP_CONFIG_PATH):
                with open(APP_CONFIG_PATH, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            else:
                cfg = {}
            if not isinstance(cfg, dict):
                cfg = {}

            api_cfg = cfg.get("api")
            if not isinstance(api_cfg, dict):
                api_cfg = {}
                cfg["api"] = api_cfg

            api_cfg["freqtrade_url"] = freqtrade_url
            api_cfg["user"] = api_user
            api_cfg["password"] = api_pass

            ollama_cfg = cfg.get("ollama")
            if ollama_cfg is None or not isinstance(ollama_cfg, dict):
                ollama_cfg = {}
                cfg["ollama"] = ollama_cfg

            ollama_cfg["base_url"] = ollama_url
            ollama_cfg["model"] = ollama_model
            ollama_cfg["options"] = ollama_options
            if task_models:
                ollama_cfg["task_models"] = task_models
            else:
                if "task_models" in ollama_cfg:
                    del ollama_cfg["task_models"]

            with open(APP_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)

            return {
                "freqtrade_url": freqtrade_url,
                "api_user": api_user,
                "api_pass": api_pass,
                "ollama_url": ollama_url,
                "ollama_model": ollama_model,
                "ollama_options": ollama_options,
                "ollama_task_models": task_models,
            }

        worker = Worker(_write)

        def _on_result(saved):
            self.status_label.setText("Settings saved. Applying...")
            if not isinstance(saved, dict):
                QMessageBox.critical(self, "Error", "Unexpected save result")
                return

            self.main_app.apply_settings(
                freqtrade_url=saved["freqtrade_url"],
                api_user=saved["api_user"],
                api_pass=saved["api_pass"],
                ollama_url=saved["ollama_url"],
                ollama_model=saved["ollama_model"],
                ollama_options=saved.get("ollama_options"),
                ollama_task_models=saved.get("ollama_task_models"),
            )
            self.status_label.setText("Settings applied.")
            QMessageBox.information(self, "Success", "Settings saved and applied.")

        def _on_error(msg: str):
            QMessageBox.critical(self, "Error", f"Failed to save settings: {msg}")
            self.status_label.setText("Save failed.")

        def _on_finished():
            self._save_running = False
            self.btn_save_apply.setEnabled(True)
            self.btn_refresh_models.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)
