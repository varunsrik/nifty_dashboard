#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jun  6 12:06:41 2025

@author: varun
"""

# core/live_scanner.py
import pandas as pd

def scan_prev_expiry_cross(
    live_bars: pd.DataFrame,
    ref_tbl:   pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Parameters
    ----------
    live_bars : intraday bars for *all* cash symbols (today only)
                columns: ['symbol','datetime','close', ...]
    ref_tbl   : table you already build in Open-Interest tab
                must contain ['cash_close_prev', 'prev_expiry_high',
                               'prev_expiry_low', 'prev_expiry_close']

    Returns
    -------
    breakout_df  – rows that have *just crossed above* prev-expiry close/high
    breakdown_df – rows that have *just crossed below* prev-expiry close/low
    """
    # latest minute close for each symbol
    last_tick = (
        live_bars.sort_values("datetime")
                 .groupby("symbol", as_index=False)
                 .last()[["symbol", "close"]]
                 .rename(columns={"close": "live_close"})
    )

    # join with reference prices (prev-expiry metrics)
    joined = last_tick.merge(
        ref_tbl[[
            "cash_close_prev", "prev_expiry_high",
            "prev_expiry_low",  "prev_expiry_close"
        ]],
        left_on="symbol", right_index=True, how="inner"
    )

    # determine yesterday’s relationship to decide “new” cross
    # Assume ref_tbl already has yesterday’s cash_close_latest column
    prev_day = ref_tbl[["cash_close_latest"]]        # yesterday EOD
    joined = joined.merge(prev_day, left_on="symbol", right_index=True)

    # -------- breakout / breakdown flags ----------------------------------
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