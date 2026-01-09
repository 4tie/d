"""
AI Strategy Builder tab component
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTextEdit, QMessageBox)

class AIBuilderTab(QWidget):
    """AI Strategy Builder tab"""
    def __init__(self, main_app=None, parent=None):
        super().__init__(parent)
        self.main_app = main_app
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()

        lbl_instruct = QLabel("Describe your strategy (e.g., 'Buy when RSI is < 30'):")
        self.txt_prompt = QTextEdit()
        self.txt_prompt.setPlaceholderText("I want a strategy that buys Bitcoin when...")
        self.txt_prompt.setMaximumHeight(100)

        self.btn_generate = QPushButton("Generate strategy")
        self.btn_generate.clicked.connect(self.on_generate_clicked)
        self.btn_generate.setStyleSheet("background-color: #6200ea; color: white; font-weight: bold; padding: 10px;")

        self.btn_open_settings = QPushButton("Open settings")
        self.btn_open_settings.clicked.connect(self.open_settings)

        self.txt_code_preview = QTextEdit()
        self.txt_code_preview.setPlaceholderText("Generated Python code will appear here...")
        self.txt_code_preview.setReadOnly(False)

        self.btn_save = QPushButton("Save strategy")
        self.btn_save.clicked.connect(self.on_save_clicked)

        self.lbl_status = QLabel("")

        layout.addWidget(lbl_instruct)
        layout.addWidget(self.txt_prompt)
        gen_row = QHBoxLayout()
        gen_row.addWidget(self.btn_generate)
        gen_row.addWidget(self.btn_open_settings)
        layout.addLayout(gen_row)
        layout.addWidget(self.txt_code_preview)
        layout.addWidget(self.btn_save)
        layout.addWidget(self.lbl_status)
        self.setLayout(layout)

    def open_settings(self):
        if hasattr(self.main_app, 'tabs') and hasattr(self.main_app, 'settings_tab'):
            idx = self.main_app.tabs.indexOf(self.main_app.settings_tab)
            if idx >= 0:
                self.main_app.tabs.setCurrentIndex(idx)
    
    def on_generate_clicked(self):
        """Handle generate button click"""
        if self.main_app:
            self.main_app.generate_strategy_logic()
    
    def on_save_clicked(self):
        """Handle save button click"""
        if self.main_app:
            self.main_app.save_strategy()
