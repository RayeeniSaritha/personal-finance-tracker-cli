"""
Web Application Launcher Entry Point for Personal Finance Tracker.
Run `python app.py` to start the Web Server.
"""

from pathlib import Path
import sys

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from web.server import run_web_server

if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_web_server(port=port)
