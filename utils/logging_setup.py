import logging
import os
from logging.handlers import RotatingFileHandler

class ColorFormatter(logging.Formatter):
    """Custom formatter to add colors to console logs."""
    
    # ANSI Color Codes
    GREY = "\x1b[38;20m"
    BLUE = "\x1b[34;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"
    
    FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

    FORMATS = {
        logging.DEBUG: GREY + FORMAT + RESET,
        logging.INFO: BLUE + FORMAT + RESET,
        logging.WARNING: YELLOW + FORMAT + RESET,
        logging.ERROR: RED + FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + FORMAT + RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)


def setup_logging(level: int = logging.INFO) -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(base_dir, "data")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "app.log")

    root = logging.getLogger()
    root.setLevel(level)

    for h in list(root.handlers):
        root.removeHandler(h)

    # Use the custom color formatter for console output
    fmt_console = ColorFormatter()
    fmt_file = logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d]: %(message)s")

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(fmt_console)

    fh = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt_file)

    root.addHandler(sh)
    root.addHandler(fh)

    return log_path
