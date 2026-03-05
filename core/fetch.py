# core/fetch.py
import os
import pandas as pd
import streamlit as st
from app_config import CACHE_SQL_TTL, CACHE_INTRADAY_LIVE_TTL


def _scale_iv_cols(df: pd.DataFrame) -> pd.DataFrame:
    iv_cols = [c for c in df.columns if "iv" in c.lower()]
    if iv_cols:
        df[iv_cols] = df[iv_cols] * 100
    return df


# --- Mode detection ---
# If TRADING_DB_URL is set AND trading_core is installed, use direct DB.
# Otherwise fall back to HTTP (Streamlit Cloud path).
_DIRECT = False
if os.environ.get("TRADING_DB_URL"):
    try:
        from trading_core.queries import (
            get_cash_data as _q_cash,
            get_fno_stock_data as _q_fno,
            get_index_data as _q_index,
            get_fno_index_data as _q_fno_index,
            get_intraday_bars as _q_bars,
            get_intraday_symbols as _q_intraday_syms,
        )
        _DIRECT = True
    except ImportError:
        _DIRECT = False

if not _DIRECT:
    import requests
    _API_URL = st.secrets["api"]["url"]
    _API_TOKEN = st.secrets["api"]["token"]
    _HDR = {"Authorization": f"Bearer {_API_TOKEN}"}


@st.cache_data(show_spinner=False, ttl="6h")
def get_constituents():
    return pd.read_csv("data/nifty_500_constituents.csv")


@st.cache_data(ttl=CACHE_SQL_TTL)
def cash_all():
    if _DIRECT:
        df = _q_cash()
    else:
        resp = requests.post(
            f"{_API_URL}/cash_data", headers=_HDR, json={"symbols": []}
        )
        df = pd.DataFrame(resp.json())
        df["date"] = pd.to_datetime(df["date"])

    symbols = get_constituents()["Symbol"].unique().tolist()
    df = df[df["symbol"].isin(symbols)]
    return df


@st.cache_data(ttl=CACHE_SQL_TTL)
def index_all():
    if _DIRECT:
        df = _q_index(symbol="ALL")
    else:
        resp = requests.post(
            f"{_API_URL}/index_data", headers=_HDR, json={"symbol": "ALL"}
        )
        df = pd.DataFrame(resp.json())
        df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data(ttl=CACHE_SQL_TTL)
def fno_stock_all():
    if _DIRECT:
        df = _q_fno()
    else:
        resp = requests.get(f"{_API_URL}/fno_stock_data", headers=_HDR)
        df = pd.DataFrame(resp.json())
        df["date"] = pd.to_datetime(df["date"])
    df = _scale_iv_cols(df)
    return df


@st.cache_data(ttl=CACHE_SQL_TTL)
def fno_index_all():
    if _DIRECT:
        df = _q_fno_index(symbol="ALL")
    else:
        resp = requests.post(
            f"{_API_URL}/fno_index_data", headers=_HDR, json={"symbol": "ALL"}
        )
        df = pd.DataFrame(resp.json())
        df["date"] = pd.to_datetime(df["date"])
    df = _scale_iv_cols(df)
    return df


@st.cache_data(ttl=CACHE_INTRADAY_LIVE_TTL, show_spinner=False)
def read_intraday(symbols: list[str], days: int = 1) -> pd.DataFrame:
    """Fetch intraday minute bars (empty list = all symbols)."""
    if _DIRECT:
        df = _q_bars(symbols if symbols else None, days)
    else:
        payload = {"symbols": symbols, "days": days}
        r = requests.post(
            f"{_API_URL}/intraday_bars", headers=_HDR, json=payload, timeout=30
        )
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        if not df.empty:
            df["datetime"] = pd.to_datetime(
                df["datetime"], format="ISO8601", errors="coerce"
            )
            df = df.dropna(subset=["datetime"])
    return df


@st.cache_data(ttl=300, show_spinner=False)
def get_intraday_symbols():
    if _DIRECT:
        return _q_intraday_syms()
    r = requests.get(f"{_API_URL}/intraday_symbols", headers=_HDR, timeout=15)
    r.raise_for_status()
    return r.json()
