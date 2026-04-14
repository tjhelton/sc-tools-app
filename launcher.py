"""SafetyCulture Tools — Desktop Launcher.

Starts the Streamlit server in the background and opens a native desktop window.
Close the window to stop the server.
"""

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


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


def main():
    app_dir = os.path.dirname(os.path.abspath(__file__))
    port = find_free_port()
    url = f"http://localhost:{port}"

    # Start Streamlit server as a background process
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            os.path.join(app_dir, "app", "Home.py"),
            "--server.port",
            str(port),
            "--server.address",
            "localhost",
            "--server.headless",
            "true",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=app_dir,
    )

    try:
        if not wait_for_server(url):
            server.terminate()
            sys.exit("Error: Streamlit server failed to start.")

        # Try native desktop window, fall back to default browser
        try:
            import webview

            webview.create_window(
                "SafetyCulture Tools",
                url,
                width=1280,
                height=900,
                min_size=(800, 600),
            )
            webview.start()
        except Exception:
            import webbrowser

            webbrowser.open(url)
            print(f"SafetyCulture Tools is running at {url}")
            print("Press Ctrl+C to stop.")
            server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()


if __name__ == "__main__":
    main()
