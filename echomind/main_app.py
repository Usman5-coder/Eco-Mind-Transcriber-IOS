import threading
import time
import traceback
from pathlib import Path


def run():
    """
    Import everything lazily inside this function so that
    any import errors are also caught and logged.
    """
    import uvicorn
    from echomind_app.service import app, config
    from echomind_app.ui import TranscriptionUI

    def run_backend():
        """
        Run the FastAPI/uvicorn backend in a background thread.
        """
        port = config.get("control_port", 8766)
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info",
            reload=False,
        )

    # Start backend server in background thread
    backend_thread = threading.Thread(target=run_backend, daemon=True)
    backend_thread.start()

    # Give server a moment to start
    time.sleep(2)

    # Start Tkinter UI in main thread
    ui = TranscriptionUI()
    ui.run()


if __name__ == "__main__":
    # Any crash inside the .app (especially when double-clicked)
    # will be written here:
    error_log = Path.home() / ".echomind" / "launcher_error.log"
    try:
        error_log.parent.mkdir(parents=True, exist_ok=True)
        run()
    except Exception:
        tb = traceback.format_exc()
        try:
            error_log.write_text(tb)
        except Exception:
            # If even logging fails, just re-raise
            pass
        raise