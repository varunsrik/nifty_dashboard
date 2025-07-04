#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun 10 14:49:01 2025

@author: varun
"""

# core/basis_screener.py
import pandas as pd, re, streamlit as st
from core.fno_utils import classify_futures          # we wrote this earlier
from core.fetch import read_intraday          # or intraday_pg
from core.preprocess import index_with_live, cash_with_live
from utils.kite_auth import get_kite

def _basis(fut_px, spot_px):
    pts = fut_px - spot_px
    pct = (pts / spot_px) * 100 if spot_px else None
    return round(pts, 2), round(pct, 2) if pct is not None else None

@st.cache_data(ttl=30, show_spinner=False)
def current_basis_table(cash_df, idx_df, fut_bars):
    """
    Returns a dataframe indexed by tradingsymbol with columns:
    spot, front_pts, front_pct, back_pts, … far_pct
    """
    # latest spot for every symbol
    spot_latest = (
        pd.concat([cash_df[["symbol","date","close"]],
                   idx_df[["symbol","date","close"]]])
        .sort_values("date")
        .groupby("symbol", as_index=False)
        .last()
        .set_index("symbol")["close"]
    )
 
    # classify futures
    front, back, far = classify_futures(fut_bars["symbol"].unique().tolist())


    def latest_price(fut_list):
        if not fut_list:
            return pd.Series(dtype=float)
        df = fut_bars[fut_bars["symbol"].isin(fut_list)]
        px = (df.sort_values("datetime")
                .groupby("symbol", as_index=False)
                .last()[["symbol","close"]])
        px["base"] = px["symbol"].str.replace(
    r"\d{2}[A-Z]{3}FUT$", "", regex=True)
        px = px.set_index('base')['close']
        
        return px

    front_px = latest_price(front)
    back_px  = latest_price(back)
    far_px   = latest_price(far)

    tbl = pd.DataFrame({
        "spot": spot_latest,
        "front_px": front_px,
        "back_px":  back_px,
        "far_px":   far_px,
    }).dropna(subset=["front_px"])
    
    
    tbl = tbl.copy()

    # ---- compute basis columns ----------------------------------------
    for label in ["front", "back", "far"]:
        tbl[[f"{label}_pts", f"{label}_pct"]] = (
            tbl.apply(
                lambda r: _basis(r[f"{label}_px"], r["spot"]),
                axis=1,
                result_type="expand"     # ⇦ tells pandas to split tuple → 2 cols
            )
        )
        
    return tbl[[
        "spot",
        "front_pts","front_pct",
        "back_pts","back_pct",
        "far_pts","far_pct"
    ]]

# -------------------------------------------------------------------
def intraday_prices(symbol, fut_bars, spot_bars):
    """Return spot & three future series for plotting."""
    patt = re.compile(rf"^{symbol}\d{{2}}[A-Z]{{3}}FUT$")
    futs = sorted({s for s in fut_bars["symbol"].unique() if patt.match(s)})

    groups = (
        fut_bars[fut_bars["symbol"].isin(futs)]
        .sort_values("datetime")
        .groupby("symbol")
    )
    fut_series = {sym: g.set_index("datetime")["close"] for sym, g in groups}

    spot_series = (
        spot_bars[spot_bars["symbol"] == symbol]
        .sort_values("datetime")
        .set_index("datetime")["close"]
    )

    return spot_series, fut_series

# --------------------------------------------------------------------
def daily_basis_series(symbol: str,
                       cash_df: pd.DataFrame,
                       idx_df: pd.DataFrame,
                       fno_df: pd.DataFrame,
                       months_back: int = 3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns
    -------
    price_df   – OHLC cash prices for the window
    basis_df   – columns ['front_pct','back_pct','far_pct'] indexed by date
    """

    end   = cash_df["date"].max()
    start = end - pd.DateOffset(months=months_back)

    # ---------- spot -------------------------------------------------------
    spot = pd.concat([cash_df, idx_df])
    spot = (spot[(spot["symbol"] == symbol) &
                 (spot["date"].between(start, end))]
            .set_index("date")[["open","high","low","close"]])


    fut_daily = (
    fno_df[
        (fno_df["symbol"] == symbol) &     # exact underlying name
        (fno_df["date"].between(start, end))
    ]
    .set_index("date")[["front_fut_close", "back_fut_close"]]
    )

    # align index and forward-fill any holiday gaps so pct calc works
    aligned = spot.join(fut_daily).ffill()
    
    basis_pct = pd.DataFrame({
        "front_pct": (aligned["front_fut_close"] - aligned["close"]) /
                     aligned["close"] * 100,
        "back_pct":  (aligned["back_fut_close"]  - aligned["close"]) /
                     aligned["close"] * 100,

    })

    return spot, basis_pct