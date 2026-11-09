"""ASGI app: the dashboard (app.py) plus the live preview stream (live.py) on the same server and
port, so anything that reaches the page also reaches the images. Started by `specpol` (cli.py)."""

from pathlib import Path

import streamlit as st

from specpol import live

app = st.App(Path(__file__).with_name("app.py"), routes=live.routes)
