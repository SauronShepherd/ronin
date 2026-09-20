from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from tools.ai_studio_runtime_smoke import run


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"data":[{"id":"smoke"}]}')

    def do_POST(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"choices":[{"message":{"content":"ok"}}]}')

    def log_message(self, *_args):
        return


def test_runtime_smoke_uses_real_http_transport():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever)
    thread.start()
    try:
        result = run(f"http://127.0.0.1:{server.server_port}", "smoke", 2)
        assert result["status"] == "passed"
    finally:
        server.shutdown()
        thread.join()
