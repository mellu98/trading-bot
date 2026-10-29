from dataclasses import replace
from datetime import timedelta
from threading import Thread
import time
import urllib.request
import json
import pytest
from conftest import prediction
from mnq_timestral.provider import AsyncPredictionProvider, HTTPTransport
from mnq_timestral.service import make_server
from mnq_timestral.schema import dumps


def test_bounded_async_missing_expired_and_failure(req):
    def slow(r): time.sleep(.15); return prediction(r)
    p=AsyncPredictionProvider(slow,max_pending=1)
    start=time.monotonic(); assert p.submit(req)
    assert time.monotonic()-start<.05
    assert not p.submit(req) and p.latest(req,req.origin) is None
    time.sleep(.2)
    assert p.latest(req,req.origin) is not None
    assert p.latest(req,req.origin+timedelta(minutes=3)) is None
    p.close(); assert not p.submit(req) and p.latest(req,req.origin) is None
    q=AsyncPredictionProvider(lambda r: (_ for _ in ()).throw(OSError("offline")),backoff_seconds=.2)
    assert q.submit(req); time.sleep(.05)
    assert q.latest(req,req.origin) is None and not q.submit(req)
    assert q.stats['errors']==1
    q.close()


def test_close_does_not_wait_for_hung_transport(req):
    p=AsyncPredictionProvider(lambda r: time.sleep(1))
    p.submit(req)
    start=time.monotonic(); p.close()
    assert time.monotonic()-start<.1


def test_real_http_local_stub_roundtrip_and_invalid(req):
    class Stub:
        def predict(self,r): return prediction(r)
    server=make_server(Stub(),port=0)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    try:
        p=HTTPTransport(url,timeout=1)(req)
        assert p.request_key==req.key
        for body in [b'{"x":NaN}',b'{}']:
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(urllib.request.Request(url+'/forecast',body,{'Content-Type':'application/json'}))
            assert exc.value.code==400
        with pytest.raises(ValueError): HTTPTransport('https://example.com')
        with pytest.raises(ValueError): make_server(Stub(),host='0.0.0.0')
    finally:
        server.shutdown(); server.server_close(); thread.join()


def test_http_transport_timeout_and_recovery_is_fail_closed(req):
    class Slow:
        def predict(self,r):time.sleep(.2);return prediction(r)
    server=make_server(Slow(),port=0)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    provider=AsyncPredictionProvider(HTTPTransport(f'http://127.0.0.1:{server.server_port}',timeout=.03),backoff_seconds=.1)
    try:
        start=time.monotonic();provider.submit(req)
        assert time.monotonic()-start<.05
        time.sleep(.08)
        assert provider.stats['errors']==1 and provider.latest(req,req.origin) is None
    finally:provider.close();server.shutdown();server.server_close();thread.join()


def test_http_payload_and_browser_origin_rejected(req):
    class Stub:
        def predict(self,r):return prediction(r)
    server=make_server(Stub(),port=0)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/forecast'
    try:
        request=urllib.request.Request(url,dumps(req).encode(),{'Content-Type':'application/json','Origin':'https://example.com'})
        with pytest.raises(urllib.error.HTTPError) as exc:urllib.request.urlopen(request)
        assert exc.value.code==400
        request=urllib.request.Request(url,b'{}',{'Content-Type':'application/json','Content-Length':'1048577'})
        with pytest.raises(urllib.error.HTTPError) as exc:urllib.request.urlopen(request)
        assert exc.value.code==413
    finally:server.shutdown();server.server_close();thread.join()


def test_audit_f4_partial_requests_are_bounded_and_absolute_deadline_recovers(req):
    import socket
    class Stub:
        def predict(self,r):return prediction(r)
    server=make_server(Stub(),port=0,max_workers=2,request_timeout=.2)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    sockets=[]
    try:
        for _ in range(12):
            sock=socket.create_connection(('127.0.0.1',server.server_port),timeout=.5)
            sock.sendall(b'POST /forecast HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: 500\r\n\r\n{')
            sockets.append(sock)
        end=time.monotonic()+.4
        while time.monotonic()<end:
            for sock in sockets:
                try:sock.sendall(b' ')
                except OSError:pass
            assert server.active_requests<=2
            time.sleep(.02)
        assert server.peak_active_requests==2 and server.rejected_requests>=10
        assert server.active_requests==0
        assert HTTPTransport(f'http://127.0.0.1:{server.server_port}',timeout=1)(req).request_key==req.key
    finally:
        for sock in sockets:sock.close()
        server.shutdown();server.server_close();thread.join()


def test_audit_f4_expired_socket_does_not_release_running_compute_slot(req):
    from threading import Event
    entered,release,finished=Event(),Event(),Event()
    class Slow:
        def predict(self,r):entered.set();release.wait(2);return prediction(r)
    server=make_server(Slow(),port=0,max_workers=1,request_timeout=.1)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    def call():
        try:HTTPTransport(f'http://127.0.0.1:{server.server_port}',timeout=1)(req)
        except Exception:pass
        finally:finished.set()
    client=Thread(target=call,daemon=True);client.start()
    try:
        assert entered.wait(1)
        assert finished.wait(.5)  # socket lifetime ends, but compute continues safely
        assert server.active_requests==1
        release.set()
        deadline=time.monotonic()+1
        while server.active_requests and time.monotonic()<deadline:time.sleep(.01)
        assert server.active_requests==0
    finally:release.set();server.shutdown();server.server_close();thread.join();client.join(1)
