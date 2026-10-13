import os
import sys
import atexit


PID_FILE = "parser.pid"


def daemonize():
    """Классическая демонизация процесса (double fork)."""
    
    # === Первый fork ===
    try:
        pid = os.fork()
        if pid > 0:
            # Родительский процесс: печатаем информацию и выходим
            print(f"✅ Агент запущен в фоне (PID: {pid})")
            print(f"📋 Логи:  tail -f logs/*_parse.log")
            print(f"🔍 Статус: python main.py --status")
            print(f"🛑 Стоп:   kill $(cat {PID_FILE})")
            os._exit(0)
    except OSError as e:
        sys.stderr.write(f"Первый fork не удался: {e}\n")
        sys.exit(1)

    # Новая сессия — отрываемся от управляющего терминала
    os.setsid()

    # === Второй fork (гарантия, что процесс не получит терминал) ===
    try:
        pid = os.fork()
        if pid > 0:
            os._exit(0)
    except OSError as e:
        sys.stderr.write(f"Второй fork не удался: {e}\n")
        sys.exit(1)

    # Чистая рабочая среда демона
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.umask(0o022)

    # Перенаправляем stdin/stdout/stderr в /dev/null
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDWR)
    os.dup2(devnull, 0)
    os.dup2(devnull, 1)
    os.dup2(devnull, 2)
    os.close(devnull)

    # Записываем PID и чистим его при выходе
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(PID_FILE) and os.remove(PID_FILE))