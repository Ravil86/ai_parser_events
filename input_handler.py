import sys
import threading
from queue import Queue, Empty


class KeyReader:
    """Читает клавиши в отдельном потоке без блокировки вывода."""
    
    def __init__(self):
        self.queue: Queue[str] = Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
    
    def __enter__(self):
        """Поддержка контекстного менеджера."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Корректное завершение потока при выходе."""
        self.stop()
        return False
    
    def _reader(self):
        if sys.platform == "win32":
            import msvcrt
            while not self._stop.is_set():
                if msvcrt.kbhit():
                    ch = msvcrt.getch()
                    try:
                        self.queue.put(ch.decode("utf-8", errors="ignore").lower())
                    except Exception:
                        pass
        else:
            import select
            import tty
            import termios
            fd = sys.stdin.fileno()
            try:
                old = termios.tcgetattr(fd)
            except termios.error:
                # stdin не терминал (например, при запуске через cron или пайп)
                return
            try:
                tty.setcbreak(fd)
                while not self._stop.is_set():
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        ch = sys.stdin.read(1).lower()
                        self.queue.put(ch)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old)
    
    def get(self, timeout: float = 0.05) -> str | None:
        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            return None
    
    def stop(self):
        self._stop.set()