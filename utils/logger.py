"""Structured Logger for Edge Labs Bot
Provides color-coded, file-and-console logging with specific channels.
"""
import os
import logging
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, 'logs')

class ColorFormatter(logging.Formatter):
    """Custom formatter for color-coded console output."""
    COLORS = {
        'DEBUG': '\033[94m',    # Blue
        'INFO': '\033[92m',     # Green
        'WARNING': '\033[93m',  # Yellow
        'ERROR': '\033[91m',    # Red
        'CRITICAL': '\033[1;91m' # Bold Red
    }
    RESET = '\033[0m'
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        # Avoid modifying the original record's levelname permanently for other handlers
        original_levelname = record.levelname
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        
        # ISO timestamp
        record.asctime = datetime.fromtimestamp(record.created).isoformat()
        
        result = super().format(record)
        record.levelname = original_levelname
        return result

class FileFormatter(logging.Formatter):
    def format(self, record):
        record.asctime = datetime.fromtimestamp(record.created).isoformat()
        return super().format(record)

def setup_logger(name: str) -> logging.Logger:
    """Creates a logger with the given name, logging to console and file."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if logger.hasHandlers():
        return logger
        
    os.makedirs(LOG_DIR, exist_ok=True)
    
    # Console Handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(ColorFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    # File Handler
    log_file = os.path.join(LOG_DIR, f"{name}.log")
    fh = logging.FileHandler(log_file, encoding='utf-8')
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(FileFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    
    logger.addHandler(ch)
    logger.addHandler(fh)
    
    return logger

# Pre-configured loggers
TICK_LOGGER = setup_logger('tick')
CANDLE_LOGGER = setup_logger('candle')
ANALYSIS_LOGGER = setup_logger('analysis')
TRADE_LOGGER = setup_logger('trade')
SYSTEM_LOGGER = setup_logger('system')

def get_logger(name: str) -> logging.Logger:
    return setup_logger(name)
