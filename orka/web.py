"""Start the local chat app and open a browser when the server is ready."""
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from .app import create_app
from .settings import load_credentials


def main():
    load_credentials()
    import os
    db = os.environ.get("ORKA_DB", str(Path(__file__).resolve().parent.parent / 'data' / 'orka.sqlite'))
    app = create_app(db)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8010, proxy_headers=False))

    def open_when_ready():
        for _ in range(100):
            if server.started:
                webbrowser.open('http://127.0.0.1:8010/')
                return
            time.sleep(.1)

    threading.Thread(target=open_when_ready, daemon=True).start()
    print('Orka is opening at http://127.0.0.1:8010/ — keep this window open. Ctrl+C stops the server.')
    server.run()


if __name__ == '__main__':
    main()
