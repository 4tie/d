import sys
import os
import logging
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QTabWidget, QLabel, QMessageBox)
from PyQt6.QtCore import QTimer, QThreadPool, Qt

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config.settings import (FREQTRADE_URL, API_USER, API_PASS, 
                           WINDOW_TITLE, WINDOW_GEOMETRY, UPDATE_INTERVAL, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_OPTIONS, OLLAMA_TASK_MODELS)

from api.client import FreqtradeClient
from ui.dashboard_tab import DashboardTab
from ui.ai_builder_tab import AIBuilderTab
from ui.ai_analysis_tab import AIAnalysisTab
from ui.bot_control_tab import BotControlTab
from ui.settings_tab import SettingsTab
from ui.backtest_tab import BacktestTab
from ui.chat_dock import ChatDock
from core.strategy_service import StrategyService
from utils.qt_worker import Worker
from utils.logging_setup import setup_logging

class SmartBotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.setGeometry(WINDOW_GEOMETRY[0], WINDOW_GEOMETRY[1], WINDOW_GEOMETRY[2], WINDOW_GEOMETRY[3])

        # Make the dock resize handle clearly visible/grabbable inside the app UI.
        self.setStyleSheet(
            (self.styleSheet() or "")
            + "\nQMainWindow::separator { background: #1b2a4a; width: 6px; height: 6px; }"
            + "\nQMainWindow::separator:hover { background: #2b59ff; }"
        )
        
        self.threadpool = QThreadPool.globalInstance()
        self._stats_worker_running = False
        self._strategy_generate_running = False
        self._strategy_save_running = False

        # Initialize services
        self.client = FreqtradeClient(FREQTRADE_URL, API_USER, API_PASS)
        self.strategy_service = StrategyService()

        # Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.layout.addWidget(self.tabs)

        # Create Tabs
        self.create_dashboard_tab()
        self.create_ai_builder_tab()
        self.create_ai_analysis_tab()
        self.create_bot_control_tab()
        self.create_settings_tab()
        self.create_backtest_tab()

        # Status Bar
        self.status_label = QLabel("Connecting...")
        self.layout.addWidget(self.status_label)

        # Docked AI Chat (persistent across tabs)
        self.chat_dock = ChatDock(
            threadpool=self.threadpool,
            base_url=OLLAMA_BASE_URL,
            model=OLLAMA_MODEL,
            options=OLLAMA_OPTIONS,
            context_provider=self._build_chat_context,
            parent=self,
        )
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
        self.setDockOptions(self.dockOptions() | QMainWindow.DockOption.AnimatedDocks)
        self.resizeDocks([self.chat_dock], [420], Qt.Orientation.Horizontal)
        self.chat_dock.topLevelChanged.connect(self._on_chat_top_level_changed)

        view_menu = self.menuBar().addMenu("View")
        self.chat_toggle_action = self.chat_dock.toggleViewAction()
        view_menu.addAction(self.chat_toggle_action)
        self.chat_toggle_action.toggled.connect(self._on_chat_toggled)

        # Timer to update stats every 5 seconds
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(UPDATE_INTERVAL)
        self.update_stats()

        # Ensure initial settings (including optional task-specific models) are applied.
        self.apply_settings(
            freqtrade_url=FREQTRADE_URL,
            api_user=API_USER,
            api_pass=API_PASS,
            ollama_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_MODEL,
            ollama_options=OLLAMA_OPTIONS,
            ollama_task_models=OLLAMA_TASK_MODELS,
        )

    def _on_chat_toggled(self, visible: bool) -> None:
        if not visible:
            return

        self.restore_chat_dock()

    def _on_chat_top_level_changed(self, top_level: bool) -> None:
        # Prevent floating state (was crashing for the user). Snap back into the main UI.
        if not top_level:
            return
        QTimer.singleShot(0, self.restore_chat_dock)

    def restore_chat_dock(self) -> None:
        # Ensure the dock returns to the expected place.
        try:
            if self.chat_dock.isFloating():
                self.chat_dock.setFloating(False)
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
            self.chat_dock.show()
            self.resizeDocks([self.chat_dock], [420], Qt.Orientation.Horizontal)
        except Exception:
            self.chat_dock.show()

    def create_dashboard_tab(self):
        """Tab 1: Shows Bot Status and Profit"""
        self.dashboard_tab = DashboardTab(self.client, self.threadpool)
        self.tabs.addTab(self.dashboard_tab, "Dashboard")

    def create_ai_builder_tab(self):
        """Tab 2: The AI Strategy Generator"""
        self.ai_builder_tab = AIBuilderTab(main_app=self)
        self.tabs.addTab(self.ai_builder_tab, "AI Strategy Builder")

    def create_ai_analysis_tab(self):
        """Tab 3: AI Analysis and Insights"""
        self.ai_analysis_tab = AIAnalysisTab(self.client, self.threadpool)
        self.tabs.addTab(self.ai_analysis_tab, "AI Analysis")

    def create_bot_control_tab(self):
        """Tab 4: Bot Control and Configuration"""
        self.bot_control_tab = BotControlTab(self.client, self.threadpool)
        self.tabs.addTab(self.bot_control_tab, "Bot Control")

    def create_settings_tab(self):
        """Tab 5: Application Settings"""
        self.settings_tab = SettingsTab(main_app=self, threadpool=self.threadpool)
        self.tabs.addTab(self.settings_tab, "Settings")

    def create_backtest_tab(self):
        """Tab 6: Backtesting"""
        self.backtest_tab = BacktestTab(threadpool=self.threadpool)
        self.tabs.addTab(self.backtest_tab, "Backtest")

    def apply_settings(self, freqtrade_url: str, api_user: str, api_pass: str, ollama_url: str, ollama_model: str, ollama_options=None, ollama_task_models=None) -> None:
        self.client.update_settings(base_url=freqtrade_url, username=api_user, password=api_pass)
        self.strategy_service.update_ollama_settings(base_url=ollama_url, model=ollama_model, options=ollama_options, task_models=ollama_task_models)

        if hasattr(self, 'ai_analysis_tab'):
            self.ai_analysis_tab.update_ollama_settings(base_url=ollama_url, model=ollama_model, options=ollama_options, task_models=ollama_task_models)

        if hasattr(self, 'chat_dock'):
            self.chat_dock.update_ollama_settings(base_url=ollama_url, model=ollama_model, options=ollama_options, task_models=ollama_task_models)
    
    def get_ollama_client(self):
        """Get the Ollama client for performance monitoring"""
        if hasattr(self, 'chat_dock') and hasattr(self.chat_dock, 'ollama'):
            return self.chat_dock.ollama
        return None

    def _build_chat_context(self) -> str:
        parts = []
        try:
            idx = self.tabs.currentIndex()
            tab_name = self.tabs.tabText(idx) if idx >= 0 else ""
            if tab_name:
                parts.append(f"Active tab: {tab_name}")
        except Exception:
            pass

        try:
            if hasattr(self, 'backtest_tab'):
                tf = self.backtest_tab.timeframe_combo.currentText().strip()
                pairs = self.backtest_tab.pairs_combo.currentText().strip()
                timerange = self.backtest_tab.timerange_combo.currentText().strip()
                if tf or pairs or timerange:
                    parts.append("Backtest selections:")
                    if tf:
                        parts.append(f"- timeframe: {tf}")
                    if pairs:
                        parts.append(f"- pairs: {pairs}")
                    if timerange:
                        parts.append(f"- timerange: {timerange}")
        except Exception:
            pass

        try:
            if hasattr(self, 'ai_builder_tab'):
                idea = self.ai_builder_tab.txt_prompt.toPlainText().strip()
                if idea:
                    parts.append("AI Builder idea (current):")
                    parts.append(idea[:2000])
        except Exception:
            pass

        try:
            if hasattr(self, 'ai_analysis_tab'):
                code = self.ai_analysis_tab.txt_strategy_input.toPlainText().strip()
                if code:
                    parts.append("AI Analysis strategy code loaded (truncated):")
                    parts.append(code[:2000])
        except Exception:
            pass

        return "\n".join(parts)

    def update_stats(self):
        """Polls the API for updates"""
        if self._stats_worker_running:
            return

        self._stats_worker_running = True

        def _fetch():
            return {
                "status": self.client.get_status(),
                "profit": self.client.get_profit(),
            }

        worker = Worker(_fetch)

        def _on_result(data):
            status = data.get("status", "Unknown")
            profit_data = data.get("profit", {})

            raw_status = str(status or "").strip()
            if raw_status == "Not configured":
                display_status = "Not configured"
                self.status_label.setStyleSheet("font-weight: bold; color: #888888;")
            elif raw_status == "Error":
                display_status = "Disconnected"
                self.status_label.setStyleSheet("font-weight: bold; color: red;")
            else:
                display_status = "Connected"
                self.status_label.setStyleSheet("font-weight: bold; color: green;")

            self.status_label.setText(display_status)

            if hasattr(self, 'dashboard_tab'):
                self.dashboard_tab.set_stats(display_status, profit_data)

        def _on_error(_msg: str):
            self.status_label.setText("Disconnected")
            self.status_label.setStyleSheet("font-weight: bold; color: red;")

        def _on_finished():
            self._stats_worker_running = False

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

    def generate_strategy_logic(self):
        """Generate AI strategy using the strategy service"""
        if self._strategy_generate_running:
            return

        user_idea = self.ai_builder_tab.txt_prompt.toPlainText()
        if not user_idea or not user_idea.strip():
            QMessageBox.warning(self, "Warning", "Please enter a strategy description.")
            return

        self._strategy_generate_running = True
        self.ai_builder_tab.btn_generate.setEnabled(False)
        self.ai_builder_tab.btn_save.setEnabled(False)
        self.ai_builder_tab.lbl_status.setText("Generating strategy (Ollama)...")

        worker = Worker(self.strategy_service.generate_strategy_code, user_idea)

        def _on_result(code: str):
            self.ai_builder_tab.txt_code_preview.setText(code)
            self.ai_builder_tab.lbl_status.setText("Strategy generated.")

        def _on_error(msg: str):
            self.ai_builder_tab.lbl_status.setText("Generation failed.")
            QMessageBox.critical(self, "Error", msg)

        def _on_finished():
            self._strategy_generate_running = False
            self.ai_builder_tab.btn_generate.setEnabled(True)
            self.ai_builder_tab.btn_save.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

    def save_strategy(self):
        """Save strategy using the strategy service"""
        if self._strategy_save_running:
            return

        code = self.ai_builder_tab.txt_code_preview.toPlainText()
        if not code or not code.strip():
            QMessageBox.warning(self, "Warning", "No strategy code to save.")
            return

        self._strategy_save_running = True
        self.ai_builder_tab.btn_save.setEnabled(False)
        self.ai_builder_tab.lbl_status.setText("Saving strategy...")

        worker = Worker(self.strategy_service.save_strategy_code, code)

        def _on_result(ok: bool):
            if ok:
                self.ai_builder_tab.lbl_status.setText("Strategy saved to strategies folder.")
                QMessageBox.information(self, "Success", "Strategy saved.")
            else:
                self.ai_builder_tab.lbl_status.setText("Save failed.")
                QMessageBox.critical(self, "Error", "Failed to save strategy.")

        def _on_error(msg: str):
            self.ai_builder_tab.lbl_status.setText("Save failed.")
            QMessageBox.critical(self, "Error", msg)

        def _on_finished():
            self._strategy_save_running = False
            self.ai_builder_tab.btn_save.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

# --- RUN APP ---
if __name__ == "__main__":
    log_path = setup_logging()
    logging.getLogger(__name__).info("Logging initialized. File: %s", log_path)
    app = QApplication(sys.argv)
    window = SmartBotApp()
    window.show()
    sys.exit(app.exec())
