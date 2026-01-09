"""
Dashboard tab component for displaying bot status and profit
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QLabel, QPushButton)
from PyQt6.QtCore import Qt, QThreadPool

from utils.qt_worker import Worker

class DashboardTab(QWidget):
    def __init__(self, client, threadpool: QThreadPool, parent=None):
        super().__init__(parent)
        self.client = client
        self.threadpool = threadpool
        self._refresh_running = False
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        self.lbl_bot_status = QLabel("Bot status: Checking...")
        self.lbl_bot_status.setStyleSheet("font-size: 18px; font-weight: bold;")

        self.lbl_freqtrade_url = QLabel("Freqtrade URL: ---")
        self.lbl_freqtrade_url.setStyleSheet("font-size: 12px; color: #888888;")
        
        self.lbl_profit = QLabel("Total profit: ---")
        self.lbl_profit.setStyleSheet("font-size: 16px; color: green;")

        btn_refresh = QPushButton("Refresh data")
        btn_refresh.clicked.connect(self.refresh_async)

        layout.addWidget(self.lbl_bot_status)
        layout.addWidget(self.lbl_freqtrade_url)
        layout.addWidget(self.lbl_profit)
        layout.addWidget(btn_refresh)
        layout.addStretch()
        self.setLayout(layout)

    def _format_url(self, url: str, max_len: int = 48) -> str:
        u = str(url or "").strip()
        if not u:
            return "(not configured)"
        if len(u) <= max_len:
            return u
        return u[: max_len - 3].rstrip() + "..."
    
    def set_stats(self, status: str, profit_data):
        raw_status = str(status or "").strip()
        if raw_status in {"Error", "Disconnected"}:
            display_status = "Disconnected"
        elif raw_status == "Not configured":
            display_status = "Not configured"
        elif raw_status == "Connected":
            display_status = "Connected"
        else:
            display_status = "Connected"

        self.lbl_bot_status.setText(f"Bot status: {display_status}")
        self.lbl_freqtrade_url.setText(f"Freqtrade URL: {self._format_url(getattr(self.client, 'base_url', ''))}")

        if display_status == "Not configured":
            self.lbl_profit.setText("Total profit: ---")
            self.lbl_profit.setStyleSheet("font-size: 16px; color: #888888;")
            return

        if display_status == "Disconnected":
            self.lbl_profit.setText("Total profit: Offline")
            self.lbl_profit.setStyleSheet("font-size: 16px; color: #888888;")
            return

        if isinstance(profit_data, dict) and 'profit_all_coin' in profit_data:
            profit_pct = profit_data.get('profit_all_percent', profit_data.get('profit_all_pct', 0))
            try:
                profit_pct = float(profit_pct)
            except Exception:
                profit_pct = 0.0
            self.lbl_profit.setText(f"Total profit: {profit_pct:.2f}%")
            self.lbl_profit.setStyleSheet("font-size: 16px; color: green;")
        else:
            self.lbl_profit.setText("Total profit: ---")
            self.lbl_profit.setStyleSheet("font-size: 16px; color: orange;")

    def refresh_async(self):
        if self._refresh_running:
            return

        self._refresh_running = True

        def _fetch():
            return {
                "status": self.client.get_status(),
                "profit": self.client.get_profit(),
            }

        worker = Worker(_fetch)

        def _on_result(data):
            status = data.get("status", "Unknown")
            profit_data = data.get("profit", {})
            self.set_stats(status, profit_data)

        def _on_finished():
            self._refresh_running = False

        worker.signals.result.connect(_on_result)
        worker.signals.finished.connect(_on_finished)
        worker.signals.error.connect(lambda msg: self.set_stats("Error", {}))
        self.threadpool.start(worker)
