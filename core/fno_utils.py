#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed May 14 14:09:42 2025

@author: varun
"""

# core/fno_utils.py
import pandas as pd, datetime as dt
from calendar import month_abbr

_INSTR_CSV = "data/instruments.csv"          # same file as collector
_month_map = {m.upper(): i for i, m in enumerate(month_abbr) if m}

# cache the master once
_master = pd.read_csv(_INSTR_CSV)[["tradingsymbol", "expiry"]]
_master["expiry"] = pd.to_datetime(_master["expiry"])

def classify_futures(symbols: list[str]) -> tuple[list[str], list[str], list[str]]:
    """
    Return (front, back, far) lists given *all* available symbols
    that END WITH 'FUT'. Works for index or stock futures.

    Front = nearest expiry ≥ today; Back = next; Far = third.
    """
    today = pd.Timestamp.today().normalize()
    fut = _master[_master.tradingsymbol.isin([s for s in symbols if s.endswith("FUT")])]

    # pick one row per tradingsymbol (duplicates per exchange not expected here)
    fut = fut.groupby("tradingsymbol", as_index=False).first()

    fut = fut[fut["expiry"] >= today].sort_values("expiry")
    unique_expiries = fut["expiry"].drop_duplicates().iloc[:3]     # at most 3
    
    if unique_expiries.empty:
        return [], [], []                          # nothing collected yet


    
    front = fut[fut["expiry"] == unique_expiries.iloc[0]].tradingsymbol.tolist()
    back  = (
        fut[fut["expiry"] == unique_expiries.iloc[1]].tradingsymbol.tolist()
        if len(unique_expiries) > 1 else []
    )
    far   = (
        fut[fut["expiry"] == unique_expiries.iloc[2]].tradingsymbol.tolist()
        if len(unique_expiries) > 2 else []
    )
    return front, back, far


