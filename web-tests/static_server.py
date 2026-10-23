from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


class ConcurrentStaticServer(ThreadingHTTPServer):
    # Chromium fans out module and stylesheet requests when a page loads.
    request_queue_size = 128


class QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format, *_args):
        pass


if __name__ == "__main__":
    handler = partial(QuietStaticHandler, directory=str(REPOSITORY_ROOT))
    server = ConcurrentStaticServer(("127.0.0.1", 8099), handler)
    server.daemon_threads = True
    server.serve_forever()
