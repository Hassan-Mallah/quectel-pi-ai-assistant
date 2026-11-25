import asyncio
import os
import signal
import sys

from live_session import run_session


async def main():
    stop_event = asyncio.Event()
    sigint_count = 0

    def handle_signal(signum, frame):
        nonlocal sigint_count
        sigint_count += 1
        if sigint_count == 1:
            print("\n[exit]: Stopping gracefully (press Ctrl+C again to force quit)...")
            stop_event.set()
        else:
            print("\n[exit]: Force quitting.", file=sys.stderr)
            os._exit(130)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await asyncio.wait_for(run_session(stop_event), timeout=None)
    except asyncio.CancelledError:
        pass
    finally:
        print("[exit]: Done.")
