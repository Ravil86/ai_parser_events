import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta

# Часовой пояс Екатеринбург (UTC+5)
YEKATERINBURG_TZ = timezone(timedelta(hours=5))


class YekaterinburgFormatter(logging.Formatter):
    """Форматтер с часовым поясом Екатеринбург."""
    
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, YEKATERINBURG_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def setup_logger(name: str = "vk_parser") -> logging.Logger:
    """Настраивает логгер с записью в файл и ротацией."""
    os.makedirs("logs", exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # DEBUG для подробностей
    
    if logger.handlers:
        logger.handlers.clear()
    
    # Формат с часовым поясом Екатеринбург
    formatter = YekaterinburgFormatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S %Z"
    )
    
    # Файловый хендлер с ротацией
    file_handler = RotatingFileHandler(
        "logs/parser.log", maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Консольный хендлер (для вывода в терминал)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    return logger


logger = setup_logger()