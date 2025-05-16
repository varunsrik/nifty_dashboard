#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May  5 10:20:16 2025

@author: varun
"""

# core/fetch.py
import pandas as pd, requests, streamlit as st
from app_config import API_URL, API_TOKEN, CACHE_SQL_TTL, CACHE_INTRADAY_LIVE_TTL

def _scale_iv_cols(df: pd.DataFrame) -> pd.DataFrame:
    iv_cols = [c for c in df.columns if "iv" in c.lower()]
    if iv_cols:
        df[iv_cols] = df[iv_cols] * 100
    return df


@st.cache_data(show_spinner=False, ttl='6h')
def get_constituents():
    return pd.read_csv("data/nifty_500_constituents.csv")


_HDR = {"Authorization": f"Bearer {API_TOKEN}"}

constituents = get_constituents()
symbols = constituents["Symbol"].unique().tolist()


@st.cache_data(ttl=CACHE_SQL_TTL)
def cash_all():
    resp = requests.post(f"{API_URL}/cash_data", headers=_HDR, json={"symbols":[]})
    df = pd.DataFrame(resp.json())
    df["date"] = pd.to_datetime(df["date"])
    df = df[df['symbol'].isin(symbols)]
    return df

@st.cache_data(ttl=CACHE_SQL_TTL)
def index_all():
    resp = requests.post(f"{API_URL}/index_data", headers=_HDR, json={"symbol":"ALL"})
    df = pd.DataFrame(resp.json())
    df["date"] = pd.to_datetime(df["date"])
    return df

@st.cache_data(ttl=CACHE_SQL_TTL)
def fno_stock_all():
    resp = requests.get(f"{API_URL}/fno_stock_data", headers=_HDR)
    df = pd.DataFrame(resp.json())
    df["date"] = pd.to_datetime(df["date"])
    df = _scale_iv_cols(df) 
    return df


@st.cache_data(ttl=CACHE_SQL_TTL)
def fno_index_all():
    resp = requests.post(f"{API_URL}/fno_index_data", headers=_HDR, json={"symbol": "ALL"})
    df = pd.DataFrame(resp.json())
    df["date"] = pd.to_datetime(df["date"])
    df = _scale_iv_cols(df) 
    return df


_HDR = {"Authorization": f"Bearer {API_TOKEN}"}

@st.cache_data(ttl=CACHE_INTRADAY_LIVE_TTL, show_spinner=False)
def read_intraday(symbols: list[str], days: int = 1) -> pd.DataFrame:
    """
    Fetch intraday minute bars for `symbols` (empty list ⇒ all),
    going `days` calendar days back (default 1).
    """
    payload = {"symbols": symbols, "days": days}
    r = requests.post(f"{API_URL}/intraday_bars", headers=_HDR, json=payload, timeout=30)
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    if not df.empty:
        df["datetime"] = pd.to_datetime(
            df["datetime"],
            format="ISO8601",            # accepts both “2025-05-15 09:34:00”
            errors="coerce"              # and “2025-05-15T09:34:00”
        )
        df = df.dropna(subset=["datetime"])
        
    return df

_HDR = {"Authorization": f"Bearer {API_TOKEN}"}

@st.cache_data(ttl=300, show_spinner=False)   # refresh list every 5 min
def get_intraday_symbols():
    r = requests.get(f"{API_URL}/intraday_symbols", headers=_HDR, timeout=15)
    r.raise_for_status()
    return r.json()          # plain list