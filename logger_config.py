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
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S %Z")

def setup_logger(name: str = "vk_parser") -> logging.Logger:
    """Настраивает логгер с записью в файл с датой и ротацией."""
    os.makedirs("logs", exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    
    if logger.handlers:
        logger.handlers.clear()
        
    formatter = YekaterinburgFormatter("%(asctime)s | %(levelname)-8s | %(message)s")
    
    # Генерируем имя файла с текущей датой (Екатеринбург), например: 2026-10-13_parse.log
    current_date = datetime.now(YEKATERINBURG_TZ).strftime("%Y-%m-%d")
    log_filename = f"logs/{current_date}_parse.log"
    
    # Файловый хендлер с ротацией (на случай очень долгой работы в один день)
    file_handler = RotatingFileHandler(
        log_filename, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Консольный хендлер (для вывода в терминал)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    logger.addHandler(console_handler)
    
    return logger

# Глобальный экземпляр логгера
logger = setup_logger()