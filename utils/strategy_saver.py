"""
Strategy file saving utilities
"""
import os
import logging
import re
from config.settings import STRATEGY_DIR

logger = logging.getLogger(__name__)

class StrategySaver:
    """Handles saving generated strategies to files"""
    
    @staticmethod
    def save_strategy(code: str, filename: str = "AIStrategy.py") -> bool:
        """
        Save strategy code to the strategies folder
        
        Args:
            code: The strategy code to save
            filename: Name of the file to save (default: AIStrategy.py)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not code:
            return False
            
        try:
            if isinstance(filename, str) and filename.strip() == "AIStrategy.py" and isinstance(code, str):
                if not re.search(r"^\s*class\s+AIStrategy\s*\(", code, flags=re.MULTILINE):
                    pat = re.compile(r"^(\s*class\s+)([A-Za-z_][A-Za-z0-9_]*)(\s*\(.*IStrategy.*\)\s*:)" , re.MULTILINE)
                    matches = list(pat.finditer(code))
                    if len(matches) == 1:
                        m = matches[0]
                        old = m.group(2)
                        if old != "AIStrategy":
                            code = code[: m.start(2)] + "AIStrategy" + code[m.end(2) :]

            # Ensure the strategies directory exists
            os.makedirs(STRATEGY_DIR, exist_ok=True)
            
            # Save the file
            file_path = os.path.join(STRATEGY_DIR, filename)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            
            return True
        except Exception as e:
            logger.exception("Error saving strategy")
            return False
    
    @staticmethod
    def show_save_success(parent=None):
        """Show success message for strategy saving"""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(parent, "Success", "Strategy saved successfully!")
    
    @staticmethod
    def show_save_error(parent=None, error: str = "Failed to save strategy"):
        """Show error message for strategy saving"""
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.critical(parent, "Error", error)
