"""Streamlit entry point. Placeholder until the compatibility engine and agent exist."""

import streamlit as st

from emerson_agent import __version__

st.set_page_config(page_title="Emerson Hardware Replacement Agent", layout="wide")
st.title("Emerson Hardware Replacement Agent")
st.caption(f"v{__version__} · prototype · synthetic demo data only")
st.info(
    "The replacement workflow is not implemented yet. "
    "See docs/architecture.md for the planned flow."
)
