import http.server
from queue import Queue
from http.server import ThreadingHTTPServer

server_queue = Queue()


def run(directory, port):
    class CustomHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

    server_address = ("", port)
    httpd = ThreadingHTTPServer(server_address, CustomHandler)
    print(f"Serving HTTP on port {port} from directory '{directory}'...")
    server_queue.put(httpd)
    try:
        httpd.serve_forever()
    except Exception as e:
        print("Server encountered an error:", e)
    finally:
        httpd.server_close()
