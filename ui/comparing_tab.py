"""
Strategy Comparing tab component
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
                             QTextEdit, QSplitter)
from PyQt6.QtCore import Qt
import logging

class ComparingTab(QWidget):
    """Comparing tab for strategy outcomes and restoration"""
    def __init__(self, main_app=None, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Header
        header = QLabel("Strategy Comparison & Version Control")
        header.setStyleSheet("font-size: 18px; font-weight: bold; color: #3b82f6;")
        layout.addWidget(header)

        # Splitter for table and code preview
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Table for results
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Type", "Strategy", "Profit %", "Trades"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)
        
        # Code preview
        self.code_preview = QTextEdit()
        self.code_preview.setReadOnly(True)
        self.code_preview.setPlaceholderText("Select a result to see the strategy code...")
        splitter.addWidget(self.code_preview)
        
        layout.addWidget(splitter)
        
        # Actions
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh Results")
        self.btn_refresh.clicked.connect(self.load_results)
        
        self.btn_restore = QPushButton("Restore to this Strategy")
        self.btn_restore.clicked.connect(self.on_restore_clicked)
        self.btn_restore.setEnabled(False)
        self.btn_restore.setStyleSheet("background-color: #ef4444;")
        
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_restore)
        layout.addLayout(btn_layout)
        
        self.load_results()

    def load_results(self):
        try:
            if not self.main_app or not hasattr(self.main_app, 'strategy_service'):
                return
                
            runs = self.main_app.strategy_service.performance_store.get_recent_runs(limit=20)
            self.table.setRowCount(0)
            self.results_data = {}
            
            for run in runs:
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                run_id = str(run.get("id", ""))
                self.results_data[run_id] = run
                
                self.table.setItem(row, 0, QTableWidgetItem(run_id))
                self.table.setItem(row, 1, QTableWidgetItem(run.get("run_type", "")))
                self.table.setItem(row, 2, QTableWidgetItem(run.get("strategy_class", "N/A")))
                
                summary = run.get("backtest_summary", {})
                profit = summary.get("total_profit_pct", 0)
                trades = summary.get("total_trades", 0)
                
                self.table.setItem(row, 3, QTableWidgetItem(f"{profit:.2f}%"))
                self.table.setItem(row, 4, QTableWidgetItem(str(trades)))
                
        except Exception as e:
            logging.error(f"Error loading results: {e}")

    def _on_selection_changed(self):
        selected = self.table.selectedItems()
        if not selected:
            self.btn_restore.setEnabled(False)
            self.code_preview.clear()
            return
            
        row = selected[0].row()
        run_id = self.table.item(row, 0).text()
        run = self.results_data.get(run_id)
        
        if run:
            self.code_preview.setPlainText(run.get("strategy_code", ""))
            self.btn_restore.setEnabled(True)

    def on_restore_clicked(self):
        selected = self.table.selectedItems()
        if not selected:
            return
            
        row = selected[0].row()
        run_id = self.table.item(row, 0).text()
        run = self.results_data.get(run_id)
        
        if not run:
            return
            
        code = run.get("strategy_code")
        if not code:
            QMessageBox.warning(self, "Error", "No code found for this record.")
            return
            
        reply = QMessageBox.question(self, 'Confirm Restore', 
                                   "This will overwrite AIStrategy.py and create a git commit. Continue?",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Save the code
                self.main_app.strategy_service.save_strategy_code(code, "AIStrategy.py")
                # Attempt git commit (best effort since we can't manage history easily)
                import subprocess
                subprocess.run(["git", "add", "user_data/strategies/AIStrategy.py"], capture_output=True)
                subprocess.run(["git", "commit", "-m", f"Restored strategy from run {run_id}"], capture_output=True)
                
                QMessageBox.information(self, "Success", f"Strategy restored to AIStrategy.py and committed.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to restore: {e}")
