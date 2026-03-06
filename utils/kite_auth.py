# utils/kite_auth.py
import os
from functools import lru_cache

import streamlit as st
from kiteconnect import KiteConnect


def _get_creds() -> tuple[str, str]:
    """
    Return (api_key, access_token) for today.

    Direct mode (local, TRADING_DB_URL set): reads from DB via trading_core.
    HTTP mode (Streamlit Cloud): hits the api_server /kite_token endpoint.

    Raises RuntimeError if trading-login hasn't been run today.
    """
    if os.environ.get("TRADING_DB_URL"):
        try:
            from trading_core.queries import get_kite_token
            creds = get_kite_token()
            if creds:
                return creds["api_key"], creds["access_token"]
        except ImportError:
            pass

    # HTTP path (Streamlit Cloud or trading_core not installed)
    import requests
    api_url = st.secrets["api"]["url"]
    api_token = st.secrets["api"]["token"]
    resp = requests.get(
        f"{api_url}/kite_token",
        headers={"Authorization": f"Bearer {api_token}"},
        timeout=10,
    )
    if resp.status_code == 404:
        raise RuntimeError(
            "No Kite token for today. Run 'trading-login' on your local machine."
        )
    resp.raise_for_status()
    data = resp.json()
    return data["api_key"], data["access_token"]


@lru_cache(maxsize=1)
def get_kite() -> KiteConnect:
    """Singleton KiteConnect client using today's token from the database."""
    api_key, access_token = _get_creds()
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(access_token)
    return kite
