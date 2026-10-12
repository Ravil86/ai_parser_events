import sys
import threading
from queue import Queue, Empty

class KeyReader:
    def __init__(self):
        self.queue: Queue[str] = Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()
    
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.stop(); return False
    
    def _reader(self):
        if sys.platform == "win32":
            import msvcrt
            while not self._stop.is_set():
                if msvcrt.kbhit():
                    try: self.queue.put(msvcrt.getch().decode("utf-8", errors="ignore").lower())
                    except Exception: pass
        else:
            import select, tty, termios
            fd = sys.stdin.fileno()
            try: old = termios.tcgetattr(fd)
            except termios.error: return
            try:
                tty.setcbreak(fd)
                while not self._stop.is_set():
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        self.queue.put(sys.stdin.read(1).lower())
            finally: termios.tcsetattr(fd, termios.TCSADRAIN, old)
    
    def get(self, timeout: float = 0.05) -> str | None:
        try: return self.queue.get(timeout=timeout)
        except Empty: return None
    def stop(self): self._stop.set()