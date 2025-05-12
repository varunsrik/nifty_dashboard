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
from core.live_zerodha import atm_straddle, get_kite
from typing import Union
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
        if sym.upper() == "NIFTY":   # two rows: weekly & monthly
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
    
    #     # ── live override (optional toggle) ─────────────────────────────
    # if st.session_state.get("use_live"):      # use the sidebar toggle you already have
    #     for sym in idx_tbl.index.tolist() + stk_tbl.index.tolist():
    #         weekly_flag = False
    #         if 'WEEKLY' in sym or 'MONTHLY' in sym:
        
    #             sym_final = sym.replace(" – WEEKLY","").replace(" – MONTHLY","")
    #             if sym == 'NIFTY - WEEKLY':
    #                 weekly_flag = True
    #         else:
    #             sym_final = sym
        
    #         live = atm_straddle(sym_final, weekly = weekly_flag)
    #         if live:
    #             tbl = idx_tbl if sym in idx_tbl.index else stk_tbl
    #             tbl.loc[sym, "Straddle"] = live["price"]
    #             tbl.loc[sym, "IV"]       = live["iv"]

    # return idx_tbl, stk_tbl


        # ── live override (optional toggle) ─────────────────────────────
    if st.session_state.get("use_live"):

        lookbacks = [1, 2, 3, 5]     # mapping to column suffixes
        # helper ------------------------------------------------------
        def recalc_changes(df_src, sym, live_price, live_iv, price_col, iv_col):
            sub = df_src[df_src["symbol"] == sym].sort_values("date")
            closes = sub[price_col].tolist() + [live_price]     # append live
            ivs    = sub[iv_col].tolist()    + [live_iv]

            row = {}
            for lb in lookbacks:
                if len(closes) > lb:
                    row[f"Δ{lb} d %"] = round(((closes[-1] / closes[-lb-1]) - 1) * 100, 2)
                    row[f"Δ{lb} d IV"] = round(ivs[-1] - ivs[-lb-1], 2)
            return row

        # loop all table rows ----------------------------------------
        for sym in idx_tbl.index.tolist() + stk_tbl.index.tolist():

            weekly_flag = "WEEKLY" in sym
            sym_clean   = sym.replace(" – WEEKLY","").replace(" – MONTHLY","")
            live = atm_straddle(sym_clean, weekly=weekly_flag)
            if not live:
                continue

            # choose source dataframe + column names
            if sym in idx_tbl.index:
                tbl      = idx_tbl
                df_src   = idx_df
                price_c  = "front_weekly_straddle_price" if weekly_flag else "front_monthly_straddle_price"
                iv_c     = price_c.replace("price", "iv")
            else:
                tbl      = stk_tbl
                df_src   = stock_df
                price_c  = "front_straddle_price"
                iv_c     = "front_straddle_iv"

            # overwrite latest level
            tbl.loc[sym, "Straddle"] = live["price"]
            tbl.loc[sym, "IV"]       = live["iv"]

            # recompute Δ columns
            delta_vals = recalc_changes(df_src, sym_clean, live["price"], live["iv"],
                                        price_c, iv_c)
            for col, val in delta_vals.items():
                tbl.loc[sym, col] = val

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
    
    
    # ---------- live append ---------------------------------------------
    if st.session_state.get("use_live"):
        live = atm_straddle(sym_clean, weekly=is_weekly)
        if live and live["price"] is not None:
            today = pd.Timestamp.today().normalize()
            new_row = pd.DataFrame(
                {"date": [today], "price": [live["price"]], "iv": [live["iv"]]}
            )
            # overwrite today if already present
            ts = (
            pd.concat([ts[ts["date"] != today], new_row], ignore_index=True)
              .sort_values("date")
              .reset_index(drop=True)
              )

    return ts


index_symbol_dict = {
    "NIFTY":     "NIFTY 50",
    "BANKNIFTY": "NIFTY BANK",
    "FINNIFTY":  "NIFTY FIN SERVICE",
}

def price_timeseries(
    symbol: str,
    start_date: Union[str, pd.Timestamp],
    end_date:   Union[str, pd.Timestamp],
    cash_df: pd.DataFrame,
    idx_df:  pd.DataFrame,
) -> pd.DataFrame:
    """
    Slice price dataframe for [start_date, end_date].

    `cash_df` should be the output of cash_with_live(...),
    so it already contains today's candle when live is on.
    """
    sym_clean = symbol.split(" – ")[0]
    mapped    = index_symbol_dict.get(sym_clean, sym_clean)

    # ---------- index branch -------------------------------------------------
    if mapped in idx_df["symbol"].unique():
        df = idx_df[idx_df["symbol"] == mapped][["date", "close"]].copy()

        # append live index quote if toggle ON
        if st.session_state.get("use_live"):
            kite = get_kite()
            tag  = f"NSE:{mapped}"
            try:
                live_px = kite.quote(tag)[tag]["last_price"]
                today   = pd.Timestamp.today().normalize()
                df = (
                    pd.concat([df[df["date"] != today],
                               pd.DataFrame({"date": [today], "close": [live_px]})],
                              ignore_index=True)
                      .sort_values("date")
                )
            except Exception as e:
                st.warning(f"Live index quote failed for {mapped}: {e}")

    # ---------- stock branch -------------------------------------------------
    else:
        df = cash_df[cash_df["symbol"] == mapped][
            ["date", "open", "high", "low", "close", "volume"]
        ].copy()

    mask = (df["date"] >= start_date) & (df["date"] <= end_date)
    return df.loc[mask].sort_values("date").reset_index(drop=True)