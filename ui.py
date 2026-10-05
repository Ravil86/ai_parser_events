from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn
from rich.text import Text
from rich.console import Group

from parser import ParseState


STATUS_STYLES = {
    "idle":    ("⏸  IDLE",     "dim"),
    "running": ("▶  RUNNING",  "bold green"),
    "paused":  ("⏸  PAUSED",   "bold yellow"),
    "stopped": ("⛔ STOPPED",  "bold red"),
    "done":    ("✅ DONE",     "bold cyan"),
}


def build_layout(state: ParseState) -> Layout:
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="stats", size=8),
        Layout(name="progress", size=5),
        Layout(name="events", size=14),
        Layout(name="help", size=3),
    )
    
    # HEADER
    label, style = STATUS_STYLES.get(state.status, ("?", "dim"))
    header = Text(f"  VK EVENTS AGENT  ·  {label}", style=style)
    layout["header"].update(Panel(header, style="bold"))
    
    # STATS
    stats = Table.grid(expand=True, padding=(0, 2))
    stats.add_column(justify="right", style="cyan", width=18)
    stats.add_column(style="white")
    stats.add_row("Категория:", state.current_category or "—")
    stats.add_row("Группа:", state.current_group or "—")
    stats.add_row("Групп обработано:", f"{state.done_groups} / {state.total_groups}")
    stats.add_row("Постов обработано:", str(state.done_posts))
    stats.add_row("Найдено событий:", f"[bold green]{state.events_found}[/]")
    stats.add_row("Ошибок:", f"[red]{state.errors}[/]")
    layout["stats"].update(Panel(stats, title="📊 Статистика", border_style="blue"))
    
    # PROGRESS
    progress = Progress(
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=None),
        TextColumn("[bold]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        expand=True,
    )
    if state.total_groups > 0:
        progress.add_task("Группы", total=state.total_groups, completed=state.done_groups)
    if state.done_posts > 0:
        progress.add_task("Посты", total=max(state.done_posts, state.total_posts),
                         completed=state.done_posts)
    layout["progress"].update(Panel(progress, title="⏳ Прогресс", border_style="cyan"))
    
    # EVENTS
    tbl = Table(expand=True, show_lines=False, row_styles=["", "dim"])
    tbl.add_column("Категория", style="magenta", width=14, no_wrap=True)
    tbl.add_column("Мероприятие", style="bold white", ratio=3)
    tbl.add_column("Дата", style="cyan", width=12)
    tbl.add_column("Цена", style="yellow", width=12, justify="right")
    for e in reversed(state.last_events[-10:]):
        price = f"{e.price_fixed}₽" if e.price_fixed else (f"от {e.price_from}₽" if e.price_from else "—")
        tbl.add_row(e.category, e.name[:60], e.date, price)
    layout["events"].update(Panel(tbl or Text("пока ничего не найдено", style="dim"),
                                  title="🎯 Последние события", border_style="green"))
    
    # HELP
    help_text = Text(
        "  [bold]SPACE[/] — пауза/продолжить  ·  "
        "[bold]S[/] — старт  ·  "
        "[bold]Q[/] — стоп  ·  "
        "[bold]R[/] — перезапуск  ·  "
        "[bold]ESC[/] — выход",
        style="dim",
    )
    layout["help"].update(Panel(help_text, style="bold"))
    
    return layout


class UI:
    def __init__(self, state: ParseState):
        self.state = state
        self.live = Live(
            build_layout(state),
            refresh_per_second=4,
            screen=True,
        )
    
    def __enter__(self):
        self.live.__enter__()
        return self
    
    def __exit__(self, *args):
        self.live.__exit__(*args)
    
    def update(self):
        self.live.update(build_layout(self.state))