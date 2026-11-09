"""`specpol`: start the dashboard (server.py: app.py + the /live preview stream) with Streamlit."""

import argparse
import os
import sys
from pathlib import Path

from specpol import __version__

# Fixed Streamlit settings, passed as flags so they apply wherever specpol is started from.
STREAMLIT_FLAGS = [
    "--server.headless", "true",  # no browser auto-open on the lab PC
    # Streamlit's telemetry posts an event to an external webhook on every script run.
    "--browser.gatherUsageStats", "false",
]


def main(argv=None):
    p = argparse.ArgumentParser(prog="specpol", description=__doc__)
    p.add_argument("--fake", action="store_true", help="simulated camera (Aravis' fake camera), no hardware needed")
    p.add_argument("--port", type=int, default=8501, help="HTTP port for page and preview stream (default 8501)")
    p.add_argument("--address", help="address to listen on (default: all interfaces)")
    p.add_argument("--version", action="version", version=f"specpol {__version__}")
    args, extra = p.parse_known_args(argv)  # anything else goes to `streamlit run` unchanged
    if args.fake:
        os.environ["SPECPOL_FAKE"] = "1"

    from streamlit.web import cli as stcli

    flags = [*STREAMLIT_FLAGS, "--server.port", str(args.port)]
    if args.address:
        flags += ["--server.address", args.address]
    sys.argv = ["streamlit", "run", str(Path(__file__).with_name("server.py")), *flags, *extra]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
