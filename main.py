import sys
import os
import logging
import traceback



from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QTabWidget, QLabel, QMessageBox)
from PyQt6.QtCore import QTimer, QThreadPool, Qt

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from config.settings import (FREQTRADE_URL, API_USER, API_PASS, 
                               WINDOW_TITLE, WINDOW_GEOMETRY, UPDATE_INTERVAL, OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_OPTIONS, OLLAMA_TASK_MODELS)
    from api.client import FreqtradeClient
    from ui.dashboard_tab import DashboardTab
    from ui.comparing_tab import ComparingTab
    from ui.ai_analysis_tab import AIAnalysisTab
    from ui.bot_control_tab import BotControlTab
    from ui.settings_tab import SettingsTab
    from ui.backtest_tab import BacktestTab
    from ui.chat_dock import ChatDock
    from core.strategy_service import StrategyService
    from utils.qt_worker import Worker
    from utils.logging_setup import setup_logging
except Exception as e:
    print(f"Critical import error: {e}")
    traceback.print_exc()
    sys.exit(1)

class SmartBotApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        
        # Default size if geometry is missing or weird
        self.resize(1024, 768)
        if isinstance(WINDOW_GEOMETRY, (list, tuple)) and len(WINDOW_GEOMETRY) == 4:
            try:
                self.setGeometry(WINDOW_GEOMETRY[0], WINDOW_GEOMETRY[1], WINDOW_GEOMETRY[2], WINDOW_GEOMETRY[3])
            except Exception:
                pass

        # Global dark theme with high contrast for VNC
        self.setStyleSheet("""
            QMainWindow { background-color: #0f172a; }
            QMainWindow::separator { background: #1e293b; width: 4px; height: 4px; }
            QMainWindow::separator:hover { background: #3b82f6; }
            QWidget { background-color: #0f172a; color: #f1f5f9; font-family: 'Segoe UI', sans-serif; }
            QTabWidget::pane { border: 1px solid #334155; top: -1px; background-color: #0f172a; }
            QTabBar::tab { background: #1e293b; color: #94a3b8; padding: 10px 20px; border: 1px solid #334155; border-bottom: none; margin-right: 2px; }
            QTabBar::tab:selected { background: #334155; color: #ffffff; font-weight: bold; border-bottom: 2px solid #3b82f6; }
            QPushButton { background-color: #3b82f6; border: none; border-radius: 4px; padding: 8px 16px; color: white; font-weight: bold; }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton:disabled { background-color: #475569; color: #94a3b8; }
            QLineEdit, QTextEdit, QPlainTextEdit { background-color: #1e293b; border: 1px solid #334155; color: #f1f5f9; padding: 6px; border-radius: 4px; }
            QLineEdit:focus, QTextEdit:focus { border: 1px solid #3b82f6; }
            QStatusBar { background: #1e293b; color: #94a3b8; border-top: 1px solid #334155; }
        """)
        
        self.threadpool = QThreadPool.globalInstance()
        self.threadpool.setMaxThreadCount(8)
        
        self._stats_worker_running = False
        self._strategy_generate_running = False
        self._strategy_save_running = False

        # Initialize services
        self.client = FreqtradeClient(FREQTRADE_URL or "", API_USER or "", API_PASS or "")
        self.strategy_service = StrategyService()

        # Main Layout
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.layout.addWidget(self.tabs)

        # Create Tabs with defensive error handling
        self._init_tabs()

        # Status Bar
        self.status_bar = self.statusBar()
        self.status_label = QLabel("Initializing...")
        self.status_bar.addPermanentWidget(self.status_label)

        # Docked AI Chat (persistent across tabs)
        try:
            self.chat_dock = ChatDock(
                threadpool=self.threadpool,
                base_url=OLLAMA_BASE_URL,
                model=OLLAMA_MODEL,
                options=OLLAMA_OPTIONS,
                context_provider=self._build_chat_context,
                parent=self,
            )
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.chat_dock)
            self.setDockOptions(self.dockOptions() | QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowTabbedDocks)
            
            # Use a slightly smaller dock by default for better fit
            self.resizeDocks([self.chat_dock], [350], Qt.Orientation.Horizontal)
            
            view_menu = self.menuBar().addMenu("View")
            self.chat_toggle_action = self.chat_dock.toggleViewAction()
            view_menu.addAction(self.chat_toggle_action)
        except Exception as e:
            logging.error(f"Error creating chat dock: {e}")

        # Timer to update stats
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_stats)
        self.timer.start(UPDATE_INTERVAL)
        QTimer.singleShot(1000, self.update_stats)

        # Apply initial settings
        self.apply_settings(
            freqtrade_url=FREQTRADE_URL or "",
            api_user=API_USER or "",
            api_pass=API_PASS or "",
            ollama_url=OLLAMA_BASE_URL,
            ollama_model=OLLAMA_MODEL,
            ollama_options=OLLAMA_OPTIONS,
            ollama_task_models=OLLAMA_TASK_MODELS,
        )

    def _init_tabs(self):
        tab_creators = [
            (self.create_dashboard_tab, "Dashboard"),
            (self.create_comparing_tab, "Comparing"),
            (self.create_ai_analysis_tab, "AI Analysis"),
            (self.create_bot_control_tab, "Control"),
            (self.create_settings_tab, "Settings"),
            (self.create_backtest_tab, "Backtest")
        ]
        
        for creator, name in tab_creators:
            try:
                creator()
            except Exception as e:
                logging.error(f"Failed to create tab {name}: {e}")
                placeholder = QWidget()
                l = QVBoxLayout(placeholder)
                l.addWidget(QLabel(f"Error loading {name}: {e}"))
                self.tabs.addTab(placeholder, name)

    def create_dashboard_tab(self):
        self.dashboard_tab = DashboardTab(self.client, self.threadpool)
        self.tabs.addTab(self.dashboard_tab, "Dashboard")

    def create_comparing_tab(self):
        self.comparing_tab = ComparingTab(main_app=self)
        self.tabs.addTab(self.comparing_tab, "Comparing")

    def create_ai_analysis_tab(self):
        self.ai_analysis_tab = AIAnalysisTab(self.client, self.threadpool)
        self.tabs.addTab(self.ai_analysis_tab, "AI Analysis")

    def create_bot_control_tab(self):
        self.bot_control_tab = BotControlTab(self.client, self.threadpool)
        self.tabs.addTab(self.bot_control_tab, "Control")

    def create_settings_tab(self):
        self.settings_tab = SettingsTab(main_app=self, threadpool=self.threadpool)
        self.tabs.addTab(self.settings_tab, "Settings")

    def create_backtest_tab(self):
        self.backtest_tab = BacktestTab(threadpool=self.threadpool)
        self.tabs.addTab(self.backtest_tab, "Backtest")

    def apply_settings(self, freqtrade_url: str, api_user: str, api_pass: str, ollama_url: str, ollama_model: str, ollama_options=None, ollama_task_models=None) -> None:
        try:
            self.client.update_settings(base_url=freqtrade_url, username=api_user, password=api_pass)
            self.strategy_service.update_ollama_settings(base_url=ollama_url, model=ollama_model, options=ollama_options, task_models=ollama_task_models)

            if hasattr(self, 'ai_analysis_tab'):
                self.ai_analysis_tab.update_ollama_settings(base_url=ollama_url, model=ollama_model, options=ollama_options, task_models=ollama_task_models)

            if hasattr(self, 'chat_dock'):
                self.chat_dock.update_ollama_settings(base_url=ollama_url, model=ollama_model, options=ollama_options, task_models=ollama_task_models)
        except Exception as e:
            logging.error(f"Error applying settings: {e}")

    def get_ollama_client(self):
        if hasattr(self, 'chat_dock') and hasattr(self.chat_dock, 'ollama'):
            return self.chat_dock.ollama
        return None

    def _build_chat_context(self) -> str:
        try:
            idx = self.tabs.currentIndex()
            tab_name = self.tabs.tabText(idx) if idx >= 0 else "Unknown"
            return f"User is currently on the {tab_name} tab."
        except Exception:
            return ""

    def update_stats(self):
        if self._stats_worker_running:
            return
        self._stats_worker_running = True

        def _fetch():
            try:
                return {
                    "status": self.client.get_status(),
                    "profit": self.client.get_profit(),
                }
            except Exception:
                return {"status": "Error", "profit": {}}

        worker = Worker(_fetch)

        def _on_result(data):
            status = data.get("status", "Unknown")
            profit_data = data.get("profit", {})

            raw_status = str(status or "").strip()
            if raw_status == "Not configured":
                self.status_label.setText("Bot: Not configured")
                self.status_label.setStyleSheet("color: #94a3b8;")
            elif raw_status == "Error":
                self.status_label.setText("Bot: Disconnected")
                self.status_label.setStyleSheet("color: #ef4444; font-weight: bold;")
            else:
                self.status_label.setText("Bot: Connected")
                self.status_label.setStyleSheet("color: #22c55e; font-weight: bold;")

            if hasattr(self, 'dashboard_tab'):
                self.dashboard_tab.set_stats(raw_status, profit_data)

        def _on_error(_msg: str):
            self.status_label.setText("Bot: Error")
            self.status_label.setStyleSheet("color: #ef4444;")

        def _on_finished():
            self._stats_worker_running = False

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

if __name__ == "__main__":
    setup_logging()
    
    # Ensure standard PyQt6 application setup
    app = QApplication(sys.argv)
    app.setApplicationName("SmartTrade AI")
    app.setOrganizationName("SmartTrade")
    
    try:
        window = SmartBotApp()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()
