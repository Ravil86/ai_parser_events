#!/usr/bin/env python3
import os
import sys
import json
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
    """Выводит текущую статистику фонового процесса."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.layout import Layout
    import subprocess

    console = Console()
    console.print("[bold cyan]📊 Статус VK Events Agent[/]\n")

    # Проверяем процесс
    result = subprocess.run(['pgrep', '-f', 'main.py'], capture_output=True, text=True)
    pids = [p for p in result.stdout.strip().split('\n') if p]
    
    if pids:
        console.print(f"[bold green]✅ Процесс запущен (PID: {', '.join(pids)})[/]\n")
    else:
        console.print("[bold yellow]⚠️  Процесс не запущен (показываем последнюю статистику)[/]\n")

    layout = Layout()
    layout.split_column(
        Layout(name="ai_stats", size=12),
        Layout(name="parse_stats", size=8),
        Layout(name="recent", size=10),
        Layout(name="logs", size=6)
    )

    # --- Статистика ИИ ---
    ai_table = Table.grid(expand=True, padding=(0, 2))
    ai_table.add_column("Параметр", style="cyan", width=30)
    ai_table.add_column("Значение", style="white")
    
    try:
        with open("stats.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            ai_stats = data.get("ai_stats", {})
            
            ai_table.add_row("Провайдер:", f"[bold]{ai_stats.get('provider', '?').upper()}[/]")
            ai_table.add_row("Модель:", ai_stats.get('model', '?'))
            ai_table.add_row("Всего вызовов ИИ:", str(ai_stats.get('total_calls', 0)))
            ai_table.add_row("Успешных:", f"[green]{ai_stats.get('successful_calls', 0)}[/]")
            ai_table.add_row("Ошибок:", f"[red]{ai_stats.get('failed_calls', 0)}[/]")
            ai_table.add_row("Fallback (regex):", f"[yellow]{ai_stats.get('fallback_calls', 0)}[/]")
            ai_table.add_row("Среднее время ответа:", f"{ai_stats.get('avg_response_time', 0):.2f}s")
            ai_table.add_row("Событий через ИИ:", f"[bold green]{ai_stats.get('events_found_via_ai', 0)}[/]")
            ai_table.add_row("Событий через fallback:", f"[yellow]{ai_stats.get('events_found_via_fallback', 0)}[/]")
    except FileNotFoundError:
        ai_table.add_row("Статистика:", "Файл stats.json не найден (запустите агент)")

    layout["ai_stats"].update(Panel(ai_table, title="🤖 Статистика работы ИИ", border_style="magenta"))

    # --- Статистика парсинга ---
    parse_table = Table.grid(expand=True, padding=(0, 2))
    parse_table.add_column("Параметр", style="cyan", width=30)
    parse_table.add_column("Значение", style="white")
    
    try:
        with open("stats.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            parse_stats = data.get("parse_stats", {})
            
            parse_table.add_row("Групп обработано:", f"{parse_stats.get('done_groups', 0)} / {parse_stats.get('total_groups', 0)}")
            parse_table.add_row("Постов проверено:", str(parse_stats.get('done_posts', 0)))
            parse_table.add_row("Всего событий найдено:", f"[bold green]{parse_stats.get('events_found', 0)}[/]")
            parse_table.add_row("Ошибок:", f"[red]{parse_stats.get('errors', 0)}[/]")
            parse_table.add_row("Завершено:", data.get('completed_at', '?'))
    except FileNotFoundError:
        parse_table.add_row("Статистика:", "Нет данных")

    layout["parse_stats"].update(Panel(parse_table, title="📈 Статистика парсинга", border_style="blue"))

    # --- Последние события ---
    events_table = Table(expand=True, show_lines=False)
    events_table.add_column("Дата", style="cyan", width=12)
    events_table.add_column("Время", style="cyan", width=8)
    events_table.add_column("Мероприятие", style="bold white")
    events_table.add_column("Место", style="blue")
    events_table.add_column("Цена", style="yellow", justify="right")
    
    try:
        with open(config.get("output_file", "events_output.json"), "r", encoding="utf-8") as f:
            data = json.load(f)
            events = data.get("events", [])[-5:]
            for ev in reversed(events):
                price = f"{ev.get('price_fixed')}₽" if ev.get('price_fixed') else (f"от {ev.get('price_from')}₽" if ev.get('price_from') else "—")
                events_table.add_row(
                    ev.get('date', '?'),
                    ev.get('time', '—'),
                    ev.get('name', '?')[:35],
                    (ev.get('location', '—') or '—')[:15],
                    price
                )
    except FileNotFoundError:
        events_table.add_row("—", "—", "Событий пока не найдено", "—", "—")
        
    layout["recent"].update(Panel(events_table, title="🎯 Последние 5 событий", border_style="green"))

    # --- Логи ---
    logs_text = Text()
    try:
        with open("logs/parser.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
            last_lines = lines[-6:] if len(lines) >= 6 else lines
            logs_text = Text("".join(last_lines), style="dim")
    except FileNotFoundError:
        logs_text = Text("Лог-файл не найден.", style="red dim")
        
    layout["logs"].update(Panel(logs_text, title="📝 Последние строки лога", border_style="yellow"))

    console.print(layout)
    console.print("\n[dim]💡 Команды:[/]")
    console.print("[dim]   • Свернуть интерактивный режим: Ctrl+Z → bg[/]")
    console.print("[dim]   • Развернуть обратно: fg[/]")
    console.print("[dim]   • Подробные логи: tail -f logs/parser.log[/]\n")

def main():
    parser_arg = argparse.ArgumentParser(description="VK Events Parser Agent")
    parser_arg.add_argument("--daemon", action="store_true", help="Запуск в фоновом режиме без UI")
    parser_arg.add_argument("--status", action="store_true", help="Показать статистику фонового процесса")  # ← ДОБАВЬТЕ ЭТУ СТРОКУ
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