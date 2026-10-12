import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta

YEKATERINBURG_TZ = timezone(timedelta(hours=5))

class YekaterinburgFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, YEKATERINBURG_TZ)
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S %Z")

def setup_logger(name: str = "vk_parser") -> logging.Logger:
    os.makedirs("logs", exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        logger.handlers.clear()
        
    formatter = YekaterinburgFormatter("%(asctime)s | %(levelname)-8s | %(message)s")
    
    file_handler = RotatingFileHandler("logs/parser.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logger()