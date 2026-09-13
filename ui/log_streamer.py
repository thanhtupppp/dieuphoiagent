import time
from typing import Callable, List, Dict, Any

class LogStreamer:
    def __init__(self):
        self.logs: List[Dict[str, Any]] = []
        self.subscribers: List[Callable[[Dict[str, Any]], None]] = []

    def subscribe(self, callback: Callable[[Dict[str, Any]], None]):
        self.subscribers.append(callback)

    def push(self, source: str, message: str):
        item = {
            "timestamp": time.strftime("%H:%M:%S"),
            "source": source,
            "message": message
        }
        self.logs.append(item)
        for cb in self.subscribers:
            try:
                cb(item)
            except Exception:
                pass

    def get_recent_logs(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self.logs[-limit:]

    def clear(self):
        self.logs.clear()
