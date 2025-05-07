#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May  7 10:59:37 2025

@author: varun
"""

# core/sector.py
import pandas as pd
import streamlit as st

LOOKBACKS = [1, 3, 5, 20, 60, 250]

@st.cache_data(ttl="2h")
def constituent_returns(sector: str,
                        cash_df: pd.DataFrame,
                        idx_df: pd.DataFrame,
                        const_df: pd.DataFrame) -> pd.DataFrame | None:
    """
    Returns a dataframe with 1‑,3‑,5‑,20‑,60‑,250‑day *relative* returns
    for all constituents of the chosen sector.
    If the constituent mapping is unknown, returns None.
    """
    # 1️⃣ constituents list (only for granular equal‑weight sectors)
    if sector in const_df["Sector"].unique():
        symbols = const_df.loc[const_df["Sector"] == sector, "Symbol"].unique()
    else:                     # official Nifty sector index → mapping missing
        return None

    # 2️⃣ build close‑price matrix
    prices = (
        cash_df[cash_df["symbol"].isin(symbols)]
        .pivot(index="date", columns="symbol", values="close")
        .sort_index()
    )

    # 3️⃣ Nifty close series (same date index)
    nifty_close = (
        idx_df[idx_df["symbol"] == "NIFTY 50"]
        .set_index("date")["close"]
        .reindex(prices.index)
    )

    rel_prices = prices.divide(nifty_close, axis=0) * 100

    # 4️⃣ compute look‑back returns
    def pct_ret(series, d):
        if len(series) < d + 1:
            return None
        return round(((series.iloc[-1] / series.iloc[-d-1]) - 1) * 100, 2)

    tbl = {
        sym: [pct_ret(rel_prices[sym].dropna(), d) for d in LOOKBACKS]
        for sym in rel_prices.columns
    }
    return pd.DataFrame(tbl, index=[f"{d}-day" for d in LOOKBACKS]).T