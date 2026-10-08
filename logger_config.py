import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger(name: str = "vk_parser") -> logging.Logger:
    """Настраивает логгер с записью в файл и ротацией."""
    os.makedirs("logs", exist_ok=True)
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Очищаем старые хендлеры, если логгер уже был создан
    if logger.handlers:
        logger.handlers.clear()
        
    # Формат: 2023-10-25 14:30:00 | INFO | Сообщение
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Файловый хендлер с ротацией (макс 5 МБ, хранит 3 старых файла)
    file_handler = RotatingFileHandler(
        "logs/parser.log", maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger

# Глобальный экземпляр логгера
logger = setup_logger()