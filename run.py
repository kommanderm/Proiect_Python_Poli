import os
import subprocess
import sys
from pathlib import Path

from app import socket
from app import app

if __name__ == "__main__":
    # Tests get their own process: they must swap in an in-memory database before `app` is imported.
    # The debug reloader re-runs this file in a child (WERKZEUG_RUN_MAIN), so test once per launch, not per reload.
    if "--skip-tests" not in sys.argv and not os.environ.get("WERKZEUG_RUN_MAIN"):
        tests = subprocess.run([sys.executable, "-m", "tests"], cwd=Path(__file__).resolve().parent)
        if tests.returncode != 0:
            sys.exit("tests failed, server not started (python run.py --skip-tests to start anyway)")
    socket.run(app, debug=True, port=5000, host="0.0.0.0")
