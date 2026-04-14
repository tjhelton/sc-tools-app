"""SafetyCulture Tools — Desktop Launcher.

Starts the Streamlit server in a background thread and opens a native
desktop window. Close the window to stop the app.

Works both in development (python launcher.py) and when bundled as a
standalone executable via PyInstaller.
"""

import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request


def get_app_dir():
    """Return the app root — handles both dev and PyInstaller-bundled modes."""
    if getattr(sys, "frozen", False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


def find_free_port():
    """Find an available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def wait_for_server(url, timeout=120):
    """Poll until the Streamlit server responds or timeout is reached."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except (urllib.error.URLError, OSError):
            time.sleep(0.5)
    return False


def _patch_signal_for_threads():
    """Allow signal.signal() calls from non-main threads to succeed silently.

    Streamlit's bootstrap calls signal.signal() to register handlers, but
    Python only allows that in the main thread.  Since the main thread must
    run the macOS GUI (Cocoa/pywebview), Streamlit runs in a daemon thread
    and would crash with ``ValueError: signal only works in main thread``.

    This patch makes non-main-thread calls a harmless no-op.
    """
    import signal

    _original = signal.signal

    def _safe_signal(signalnum, handler):
        if threading.current_thread() is not threading.main_thread():
            return signal.getsignal(signalnum)
        return _original(signalnum, handler)

    signal.signal = _safe_signal


def run_streamlit_server(app_path, port):
    """Run the Streamlit server (called in a daemon thread)."""
    _patch_signal_for_threads()

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        # PyInstaller bundles Streamlit outside of site-packages, so
        # Streamlit's auto-detection incorrectly sets developmentMode=True.
        # That mode forbids setting server.port, crashing the app on
        # startup.  Force it off.
        "--global.developmentMode=false",
        "--server.port",
        str(port),
        "--server.address",
        "localhost",
        "--server.headless",
        "true",
        "--browser.gatherUsageStats",
        "false",
        "--server.maxUploadSize",
        "200",
        "--theme.primaryColor",
        "#6C63FF",
        "--theme.backgroundColor",
        "#FFFFFF",
        "--theme.secondaryBackgroundColor",
        "#F5F5F5",
        "--theme.textColor",
        "#333333",
        "--theme.font",
        "sans serif",
    ]
    try:
        from streamlit.web.cli import main

        main()
    except SystemExit:
        pass


# Inline HTML shown in the webview while Streamlit is starting up.
_LOADING_HTML = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>SafetyCulture Tools</title>
<style>
  body { margin:0; height:100vh; display:flex; align-items:center;
         justify-content:center; font-family:-apple-system,sans-serif;
         background:#FFFFFF; color:#333; }
  .box { text-align:center; }
  .spinner { width:48px; height:48px; border:4px solid #E0E0E0;
             border-top-color:#6C63FF; border-radius:50%;
             animation:spin .8s linear infinite; margin:0 auto 20px; }
  @keyframes spin { to { transform:rotate(360deg); } }
  h2 { font-weight:500; margin:0 0 8px; }
  p  { color:#888; font-size:14px; margin:0; }
</style></head>
<body><div class="box">
  <div class="spinner"></div>
  <h2>SafetyCulture Tools</h2>
  <p>Starting up &hellip;</p>
</div></body>
</html>
"""


def _navigate_when_ready(window, url, timeout=120):
    """Background thread: wait for Streamlit, then redirect the webview."""
    if wait_for_server(url, timeout):
        window.load_url(url)
    else:
        window.load_html(
            "<html><body style='font-family:sans-serif;padding:40px'>"
            "<h2>Startup Error</h2>"
            "<p>The Streamlit server failed to start. "
            "Please quit and try again.</p></body></html>"
        )


def main():
    app_dir = get_app_dir()
    port = find_free_port()
    url = f"http://localhost:{port}"
    app_path = os.path.join(app_dir, "app", "Home.py")

    # Start Streamlit in a daemon thread so it dies when the main thread exits
    server_thread = threading.Thread(
        target=run_streamlit_server,
        args=(app_path, port),
        daemon=True,
    )
    server_thread.start()

    # Native desktop window — show a loading page immediately so the dock
    # icon settles, then navigate to Streamlit once it is ready.
    try:
        import webview

        window = webview.create_window(
            "SafetyCulture Tools",
            html=_LOADING_HTML,
            width=1280,
            height=900,
            min_size=(800, 600),
        )
        nav_thread = threading.Thread(
            target=_navigate_when_ready,
            args=(window, url),
            daemon=True,
        )
        nav_thread.start()
        webview.start()
    except Exception as exc:
        # webview failed — fall back to the default browser.
        # Log the error so it's visible in Console.app for .app bundles.
        print(f"pywebview unavailable ({exc}); falling back to browser.")
        if not wait_for_server(url):
            sys.exit("Error: Streamlit server failed to start.")
        import webbrowser

        webbrowser.open(url)
        print(f"SafetyCulture Tools is running at {url}")
        print("Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
