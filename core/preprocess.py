#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May  5 10:26:45 2025

@author: varun
"""

# core/preprocess.py
import pandas as pd, streamlit as st, datetime as dt
from app_config import CACHE_LIVE_TTL, CACHE_SQL_TTL
from core.fetch import cash_all, index_all
from core.live_zerodha import live_quotes, live_index_quotes

TODAY = dt.date.today()
TODAY_STR  = TODAY.strftime("%d %b %Y")


    
@st.cache_data(ttl=CACHE_LIVE_TTL)
def cash_with_live(use_live: bool):
    df = cash_all()
    if not use_live:
        return df

    live_df = live_quotes(df["symbol"].unique().tolist())
    if live_df.empty:
        return df

    combined = (
        pd.concat([df, live_df], ignore_index=True)
        .sort_values(["symbol", "date", "datetime"])
        .drop_duplicates(subset=["symbol", "date"], keep="last")
    )
    return combined



@st.cache_data(ttl=CACHE_LIVE_TTL, show_spinner=False)
def index_with_live(use_live: bool) -> pd.DataFrame:
    """
    Historical index data (+today's live close if use_live==True).
    """
    hist = index_all()
    if not use_live:
        return hist

    live_df = live_index_quotes(hist["symbol"].unique().tolist())
    if live_df.empty:
        return hist

    combined = (
        pd.concat([hist[hist["date"] != live_df["date"].iloc[0]], live_df],
                  ignore_index=True)
          .sort_values(["symbol", "date"])
          .reset_index(drop=True)
    )
    return combined


@st.cache_data(ttl=CACHE_LIVE_TTL, show_spinner=False)
def compute_adv_decl(cash_df: pd.DataFrame):
    """
    Return two dataframes:
      1) breadth_df with advancers / decliners / adv_dec_ratio
      2) pct_df with %>EMA20/50/100/200 per day
    """
    work = cash_df.copy().sort_values(["symbol", "date"])

    # EMAs
    for span in (20, 50, 100, 200):
        work[f"ema{span}"] = (
            work.groupby("symbol")["close"].transform(lambda x: x.ewm(span=span).mean())
        )

    cutoff = work["date"].max() - pd.DateOffset(months=3)
    last_12m = work[work["date"] >= cutoff].copy()

    last_12m["direction"] = last_12m.groupby("symbol")["close"].diff()

    breadth = (
        last_12m.groupby("date")["direction"]
        .agg(
            advancers=lambda x: (x > 0).sum(),
            decliners=lambda x: (x < 0).sum(),
        )
        .reset_index()
    )
    breadth["adv_dec_ratio"] = breadth["advancers"] / breadth["decliners"].replace(0, pd.NA)

    pct_above = {}
    for span in (20, 50, 100, 200):
        pct_above[f"above_{span}"] = (
            (last_12m["close"] > last_12m[f"ema{span}"])
            .groupby(last_12m["date"])
            .mean()
            * 100
        )
    pct_df = pd.DataFrame(pct_above)

    return breadth, pct_df



@st.cache_data(ttl=CACHE_LIVE_TTL, show_spinner=False)
def official_sector(idx_df: pd.DataFrame):
    # restrict to 400-day window
    idx_400 = idx_df[idx_df["date"] >= idx_df["date"].max() - pd.Timedelta(days=400)]

    nifty_close = (
        idx_400[idx_400["symbol"] == "NIFTY 50"]
        .set_index("date")["close"]
    )
    
    def rel_series(sym):
        s = idx_400[idx_400["symbol"] == sym].set_index("date")["close"]
        return (s / nifty_close.reindex(s.index)) * 100

    official_syms = (
        idx_400["symbol"].unique().tolist()
    )
    official_syms.remove("NIFTY 50")
    
    rel_official = {sym: rel_series(sym) for sym in official_syms}
    rel_official_df = pd.DataFrame(rel_official)
    
    
    lookbacks = [1, 3, 5, 20, 60, 250]
    
    def pct_return(s, d):
        if len(s) < d+1:
            return None
        return round(((s.iloc[-1] / s.iloc[-d-1]) - 1) * 100,2)
    
    tbl = {
        sym: [pct_return(rel_official_df[sym].dropna(), d) for d in lookbacks]
        for sym in official_syms
    }
    official_table = pd.DataFrame(tbl, index=[f"{d}-day" for d in lookbacks]).T
    
    return rel_official_df, official_table, official_syms



@st.cache_data(ttl=CACHE_LIVE_TTL, show_spinner=False)
def equal_weight_sector(cash_df: pd.DataFrame, const_df: pd.DataFrame, idx_df: pd.DataFrame):
    """
    Returns:
      eq_sector_rel  – dataframe of equal‑weight sector indices vs Nifty
      eq_table       – % returns table (1,3,5,20,60,250‑day)
    """
    lookbacks = [1, 3, 5, 20, 60, 250]

    cash_400 = cash_df[cash_df["date"] >= cash_df["date"].max() - pd.Timedelta(days=400)]
    cash_400 = cash_400.merge(const_df[["Symbol", "Sector"]],
                              left_on="symbol", right_on="Symbol")

    prices = (
        cash_400.pivot(index="date", columns="symbol", values="close")
        .sort_index()
    )
    rets = prices.pct_change().dropna(axis=0, how="all")

    sector_returns = {}
    for sector, syms in const_df.groupby("Sector")["Symbol"]:
        syms = [s for s in syms if s in rets.columns]
        if syms:
            sector_returns[sector] = rets[syms].mean(axis=1)

    sector_rets_df = pd.DataFrame(sector_returns)
    eq_sector_idx   = (1 + sector_rets_df).cumprod() * 100

    nifty_close = idx_df
    nifty_close = (
        nifty_close[nifty_close["symbol"] == "NIFTY 50"]
        .set_index("date")["close"]
    )
    nifty_rets = nifty_close.pct_change().dropna()
    nifty_idx  = (1 + nifty_rets).cumprod() * 100

    eq_sector_rel = eq_sector_idx.divide(nifty_idx, axis=0) * 100

    # lookback table
    def pct_return(s, d):
        if len(s) < d + 1:
            return None
        return round(((s.iloc[-1] / s.iloc[-d-1]) - 1) * 100, 2)

    eq_table = pd.DataFrame({
        sec: [pct_return(eq_sector_rel[sec].dropna(), d) for d in lookbacks]
        for sec in eq_sector_rel.columns
    }, index=[f"{d}-day" for d in lookbacks]).T

    return eq_sector_rel, eq_table



@st.cache_data(ttl=CACHE_LIVE_TTL, show_spinner=False)
def fno_oi_processing(fno_df, cash_df):
    fno_df.sort_values(["symbol", "date"], inplace=True)
  
    latest_date = fno_df['date'].max()
    fno_syms = fno_df[fno_df['date']==latest_date]['symbol'].to_list()
    latest_expiry = fno_df[fno_df['date'] == latest_date]['front_expiry'].mode().iloc[0]
     
     # Previous expiry is the max expiry date before the latest expiry
    prev_expiry = fno_df[fno_df['front_expiry'] < latest_expiry]['front_expiry'].max()
     
     # Filter data for the two expiry dates
    latest_df = fno_df[fno_df['date'] == latest_date].set_index('symbol')
    prev_df = fno_df[fno_df['front_expiry'] == prev_expiry].groupby('symbol').last()
    
    combined = latest_df[['combined_open_interest']].join(
    prev_df[['combined_open_interest']],
    lsuffix='_latest', rsuffix='_prev',
    how='inner'
    ).dropna()
    
    cash_data = cash_df.copy()
    cash_data = cash_data[cash_data["symbol"].isin(fno_syms)]
    
    cash_latest_date = cash_data['date'].sort_values().iloc[-1]
    
    cash_latest = (
    cash_data[cash_data["date"] == cash_latest_date]
    .set_index("symbol")["close"]
    .rename("cash_close_latest")
    )
    
    cash_prev = (
    cash_data[cash_data["date"] == prev_expiry]
    .set_index("symbol")["close"]
    .rename("cash_close_prev")
    )
    
    combined = combined.join([cash_latest, cash_prev]).dropna()

    # --- price & OI % changes using cash closes ---------------------------------
    combined["price_change"] = (
    (combined["cash_close_latest"] / combined["cash_close_prev"]) - 1
    ).mul(100).round(1)
    
    combined["oi_change"] = (
    (combined["combined_open_interest_latest"] /
     combined["combined_open_interest_prev"]) - 1
    ).mul(100).round(1)
     
    # ---------------------------------------------------------------------------
    # 1) Identify the calendar window of the previous expiry
    prev_dates   = fno_df[fno_df["front_expiry"] == prev_expiry]["date"].unique()
    window_start = prev_dates.min()
    window_end   = prev_expiry
    
    
    cash_window = cash_data[
    (cash_data["date"] >= window_start) & (cash_data["date"] <= window_end)
    ]
    
    # high & low of CASH closes within that window
     
    prev_high  =(
    cash_window.groupby("symbol")["close"]
    .max()
    .rename("prev_expiry_high")
    )
    
    
    prev_low = (
    cash_window.groupby("symbol")["close"]
    .min()
    .rename("prev_expiry_low")
    )
    
    # cash close on previous expiry day (already built earlier as `cash_prev`)
    prev_close = cash_prev.rename("prev_expiry_close")
     
     # ---------------------------------------------------------------------------
     # 3) Join these reference prices into combined
    combined = combined.join([prev_high, prev_low, prev_close])
    
    # ---------------------------------------------------------------------------
    # 4) Recompute the price_signal column based on CASH prices
    def classify(row):
        if row["cash_close_latest"] > row["prev_expiry_high"]:
            return "price_above_prev_expiry_high"
        elif row["cash_close_latest"] > row["prev_expiry_close"]:
            return "price_above_prev_expiry_close"
        elif row["cash_close_latest"] < row["prev_expiry_low"]:
            return "price_below_prev_expiry_low"
        elif row["cash_close_latest"] < row["prev_expiry_close"]:
            return "price_below_prev_expiry_close"
        else:
            return None
    
    combined["price_signal"] = combined.apply(classify, axis=1)
    
     # Classify into quadrants
    conditions = [
    (combined['price_change'] > 0) & (combined['oi_change'] > 0),
    (combined['price_change'] < 0) & (combined['oi_change'] > 0),
    (combined['price_change'] > 0) & (combined['oi_change'] < 0),
    (combined['price_change'] < 0) & (combined['oi_change'] < 0),
    ]
    
    
    labels = [
    "OI Up / Price Up",
    "OI Up / Price Down",
    "OI Down / Price Up",
    "OI Down / Price Down"
    ]
    combined['quadrant'] = None
    for cond, label in zip(conditions, labels):
        combined.loc[cond, 'quadrant'] = label
    
    return combined, prev_expiry, latest_expiry, cash_latest_date


@st.cache_data(ttl=CACHE_LIVE_TTL, show_spinner=False)
def stock_explorer_processing(cash_df, choice, fno_df, win_days, nifty_df, prev_expiry):
    price_df = cash_df.copy()
    price_df = price_df[price_df["symbol"] == choice.upper()]
    ind_df = fno_df[fno_df['symbol']==choice.upper()]
    
    
    if price_df.empty:
        st.warning("No price data found for this symbol.")
        st.stop()


    # ----------- prep & filtering -------------------------------------------
    price_df["date"] = pd.to_datetime(price_df["date"])
  
    ind_df["date"] = pd.to_datetime(ind_df["date"])
    
    price_df["deliv_pct_smooth"] = (
    price_df["deliv_pct"]
    .ewm(span=3, adjust=False)
    .mean()
    )

    # window filter
    cutoff = price_df["date"].max() - pd.Timedelta(days=win_days)
    price_df = price_df[price_df["date"] >= cutoff]
    select_nifty_df = nifty_df[nifty_df["date"] >= cutoff]
    ind_df   = ind_df[ind_df["date"] >= cutoff]
        
        
    # ── NEW: enforce strict chronological order & dedup ----------------
    price_df = price_df.sort_values("date").drop_duplicates("date")
    select_nifty_df = select_nifty_df.sort_values("date").drop_duplicates("date")
    # --------------------------------------------------------------------
    sel =  price_df.loc[price_df["date"] == prev_expiry, "close"]
    
        
    if sel.empty:
        prev_close_price = None                # nothing to draw
    else:
        prev_close_price = float(sel.iloc[0])  # take the first value

    # align index close to price dates
    index_series = (
        select_nifty_df.groupby("date")["close"].mean()
        .reindex(price_df["date"])
        .fillna(method="ffill")
    )
    
    # --- rebasing to 100 at window start ------------------------------------
    reb_base_stock  = price_df["close"].iloc[0]
    reb_base_index  = index_series.iloc[0]

    rebased_stock  = (price_df["close"] / reb_base_stock) * 100
    rebased_index  = (index_series / reb_base_index) * 100

 
    return price_df, ind_df, rebased_stock, rebased_index, prev_close_price

