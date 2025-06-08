#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jun  6 12:06:41 2025

@author: varun
"""

# core/live_scanner.py
import pandas as pd

def scan_prev_expiry_cross(
    reference: pd.DataFrame,
    *,
    live_bars: pd.DataFrame | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    
    """
    Parameters
    ----------
    reference   combined table from Open-Interest tab
                (index = symbol)  must have columns:
                ['cash_close_latest', 'prev_expiry_high', 'prev_expiry_low',
                 'prev_expiry_close']
    live_bars   optional intraday bars (today only).
                If None → use *cash_close_latest* as 'now' price
                (EOD scanner).  If DataFrame → use the **latest minute**
                close for each symbol (live scanner).

    Returns
    -------
    breakout_df  rows that crossed above prev-expiry high OR close *today*
    breakdown_df rows that crossed below prev-expiry low  OR close *today*
    """
       # -------- 1. choose “now” price ----------------------------------------
    if live_bars is None:
        now_price = reference["cash_close_latest"].rename("now_price")
    else:
        now_price = (
            live_bars.sort_values("datetime")
                     .groupby("symbol", as_index=False)
                     .last()[["symbol", "close"]]
                     .set_index("symbol")["close"]
                     .rename("now_price")
        )
       
    joined = reference.join(now_price, how="inner").dropna()
       
    # yesterday’s settle (needed to detect *new* cross)
    prev_price = reference["cash_close_prev"].rename("prev_price")
    joined = joined.join(prev_price, how="inner")


    # -------- 2. conditions -------------------------------------------------
    breakout_close = joined[
        (joined["cash_close_latest"] <= joined["prev_expiry_close"]) &    # was ≤
        (joined["live_close"]          > joined["prev_expiry_close"])].copy()
    
    breakout_high = joined[
        (joined["cash_close_latest"] <= joined["prev_expiry_high"])  &
        (joined["live_close"]          > joined["prev_expiry_high"])
    ].copy()

    breakdown_close = joined[
        (joined["cash_close_latest"] >= joined["prev_expiry_close"]) &    # was ≥
        (joined["live_close"]          < joined["prev_expiry_close"])].copy()
    
    breakdown_low = joined[
        (joined["cash_close_latest"] >= joined["prev_expiry_low"])    &
        (joined["live_close"]          < joined["prev_expiry_low"])
    ].copy()

    return breakout_close, breakout_high, breakdown_close, breakdown_low