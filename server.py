"""Entry point: `streamlit run server.py` (the `app` script). Runs app.py, plus the live preview
stream (live.py) on the same server and port, so anything that reaches the page also reaches
the images."""

import streamlit as st

import live

app = st.App("app.py", routes=live.routes)
