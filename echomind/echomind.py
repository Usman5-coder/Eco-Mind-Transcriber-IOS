#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

def kill_other_launchers():
    """
    Kill all EchoMindLauncher processes except the current one.
    """
    try:
        current_pid = os.getpid()

        # Get all PIDs with the name "EchoMindLauncher"
        result = subprocess.run(
            ["pgrep", "-f", "EchoMindLauncher"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        if result.stdout:
            pids = [int(pid) for pid in result.stdout.strip().split("\n")]

            for pid in pids:
                if pid != current_pid:  # Do NOT kill the currently running launcher
                    try:
                        os.kill(pid, 9)
                    except Exception:
                        pass

    except Exception:
        pass


def main():
    # First: Kill all other EchoMindLauncher processes
    kill_other_launchers()

    # Path to *.app/Contents/MacOS/
    macos_dir = Path(sys.argv[0]).resolve().parent

    # EchoMind binary inside .app bundle
    echomind_path = macos_dir / "EchoMind"

    if not echomind_path.exists():
        raise FileNotFoundError(f"EchoMind binary not found at: {echomind_path}")

    # Make sure executable
    echomind_path.chmod(0o755)

    # Launch EchoMind (detached)
    subprocess.Popen(
        [str(echomind_path)],
        cwd=macos_dir,
        start_new_session=True,
    )

    # Exit launcher immediately
    os._exit(0)


if __name__ == "__main__":
    main()
