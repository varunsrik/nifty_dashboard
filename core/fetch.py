#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May  5 10:20:16 2025

@author: varun
"""

# core/fetch.py
import pandas as pd, requests, streamlit as st
from config import API_URL, API_TOKEN, CACHE_SQL_TTL

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