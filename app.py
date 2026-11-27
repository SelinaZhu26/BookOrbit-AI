"""BookOrbit AI - application entry point.

    python app.py            open the app in its own desktop window
                             (pywebview if installed, otherwise your browser)
    python app.py --browser  always use the default web browser
    python app.py --no-open  only start the local server (for tests)

Everything runs locally: the GUI is served from 127.0.0.1, data lives in
data/*.txt, the LLM is the local Ollama server, face models are in models/.
"""
from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bookorbit.app_context import AppContext  # noqa: E402
from bookorbit.config import Config  # noqa: E402
from bookorbit.ui.web import create_app  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="BookOrbit AI")
    ap.add_argument("--browser", action="store_true", help="open in the default browser instead of a window")
    ap.add_argument("--no-open", action="store_true", help="do not open any window")
    ap.add_argument("--port", type=int)
    args = ap.parse_args()

    config = Config()
    if args.port:
        config.port = args.port
    users_file = config.data_dir / "users.txt"
    if not users_file.exists() or users_file.stat().st_size == 0:
        print("No data yet - creating the demo store (python seed.py) ...")
        from seed import seed
        seed(config)

    ctx = AppContext(config)
    ctx.startup()
    app = create_app(ctx)
    url = f"http://{config.host}:{config.port}/"
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    print(f"BookOrbit AI running at {url}")
    print(f"  LLM:  {ctx.llm.status_text()}")
    print(f"  Face: {ctx.biometric.status_text()}")

    server = threading.Thread(target=lambda: app.run(config.host, config.port, threaded=True,
                                                     use_reloader=False), daemon=True)
    server.start()
    time.sleep(0.8)
    if args.no_open:
        server.join()
        return 0
    if not args.browser:
        try:
            import webview  # pywebview: a native desktop window
            webview.create_window("BookOrbit AI", url, width=1360, height=880, min_size=(1100, 700))
            webview.start()
            return 0
        except ImportError:
            print("pywebview is not installed - opening your web browser instead "
                  "(pip install pywebview for a desktop window).")
    webbrowser.open(url)
    try:
        while server.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
