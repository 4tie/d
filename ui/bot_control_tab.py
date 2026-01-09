"""
Bot Control Tab for managing the Freqtrade bot
"""
import logging
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QLineEdit, QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox,
    QFormLayout, QGroupBox
)
from PyQt6.QtCore import Qt, QThreadPool
from api.client import FreqtradeClient
from config.settings import BOT_CONFIG_PATH

from utils.qt_worker import Worker

logger = logging.getLogger(__name__)

class BotControlTab(QWidget):
    def __init__(self, client: FreqtradeClient, threadpool: QThreadPool, parent=None):
        super().__init__(parent)
        self.client = client
        self.threadpool = threadpool
        self._config_load_running = False
        self._save_running = False
        self._reload_running = False
        self._open_trades_running = False
        self.setup_ui()
        self.load_current_config_async()
        self.refresh_open_trades_async(silent=True)

    def setup_ui(self):
        layout = QVBoxLayout()

        config_box = QGroupBox("Bot Configuration")
        config_box_layout = QVBoxLayout()

        form = QFormLayout()
        self.strategy_input = QLineEdit()
        self.strategy_input.setPlaceholderText("e.g. MyStrategy")
        self.timeframe_input = QLineEdit()
        self.timeframe_input.setPlaceholderText("e.g. 5m, 15m, 1h")
        self.pairs_input = QLineEdit()
        self.pairs_input.setPlaceholderText("e.g. BTC/USDT, ETH/USDT")
        self.pairs_input.setToolTip("Comma-separated pair list")
        self.max_open_trades_input = QSpinBox()
        self.max_open_trades_input.setMinimum(0)
        self.max_open_trades_input.setMaximum(999)
        self.max_open_trades_input.setToolTip("0 means no limit (depends on bot settings)")

        form.addRow("Strategy", self.strategy_input)
        form.addRow("Timeframe", self.timeframe_input)
        form.addRow("Pairs", self.pairs_input)
        form.addRow("Max open trades", self.max_open_trades_input)

        button_layout = QHBoxLayout()
        self.reload_button = QPushButton("Reload config")
        self.reload_button.clicked.connect(self.reload_bot_config_async)
        self.save_button = QPushButton("Save & reload")
        self.save_button.clicked.connect(self.save_and_reload_async)
        button_layout.addWidget(self.reload_button)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch()

        config_box_layout.addLayout(form)
        config_box_layout.addLayout(button_layout)
        config_box.setLayout(config_box_layout)
        layout.addWidget(config_box)

        trades_box = QGroupBox("Open Trades")
        trades_layout = QVBoxLayout()
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(6)
        self.trades_table.setHorizontalHeaderLabels(["Pair", "Type", "Amount", "Open Rate", "Current Rate", "Profit %"])
        self.trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.refresh_trades_button = QPushButton("Refresh open trades")
        self.refresh_trades_button.clicked.connect(self.refresh_open_trades_async)
        trades_layout.addWidget(self.refresh_trades_button)
        trades_layout.addWidget(self.trades_table)

        trades_box.setLayout(trades_layout)
        layout.addWidget(trades_box)
        self.setLayout(layout)

    def load_current_config_async(self):
        if self._config_load_running:
            return

        self._config_load_running = True
        self.save_button.setEnabled(False)

        def _read_file():
            with open(BOT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)

        worker = Worker(_read_file)

        def _on_result(cfg):
            try:
                if not isinstance(cfg, dict):
                    QMessageBox.critical(self, "Error", "Invalid bot config format (expected JSON object).")
                    return

                self.strategy_input.setText(str(cfg.get('strategy', '')))
                self.timeframe_input.setText(str(cfg.get('timeframe', '')))

                ex = cfg.get('exchange', {})
                if isinstance(ex, dict):
                    pair_whitelist = ex.get('pair_whitelist', [])
                    if not isinstance(pair_whitelist, list):
                        pair_whitelist = []
                    self.pairs_input.setText(", ".join([str(p) for p in pair_whitelist]))
                else:
                    self.pairs_input.setText("")

                mot = cfg.get('max_open_trades', 0)
                try:
                    self.max_open_trades_input.setValue(int(mot))
                except Exception:
                    self.max_open_trades_input.setValue(0)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to parse bot config: {e}")

        def _on_error(msg: str):
            QMessageBox.critical(self, "Error", f"Failed to load bot config: {msg}")

        def _on_finished():
            self._config_load_running = False
            self.save_button.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

    def save_and_reload_async(self):
        if self._save_running:
            return

        self._save_running = True
        self.save_button.setEnabled(False)
        self.reload_button.setEnabled(False)

        strategy = self.strategy_input.text().strip()
        timeframe = self.timeframe_input.text().strip()
        pairs_raw = self.pairs_input.text()
        pairs = [p.strip() for p in pairs_raw.split(',') if p.strip()]
        max_open_trades = int(self.max_open_trades_input.value())

        def _write_file():
            with open(BOT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                raise RuntimeError("Invalid bot config format")

            cfg['strategy'] = strategy
            cfg['timeframe'] = timeframe
            cfg['max_open_trades'] = max_open_trades

            ex = cfg.get('exchange')
            if not isinstance(ex, dict):
                ex = {}
                cfg['exchange'] = ex
            ex['pair_whitelist'] = pairs

            with open(BOT_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=4)

            return True

        worker = Worker(_write_file)

        def _on_result(_ok: bool):
            QMessageBox.information(self, "Success", "Bot config saved. Reloading bot...")
            self.reload_bot_config_async()

        def _on_error(msg: str):
            QMessageBox.critical(self, "Error", f"Failed to save bot config: {msg}")

        def _on_finished():
            self._save_running = False
            self.save_button.setEnabled(True)
            self.reload_button.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

    def reload_bot_config_async(self):
        if self._reload_running:
            return

        self._reload_running = True
        self.reload_button.setEnabled(False)

        worker = Worker(self.client.reload_config)

        def _on_result(result):
            status = None
            if isinstance(result, dict):
                status = result.get('status')
            if status and 'reload' in str(status).lower():
                QMessageBox.information(self, "Success", "Bot configuration reload triggered.")
            else:
                QMessageBox.warning(self, "Warning", f"Could not reload config: {result}")

        def _on_error(msg: str):
            QMessageBox.critical(self, "Error", f"Reload failed: {msg}")

        def _on_finished():
            self._reload_running = False
            self.reload_button.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

    def refresh_open_trades_async(self, silent: bool = False):
        if self._open_trades_running:
            return

        self._open_trades_running = True
        self.refresh_trades_button.setEnabled(False)

        worker = Worker(self.client.get_open_trades)

        def _on_result(open_trades):
            if not isinstance(open_trades, list):
                open_trades = []
            self.trades_table.setRowCount(len(open_trades))
            for row, trade in enumerate(open_trades):
                if not isinstance(trade, dict):
                    trade = {}
                self.trades_table.setItem(row, 0, QTableWidgetItem(str(trade.get('pair', ''))))
                self.trades_table.setItem(row, 1, QTableWidgetItem(str(trade.get('trade_type', ''))))
                self.trades_table.setItem(row, 2, QTableWidgetItem(str(trade.get('amount', ''))))
                self.trades_table.setItem(row, 3, QTableWidgetItem(str(trade.get('open_rate', ''))))
                self.trades_table.setItem(row, 4, QTableWidgetItem(str(trade.get('current_rate', ''))))

                profit_val = trade.get('profit_pct', 0)
                try:
                    profit_val_f = float(profit_val)
                except Exception:
                    profit_val_f = 0.0
                profit_item = QTableWidgetItem(f"{profit_val_f:.4f}")
                if profit_val_f < 0:
                    profit_item.setForeground(Qt.GlobalColor.red)
                else:
                    profit_item.setForeground(Qt.GlobalColor.green)
                self.trades_table.setItem(row, 5, profit_item)

        def _on_error(msg: str):
            logger.warning("Failed to fetch open trades: %s", msg)
            try:
                self.trades_table.setRowCount(0)
            except Exception:
                pass
            if silent:
                return
            QMessageBox.critical(self, "Error", f"Failed to fetch open trades: {msg}")

        def _on_finished():
            self._open_trades_running = False
            self.refresh_trades_button.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)
