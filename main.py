#!/usr/bin/env python3
import os
import sys
import yaml
import time
import argparse
from pathlib import Path
from dotenv import load_dotenv

from parser import Parser, ParseState
from ui import UI
from input_handler import KeyReader
from logger_config import logger

load_dotenv()

HELP_UI = """
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

    env_overrides = {
        "vk_token": "VK_TOKEN",
        "ai_api_key": "AI_API_KEY",
        "ai_provider": "AI_PROVIDER",
        "ai_model": "AI_MODEL",
    }
    for cfg_key, env_key in env_overrides.items():
        env_val = os.getenv(env_key)
        if env_val:
            cfg[cfg_key] = env_val
    return cfg

def run_daemon_mode(config: dict):
    """Запуск в фоновом режиме без UI."""
    print("🚀 Запуск в фоновом режиме (daemon). Логи пишутся в logs/parser.log")
    logger.info("Агент запущен в фоновом режиме (daemon)")
    
    state = ParseState()
    parser = Parser(config, state)
    
    # Запускаем и ждём завершения (или можно использовать nohup)
    parser.run()
    
    print(f"✅ Фоновая задача завершена. Найдено событий: {state.events_found}")
    logger.info(f"Фоновая задача завершена. Всего событий: {state.events_found}")

def run_ui_mode(config: dict):
    """Запуск с интерактивным интерфейсом."""
    print(HELP_UI)
    print("Нажмите ENTER для запуска агента...")
    input()
    
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


def show_status(config: dict):
    """Выводит текущую статистику фонового процесса без его остановки."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    import os

    console = Console()
    console.print("[bold cyan]📊 Статус VK Events Agent (Фоновый режим)[/]\n")

    # 1. Проверяем, запущен ли процесс
    import subprocess
    result = subprocess.run(['pgrep', '-f', 'main.py'], capture_output=True, text=True)
    pids = result.stdout.strip().split('\n')
    pids = [p for p in pids if p] # убираем пустые
    
    if not pids:
        console.print("[bold red]❌ Процесс НЕ запущен в фоне.[/]\n")
    else:
        console.print(f"[bold green]✅ Процесс запущен (PID: {', '.join(pids)})[/]\n")

    # 2. Читаем состояние из файлов
    state_file = "processed_posts.json"
    output_file = config.get("output_file", "events_output.json")
    log_file = "logs/parser.log"

    layout = Layout()
    layout.split_column(
        Layout(name="stats", size=10),
        Layout(name="recent", size=12),
        Layout(name="logs", size=6)
    )

    # --- Блок статистики ---
    stats_table = Table.grid(expand=True, padding=(0, 2))
    stats_table.add_column("Параметр", style="cyan", width=25)
    stats_table.add_column("Значение", style="white")
    
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            state = json.load(f)
            groups_processed = len(state)
            total_posts = sum(len(posts) for posts in state.values())
            stats_table.add_row("Групп обработано:", str(groups_processed))
            stats_table.add_row("Постов проверено:", str(total_posts))
    except FileNotFoundError:
        stats_table.add_row("Состояние:", "Файл состояния не найден (возможно, первый запуск)")

    layout["stats"].update(Panel(stats_table, title="📈 Прогресс", border_style="blue"))

    # --- Блок последних событий ---
    events_table = Table(expand=True, show_lines=False)
    events_table.add_column("Дата", style="cyan", width=12)
    events_table.add_column("Мероприятие", style="bold white")
    events_table.add_column("Цена", style="yellow", justify="right")
    
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            events = data.get("events", [])[-5:] # Берем последние 5
            for ev in reversed(events):
                price = f"{ev.get('price_fixed')}₽" if ev.get('price_fixed') else (f"от {ev.get('price_from')}₽" if ev.get('price_from') else "—")
                events_table.add_row(ev.get('date', '?'), ev.get('name', '?')[:40], price)
    except FileNotFoundError:
        events_table.add_row("—", "Событий пока не найдено", "—")
        
    layout["recent"].update(Panel(events_table, title="🎯 Последние 5 событий", border_style="green"))

    # --- Блок логов ---
    logs_text = Text()
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_lines = lines[-6:] if len(lines) >= 6 else lines
            logs_text = Text("".join(last_lines), style="dim")
    except FileNotFoundError:
        logs_text = Text("Лог-файл не найден.", style="red dim")
        
    layout["logs"].update(Panel(logs_text, title="📝 Последние строки лога", border_style="yellow"))

    console.print(layout)
    console.print("\n[dim]💡 Совет: Чтобы свернуть интерактивный режим, нажмите Ctrl+Z, затем введите 'bg'.[/]")
    console.print("[dim]💡 Чтобы вернуть его обратно, введите 'fg'.[/]\n")



def main():
    parser_arg = argparse.ArgumentParser(description="VK Events Parser Agent")
    parser_arg.add_argument("--daemon", action="store_true", help="Запуск в фоновом режиме без UI")
    args = parser_arg.parse_args()
    
    config = load_config()

    # Если запрошен статус, показываем и выходим
    if args.status:
        show_status(config)
        return
    
    if not config.get("vk_token"):
        print("⚠ ВНИМАНИЕ: VK_TOKEN не задан. Будет использован fallback или API вернёт ошибку.")
        logger.warning("VK_TOKEN не задан в окружении или config.yaml")

    provider = config.get("ai_provider", "fallback")
    if provider not in ("ollama", "fallback") and not config.get("ai_api_key"):
        print(f"⚠  AI_API_KEY не задан для провайдера '{provider}'.")
        print("   Будет использован fallback-парсер без LLM.\n")

    if args.daemon:
        run_daemon_mode(config)
    else:
        run_ui_mode(config)

if __name__ == "__main__":
    main()