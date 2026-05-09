import copy
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

COLORS = {
    logging.DEBUG:    "\033[94m",
    logging.INFO:     "\033[92m",
    logging.WARNING:  "\033[93m",
    logging.ERROR:    "\033[91m",
    logging.CRITICAL: "\033[95m",
}
RESET = "\033[0m"


class ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        # Copy record so we don't mutate the original (avoids corrupting
        # the plain-text file handler that shares the same LogRecord).
        record = copy.copy(record)
        color = COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{RESET}"
        return super().format(record)

def get_logger(name: str = "jarvis") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(ColorFormatter("[%(asctime)s] %(levelname)s %(message)s", "%H:%M:%S"))
    fh = RotatingFileHandler(LOGS_DIR / "jarvis.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(name)s - %(message)s"))
    logger.addHandler(ch)
    logger.addHandler(fh)
    return logger
