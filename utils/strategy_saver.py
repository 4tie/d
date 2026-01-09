"""
Strategy file saving utilities
"""
import os
import logging
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
            # Ensure the strategies directory exists
            os.makedirs(STRATEGY_DIR, exist_ok=True)
            
            # Save the file
            file_path = os.path.join(STRATEGY_DIR, filename)
            with open(file_path, "w") as f:
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
