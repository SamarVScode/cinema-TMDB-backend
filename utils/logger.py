import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

def setup_logger(name: str):
    logger = logging.getLogger(name)
    
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    logger.setLevel(log_level)

    if not logger.handlers:
        # Console handler
        ch = logging.StreamHandler()
        ch_formatter = logging.Formatter('%(levelname)s: %(message)s')
        ch.setFormatter(ch_formatter)
        logger.addHandler(ch)

        # File handler (if logs directory exists)
        os.makedirs("logs", exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        fh = RotatingFileHandler(f"logs/relay_{date_str}.log", maxBytes=10485760, backupCount=5)
        fh_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        fh.setFormatter(fh_formatter)
        logger.addHandler(fh)

    return logger
