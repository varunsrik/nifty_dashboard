#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May  6 11:30:00 2025

@author: varun
"""

# core/straddles.py
import pandas as pd
import streamlit as st
from datetime import timedelta
from core.fetch import fno_stock_all, fno_index_all, cash_all, index_all
     # we already cache both



def _change_cols(df: pd.DataFrame, price_col: str, iv_col: str, pct_price=True):
    """
    Build a 1‑row Series with latest level + 1/2/3/5‑day changes.

    price  → % change
    IV     → absolute change
    """
    df = df.sort_values("date")
    # price % changes
    df["p_Δ1"] = df[price_col].pct_change(1) * 100
    df["p_Δ2"] = df[price_col].pct_change(2) * 100
    df["p_Δ3"] = df[price_col].pct_change(3) * 100
    df["p_Δ5"] = df[price_col].pct_change(5) * 100
    # iv   absolute changes
    df["iv_Δ1"] = df[iv_col].diff(1)
    df["iv_Δ2"] = df[iv_col].diff(2)
    df["iv_Δ3"] = df[iv_col].diff(3)
    df["iv_Δ5"] = df[iv_col].diff(5)

    latest = df.iloc[-1]
    return pd.Series(
        {
            "Straddle": latest[price_col],
            "IV": latest[iv_col],
            "Δ1 d %": latest["p_Δ1"],
            "Δ1 d IV": latest["iv_Δ1"],
            "Δ2 d %": latest["p_Δ2"],
            "Δ2 d IV": latest["iv_Δ2"],
            "Δ3 d %": latest["p_Δ3"],
            "Δ3 d IV": latest["iv_Δ3"],
            "Δ5 d %": latest["p_Δ5"],
            "Δ5 d IV": latest["iv_Δ5"],
        }
    )



@st.cache_data(ttl="1h")
def straddle_tables():
    """
    Returns:
        idx_tbl  – index straddles (weekly, monthly)
        stk_tbl  – stock straddles
    """
    stock_df = fno_stock_all()
    idx_df   = fno_index_all()

    # keep only last ~10 calendar days
    cutoff = max(stock_df["date"].max(), idx_df["date"].max()) - pd.Timedelta(days=10)
    stock_df = stock_df[stock_df["date"] >= cutoff]
    idx_df   = idx_df[idx_df["date"] >= cutoff]

    # ── index side ───────────────────────────────────────────────────────────
    idx_rows = []

    for sym, sub in idx_df.groupby("symbol"):
        sub = sub.copy()
        if sym.upper() == "NIFTY":       # two rows: weekly & monthly
            idx_rows.append(
                _change_cols(
                    sub, "front_weekly_straddle_price", "front_weekly_straddle_iv"
                ).rename("NIFTY – WEEKLY")
            )
            idx_rows.append(
                _change_cols(
                    sub, "front_monthly_straddle_price", "front_monthly_straddle_iv"
                ).rename("NIFTY – MONTHLY")
            )
        else:                            # other indices → only monthly
            if "front_monthly_straddle_price" in sub.columns:
                idx_rows.append(
                    _change_cols(
                        sub, "front_monthly_straddle_price", "front_monthly_straddle_iv"
                    ).rename(sym)
                )

    idx_tbl = pd.DataFrame(idx_rows)

    # ── stock side ───────────────────────────────────────────────────────────
    stk_rows = []
    for sym, sub in stock_df.groupby("symbol"):
        if "front_straddle_price" in sub.columns and "front_straddle_iv" in sub.columns:
            stk_rows.append(
                _change_cols(sub, "front_straddle_price", "front_straddle_iv").rename(sym)
            )
    stk_tbl = pd.DataFrame(stk_rows)

    return idx_tbl, stk_tbl


# ──────────────────────────────────────────────────────────────────────

def straddle_timeseries(symbol: str) -> pd.DataFrame:
    """
    Returns a dataframe with ['date','price'] covering the *current* expiry
    for the requested straddle symbol.

    symbol examples:
        "NIFTY – WEEKLY", "NIFTY – MONTHLY", "BANKNIFTY",
        "RELIANCE", "TCS", ...
    """
    sym_clean = symbol.split(" – ")[0]        # strip WEEKLY / MONTHLY tag
    is_weekly = symbol.endswith("WEEKLY")

    if sym_clean in fno_index_all()["symbol"].unique():
        df = fno_index_all().copy()
        df = df[df["symbol"] == sym_clean]

        price_col  = (
            "front_weekly_straddle_price" if is_weekly
            else "front_monthly_straddle_price"
        )
        expiry_col = (
            "front_weekly_expiry" if is_weekly
            else "front_monthly_expiry"
        )
        iv_col = (
            "front_weekly_straddle_iv" if is_weekly
            else "front_monthly_straddle_iv"
        )
        
    else:                               # stock
        df = fno_stock_all().copy()
        df = df[df["symbol"] == sym_clean]
        price_col  = "front_straddle_price"
        expiry_col = "front_expiry"
        iv_col = "front_straddle_iv"

    if df.empty or price_col not in df.columns:
        return pd.DataFrame(columns=["date", "price"])
    current_expiry = df[expiry_col].max()
    ts = (
      df[df[expiry_col] == current_expiry][["date", price_col, iv_col]]
      .rename(columns={price_col: "price", iv_col: "iv"})
      .sort_values("date")
      .reset_index(drop=True))
    return ts

def price_timeseries(symbol: str, start_date, end_date):
    """
    Return a price dataframe for the symbol covering [start_date, end_date].
    Stocks → cash table, indices → index table. Re-index to keep only window.
    """
    
    index_symbol_dict = {
        'NIFTY': 'NIFTY 50',
        'BANKNIFTY': 'NIFTY BANK',
        'FINNIFTY': 'NIFTY FIN SERVICE'
        }
    
    sym_clean = symbol.split(" – ")[0]
    if sym_clean in list(index_symbol_dict.keys()):
        sym_clean = index_symbol_dict[sym_clean]
        
    if sym_clean in index_all()["symbol"].unique():
        df = index_all()
        df = df[df["symbol"] == sym_clean][["date","close"]]
    else:
        df = cash_all()
        df = df[df["symbol"] == sym_clean]

    mask = (df["date"] >= start_date) & (df["date"] <= end_date)
    return df.loc[mask].copy().sort_values("date")