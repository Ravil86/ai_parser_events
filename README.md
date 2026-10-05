# ai_parser_events

vk-events-agent/
├── config.yaml          # Категории и настройки
├── main.py             # Точка входа
├── vk_client.py        # Работа с VK API
├── ai_extractor.py     # Извлечение данных через ИИ
├── models.py           # Модели данных
├── requirements.txt    # Зависимости
└── events_output.json  # Результат (создаётся автоматически)


# Формат файлов со ссылками

# sources/Квизы.txt
ЭЙШТЕЙН ПАТИ | https://vk.ru/einsteinhmansy
ВАУ КВИЗ | https://vk.ru/wowquizhm
МОЗГОБОЙНЯ и ТУЦ ТУЦ | https://vk.ru/mzgb_hm

# sources/Развлечения.txt
Югра-Классик | https://vk.ru/ugraclassic | https://ugraclassic.ru/
Harat's pub | https://vk.ru/harats_hanty

Строки, начинающиеся с # — комментарии (игнорируются)
| — разделитель между названием и ссылками
Можно указывать несколько ссылок на группу (VK + сайт), парсится только VK-ссылка