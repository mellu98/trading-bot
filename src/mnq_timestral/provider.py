"""Trading-thread methods never infer or perform network I/O. Transport runs in one bounded worker."""
from collections import Counter
from typing import Protocol
from queue import Queue, Empty, Full
from threading import Thread, Lock, Event
import time
from urllib.parse import urlparse
from urllib.request import Request as URLRequest, urlopen
from .schema import dumps, loads, Prediction

MAX_PAYLOAD = 1024*1024

class PredictionProvider(Protocol):
    """Engine seam: submit/cache only; orders and exits remain outside the prediction service."""
    def submit(self, request) -> bool: ...
    def latest(self, request, now) -> Prediction | None: ...
    def close(self) -> None: ...


class HTTPTransport:
    def __init__(self, url='http://127.0.0.1:8765', timeout=5):
        parsed = urlparse(url)
        if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.username or parsed.password:
            raise ValueError("literal loopback HTTP endpoint required")
        if not 0 < timeout <= 60: raise ValueError("bounded timeout required")
        self.url, self.timeout = url.rstrip('/'), timeout

    def __call__(self, request):
        wire = URLRequest(self.url+'/forecast', dumps(request).encode(), {'Content-Type': 'application/json'})
        with urlopen(wire, timeout=self.timeout) as response:
            data = response.read(MAX_PAYLOAD+1)
        if len(data) > MAX_PAYLOAD: raise ValueError("oversized prediction")
        return Prediction.from_dict(loads(data))


class AsyncPredictionProvider:
    def __init__(self, transport, max_pending=1, backoff_seconds=1, ttl=90):
        if max_pending != 1: raise ValueError("one outstanding request per provider; use one provider per instrument")
        self.transport, self.backoff_seconds, self.ttl = transport, backoff_seconds, ttl
        self._queue, self._lock, self._closed = Queue(maxsize=1), Lock(), Event()
        self._busy, self._cached, self._retry = False, None, 0.
        self.stats = Counter()
        self._thread = Thread(target=self._run, daemon=True, name='prediction-transport')
        self._thread.start()

    def submit(self, request):
        if not self._lock.acquire(blocking=False): return False
        try:
            if self._closed.is_set() or self._busy or time.monotonic() < self._retry: return False
            self._busy, self._cached = True, None
            self._queue.put_nowait(request)
            self.stats['submitted'] += 1
            return True
        finally: self._lock.release()

    def latest(self, request, now):
        if not self._lock.acquire(blocking=False): return None
        try:
            if self._closed.is_set(): return None
            p = self._cached
            if p is None: return None
            if p.request_key != request.key or (now-p.origin).total_seconds() > self.ttl:
                self._cached = None
                return None
            return p if p.valid_for(request, now, self.ttl) else None
        finally: self._lock.release()

    def _run(self):
        while not self._closed.is_set():
            try: request = self._queue.get(timeout=.05)
            except Empty: continue
            try:
                result = self.transport(request)
                if not isinstance(result, Prediction) or result.request_key != request.key:
                    raise ValueError("transport identity mismatch")
                with self._lock:
                    if not self._closed.is_set(): self._cached = result
                    self.stats['completed'] += 1
            except Exception:
                with self._lock:
                    self._cached = None
                    self._retry = time.monotonic()+self.backoff_seconds
                    self.stats['errors'] += 1
            finally:
                with self._lock: self._busy = False
                self._queue.task_done()

    def close(self):
        self._closed.set()
        with self._lock: self._cached = None
        # Never join a potentially stuck transport; daemon cannot hold process shutdown.

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
