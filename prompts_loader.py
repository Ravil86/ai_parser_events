import os
from pathlib import Path
from logger_config import logger

class PromptsLoader:
    """Загружает промпты из файлов с кэшированием."""
    
    _cache = {}
    
    @classmethod
    def load_prompt(cls, file: str) -> str:
    #def load_prompt(cls, task: str, file: str) -> str:
        """
        Загружает промпт из файла.
        
        Args:
            #task: Название задачи (например, "event_extraction")
            file: Имя файла (например, "system" или "examples")
            
        Returns:
            Содержимое файла как строка
        """
        cache_key = f"{file}"
        #cache_key = f"{task}/{file}"
        
        # Возвращаем из кэша, если уже загружали
        if cache_key in cls._cache:
            return cls._cache[cache_key]
        
        # Пытаемся загрузить из файла
        file_path = Path(f"prompts/{file}.txt")
        #file_path = Path(f"prompts/{task}/{file}.txt")
        
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8").strip()
                cls._cache[cache_key] = content
                logger.debug(f"📄 Загружен промпт: {file_path}")
                return content
            except Exception as e:
                logger.warning(f"⚠️  Ошибка чтения {file_path}: {e}")
        else:
            logger.debug(f"ℹ️  Файл промпта не найден: {file_path} (используется дефолтный)")
        
        # Дефолтные значения, если файл не найден
        defaults = {
            "system": "Верни JSON с полями: events, name, date, time, location, price_from, price_fixed, description",
            "examples": "",
        }
        
        default_value = defaults.get(cache_key, "")
        cls._cache[cache_key] = default_value
        return default_value
    
    @classmethod
    def get_event_extraction_prompts(cls) -> tuple[str, str]:
        """Возвращает системный промпт и примеры для извлечения событий."""
        system = cls.load_prompt("system")
        examples = cls.load_prompt("examples")
        #system = cls.load_prompt("event_extraction", "system")
        #examples = cls.load_prompt("event_extraction", "examples")
        return system, examples