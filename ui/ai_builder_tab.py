"""
AI Strategy Builder tab component
"""
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTextEdit, QMessageBox, QComboBox)

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

        template_row = QHBoxLayout()
        template_row.addWidget(QLabel("Templates:"))
        self.template_combo = QComboBox()
        self.template_combo.addItems([
            "Select a template...",
            "Simple RSI Strategy",
            "EMA Crossover",
            "Bollinger Bands Mean Reversion",
            "MACD with Volume Confirmation"
        ])
        self.template_combo.currentTextChanged.connect(self._on_template_selected)
        template_row.addWidget(self.template_combo, 1)

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
        layout.addLayout(template_row)
        gen_row = QHBoxLayout()
        gen_row.addWidget(self.btn_generate)
        gen_row.addWidget(self.btn_open_settings)
        layout.addLayout(gen_row)
        layout.addWidget(self.txt_code_preview)
        layout.addWidget(self.btn_save)
        layout.addWidget(self.lbl_status)
        self.setLayout(layout)

    def _on_template_selected(self, text):
        templates = {
            "Simple RSI Strategy": "Create a strategy that buys when RSI is below 30 and sells when RSI is above 70. Use 5m timeframe.",
            "EMA Crossover": "Buy when the 20-period EMA crosses above the 50-period EMA. Sell when it crosses below.",
            "Bollinger Bands Mean Reversion": "Buy when price touches the lower Bollinger Band. Sell when it touches the upper band.",
            "MACD with Volume Confirmation": "Buy when MACD line crosses above the signal line and volume is above the 20-period average."
        }
        if text in templates:
            self.txt_prompt.setPlainText(templates[text])

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
