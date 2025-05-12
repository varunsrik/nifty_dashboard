#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May  7 20:46:29 2025

@author: varun
"""

# utils/kite_auth.py
from kiteconnect import KiteConnect
from functools import lru_cache
import streamlit as st
import webbrowser

# 1) -------------------------------------------------------------------------
# Put these three env-vars in ~/.bashrc or export them before running Streamlit
#   KC_API_KEY, KC_API_SECRET, KC_ACCESS_TOKEN
# KC_ACCESS_TOKEN is blank the very first time; you’ll generate it with the CLI below.

API_KEY = st.secrets.get("kite", {}).get("api_key", None)
API_SECRET = st.secrets.get("kite", {}).get("api_secret", None)

# 2) -------------------------------------------------------------------------
def manual_login() -> str:
    """Run this once each morning to generate a fresh access token."""
    kite = KiteConnect(api_key=API_KEY)
    print("Opening Zerodha login…")
    webbrowser.open(kite.login_url())

    req_tok = input("Paste request_token from redirected URL: ").strip()
    sess = kite.generate_session(req_tok, api_secret=API_SECRET)
    print("ACCESS_TOKEN =", sess["access_token"])
    # copy-paste that token into your env var
    return sess["access_token"]


@lru_cache(maxsize=1)
def get_kite() -> KiteConnect:
    """
    Return a singleton KiteConnect client.
    Reads the *current* access token from st.secrets each call,
    so updating secrets + rerunning Streamlit picks up the new token.
    """
    token = st.secrets["kite"]["access_token"]
    if not token:
        raise RuntimeError("access_token empty – run manual_login() and update secrets")

    kite = KiteConnect(api_key=API_KEY)
    kite.set_access_token(token)
    return kite