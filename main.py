#!/usr/bin/env python3
import os
import sys
import yaml
import time
from pathlib import Path
from dotenv import load_dotenv  # ← NEW

from parser import Parser, ParseState
from ui import UI
from input_handler import KeyReader

# Загружаем .env ДО всего остального, чтобы переменные были доступны
load_dotenv()

HELP = """
╔══════════════════════════════════════════════════════════╗
║                   VK EVENTS AGENT                        ║
╠══════════════════════════════════════════════════════════╣
║  SPACE  — пауза / продолжить                             ║
║  S      — старт (если остановлен)                        ║
║  Q      — стоп                                           ║
║  R      — перезапуск с нуля                              ║
║  ESC    — выход                                          ║
╚══════════════════════════════════════════════════════════╝
"""


def load_config(path: str = "config.yaml") -> dict:
    p = Path(path)
    if not p.exists():
        print(f"❌ Файл {path} не найден!")
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Переопределяем секреты из env (env имеет приоритет над config.yaml)
    env_overrides = {
        "vk_token":      "VK_TOKEN",
        "ai_api_key":    "AI_API_KEY",
        "ai_provider":   "AI_PROVIDER",
        "ai_model":      "AI_MODEL",
    }
    for cfg_key, env_key in env_overrides.items():
        env_val = os.getenv(env_key)
        if env_val:
            cfg[cfg_key] = env_val

    return cfg


def main():
    print(HELP)
    print("Нажмите ENTER для запуска агента...")
    input()

    config = load_config()

    # Проверка секретов
    if not config.get("vk_token"):
        print("⚠  ВНИМАНИЕ: VK_TOKEN не задан.")
        print("   Заполните .env файл или установите переменную окружения VK_TOKEN.")
        print("   Получить токен: https://vkhost.github.io/\n")

    if config.get("ai_provider") not in ("ollama", "fallback") and not config.get("ai_api_key"):
        print(f"⚠  AI_API_KEY не задан для провайдера '{config.get('ai_provider')}'.")
        print("   Будет использован fallback-парсер без LLM.\n")

    state = ParseState()
    parser = Parser(config, state)

    with UI(state) as ui, KeyReader() as keys:
        parser.start_parsing()

        try:
            while True:
                ui.update()
                key = keys.get(timeout=0.25)
                if key is None:
                    if state.status in ("done", "stopped"):
                        time.sleep(0.5)
                    continue

                if key in ("\x1b", "q"):  # ESC или Q
                    parser.stop()
                    ui.update()
                    time.sleep(0.3)
                    break
                elif key == " ":
                    if parser.is_paused:
                        parser.resume()
                    else:
                        parser.pause()
                elif key == "s":
                    if state.status in ("idle", "stopped", "done"):
                        parser = Parser(config, state)
                        state.__init__()
                        parser.start_parsing()
                    else:
                        parser.resume()
                elif key == "r":
                    parser.stop()
                    time.sleep(0.3)
                    state.__init__()
                    parser = Parser(config, state)
                    parser.start_parsing()

        except KeyboardInterrupt:
            parser.stop()

    print(f"\n✅ Готово! Событий найдено: {state.events_found}")
    print(f"💾 Результаты сохранены в: {config.get('output_file', 'events_output.json')}")


if __name__ == "__main__":
    main()