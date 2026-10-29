"""Independent bounded loopback service. No brokerage imports, credentials or order APIs."""
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from threading import BoundedSemaphore, Event, Lock, Thread
import math
import socket
import time
from .schema import Request, dumps, loads
from .provider import MAX_PAYLOAD


class BoundedHTTPServer(ThreadingHTTPServer):
    """Admission precedes handler-thread/body creation. Socket deadlines do not cancel compute."""
    daemon_threads = True

    def __init__(self, address, handler, max_workers, request_timeout):
        super().__init__(address, handler)
        self._slots=BoundedSemaphore(max_workers)
        self._active={};self._lock=Lock();self._stop=Event()
        self.request_timeout=request_timeout
        self.peak_active_requests=0;self.rejected_requests=0
        self._watchdog=Thread(target=self._expire,daemon=True,name='prediction-request-deadlines')
        self._watchdog.start()

    @property
    def active_requests(self):
        with self._lock: return len(self._active)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.rejected_requests+=1
            self.shutdown_request(request)
            return
        with self._lock:
            self._active[request]=time.monotonic()+self.request_timeout
            self.peak_active_requests=max(self.peak_active_requests,len(self._active))
        try: super().process_request(request,client_address)
        except Exception:
            self._release(request)
            raise

    def process_request_thread(self, request, client_address):
        try: super().process_request_thread(request,client_address)
        finally: self._release(request)

    def _release(self, request):
        with self._lock: self._active.pop(request,None)
        self._slots.release()

    @staticmethod
    def _close_socket(request):
        try: request.shutdown(socket.SHUT_RDWR)
        except OSError: pass
        request.close()

    def _expire(self):
        while not self._stop.wait(min(.05,self.request_timeout/4)):
            with self._lock:
                expired=[request for request,deadline in self._active.items() if deadline<=time.monotonic()]
                for request in expired: self._active[request]=math.inf
            for request in expired: self._close_socket(request)
            # Keep admission slots until handlers actually return, including non-cancellable inference.

    def server_close(self):
        self._stop.set()
        with self._lock: active=list(self._active)
        for request in active: self._close_socket(request)
        self._watchdog.join(timeout=.2)
        super().server_close()


def make_server(adapter, host='127.0.0.1', port=8765, max_workers=4, request_timeout=5.):
    if host != '127.0.0.1': raise ValueError("remote exposure is not supported")
    if not isinstance(max_workers,int) or isinstance(max_workers,bool) or not 1<=max_workers<=16:
        raise ValueError('worker bound must be an integer in 1..16')
    if not math.isfinite(request_timeout) or request_timeout<=0: raise ValueError('positive finite request deadline required')
    gate = BoundedSemaphore(1)

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(min(5.,request_timeout))

        def log_message(self, *args): pass

        def reply(self, code, body):
            data = dumps(body).encode()
            try:
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(data)
            except OSError: pass  # absolute deadline may already have closed the socket

        def do_GET(self):
            self.reply(200 if self.path == '/health' else 404, {'simulation_only': True})

        def do_POST(self):
            if self.path != '/forecast': return self.reply(404, {'error': 'not_found'})
            if self.headers.get('Origin') or self.headers.get('Content-Type') != 'application/json':
                return self.reply(400, {'error': 'json_local_clients_only'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_PAYLOAD: return self.reply(413, {'error': 'payload_limit'})
                if self.headers.get('Transfer-Encoding'): raise ValueError('unsupported transfer encoding')
                request = Request.from_dict(loads(self.rfile.read(length)))
            except (ValueError, KeyError, TypeError, OSError):
                return self.reply(400, {'error': 'invalid_request'})
            if not gate.acquire(blocking=False): return self.reply(503, {'error': 'busy'})
            try:
                self.reply(200, adapter.predict(request))
            except Exception:
                self.reply(503, {'error': 'inference_unavailable'})
            finally: gate.release()

    return BoundedHTTPServer((host, port), Handler, max_workers, request_timeout)
