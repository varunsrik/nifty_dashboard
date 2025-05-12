#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu May  8 12:26:21 2025

@author: varun
"""

# core/live_zerodha.py
import pandas as pd, streamlit as st, requests, time
from pathlib import Path
from utils.kite_auth import get_kite
import datetime as dt
import numpy as np
from config import CACHE_LIVE_TTL

MASTER_URL   = "https://api.kite.trade/instruments"
MASTER_FILE  = Path("data/instruments.csv")
REFRESH_SECS = 24 * 3600

# ── instrument dump (auto-refresh daily) ───────────────────────────────────
@st.cache_data(ttl=REFRESH_SECS, show_spinner=False)
def instrument_master() -> pd.DataFrame:
    need = (
        not MASTER_FILE.exists()
        or (time.time() - MASTER_FILE.stat().st_mtime) > REFRESH_SECS
    )
    if need:
        MASTER_FILE.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(MASTER_URL, timeout=30)
        r.raise_for_status()
        MASTER_FILE.write_bytes(r.content)
    return pd.read_csv(MASTER_FILE)


@st.cache_data(ttl=CACHE_LIVE_TTL, show_spinner=False)
def live_quotes(symbols: list[str]) -> pd.DataFrame:
    """
    Robust live quote fetch:
    • deterministic token<->symbol mapping via instrument_master
    • drop rows whose live price deviates >30 % from previous close
    """
    master = instrument_master()

    # --- build token list ----------------------------------------------------
    map_df = (
        master.loc[
            (master.exchange == "NSE") &  # cash eq; adjust if you want NFO
            (master.tradingsymbol.isin(symbols)),
            ["instrument_token", "tradingsymbol", "last_price"]
        ]
        .drop_duplicates("tradingsymbol")
    )
    if map_df.empty:
        st.warning("No instrument tokens found for requested symbols.")
        return pd.DataFrame()

    token_list = map_df["instrument_token"].astype(int).tolist()
    token2sym  = dict(zip(map_df["instrument_token"].astype(str), map_df["tradingsymbol"]))

    # --- call Kite quote -----------------------------------------------------
    kite = get_kite()
    quote = kite.quote(token_list)

    rows = []
    for tok_str, data in quote.items():
        sym = token2sym.get(tok_str)
        if sym is None:
            # unknown token – shouldn't happen, but skip defensively
            continue

        ts = pd.to_datetime(data["last_trade_time"])
        live_price  = data["last_price"]
        prev_close  = data["ohlc"]["close"]

        # ---- sanity filter --------------------------------------------------
        if prev_close and abs(live_price - prev_close) / prev_close > 0.30:
            # skip if >30 % away from yesterday's close
            continue

        rows.append(
            dict(
                symbol=sym,
                date=ts.normalize(),
                datetime=ts,
                open=data["ohlc"]["open"],
                high=data["ohlc"]["high"],
                low=data["ohlc"]["low"],
                close=live_price,
                volume=data.get("volume", 0),
            )
        )

    return pd.DataFrame(rows)


# -------------------------------------------------------------------------
@st.cache_data(ttl=CACHE_LIVE_TTL, show_spinner=False)        # one REST hit every 20 s
def live_index_quotes(symbols: list[str]) -> pd.DataFrame:
    """
    Returns dataframe ['symbol','date','close'] with today's live close
    for every index in `symbols` that Zerodha supports.
    """
    kite = get_kite()
    tags = [f"NSE:{s}" for s in symbols]          # e.g. 'NSE:NIFTY 50'
    try:
        q = kite.quote(tags)
    except Exception as e:
        st.warning(f"Index live quote error: {e}")
        return pd.DataFrame()

    rows, today = [], pd.Timestamp.today().normalize()
    for tag, data in q.items():
        sym = tag.split("NSE:")[1]
        rows.append(dict(symbol=sym, date=today, close=data["last_price"]))
    return pd.DataFrame(rows)



@st.cache_data(ttl=CACHE_LIVE_TTL)               # refresh once per minute
def atm_straddle(symbol: str, weekly=False) -> dict | None:
    """
    Return {'strike':int, 'price':float, 'iv':float} for the current-expiry
    ATM straddle of `symbol`. Works for index (NIFTY, BANKNIFTY) & stock F&O.
    """
    
    try:
        
        kite   = get_kite()
        master = instrument_master()
        
        
        # 1️⃣  get live spot price
        
        fut_prices = master[(master['name']==symbol)&
               (master['instrument_type']=='FUT')]
        front_expiry = fut_prices['expiry'].apply(lambda x: dt.datetime.strptime(x, "%Y-%m-%d")).sort_values().iloc[0] + dt.timedelta(hours = 15, minutes = 30)
        tte = (front_expiry - dt.datetime.today()).total_seconds()
        tte_years = tte/(365*24*60*60)
        front_expiry_str = front_expiry.strftime('%Y-%m-%d')
        front_fut_token = str(fut_prices[fut_prices['expiry']==front_expiry_str]['instrument_token'].values[0])
        front_fut_price = kite.quote(front_fut_token)[front_fut_token]['last_price']
    
                    
        if weekly:
            front_fut_price = kite.quote('NSE:NIFTY 50')['NSE:NIFTY 50']['last_price']
            expiry_series = pd.Series(master[(master.name==symbol)
                   &(master.segment=='NFO-OPT')]['expiry'].unique())
            front_weekly_str = expiry_series[expiry_series<front_expiry_str].sort_values().values[0]
            front_weekly = dt.datetime.strptime(front_weekly_str, "%Y-%m-%d")+dt.timedelta(hours = 15, minutes = 30)
            tte = (front_weekly - dt.datetime.today()).total_seconds()
            tte_years = tte/(365*24*60*60)
            opt_chain = master[master.expiry == front_weekly_str]
            
        else:    
            opt_chain = master[(master.name==symbol)
                          &(master.segment=='NFO-OPT')&
                          (master.expiry==front_expiry_str)]
        
        atm_strike_loc = abs(opt_chain[(opt_chain['strike']>=0.98*front_fut_price)&
                  (opt_chain['strike']<=1.02*front_fut_price)
                  ]['strike'].drop_duplicates() - front_fut_price).sort_values().index[0]
        
        atm_strike = opt_chain.loc[atm_strike_loc]['strike']
        
        opt_chain = opt_chain[opt_chain['strike']==atm_strike]
        ce_token  = str(opt_chain[opt_chain['instrument_type']=='CE']['instrument_token'].values[0])
        pe_token  = str(opt_chain[opt_chain['instrument_type']=='PE']['instrument_token'].values[0])
        results = kite.quote([ce_token, pe_token])
        ce_price, pe_price = results[ce_token]['last_price'], results[pe_token]['last_price'] 
        straddle_price = ce_price + pe_price
    
        if weekly:
            front_fut_price = ce_price - pe_price + atm_strike
            
        
        iv = round((100*straddle_price)/(front_fut_price*0.8*np.sqrt(tte_years)), 2)
        
        return {"strike": atm_strike, "price": straddle_price, "iv": iv}

    
    except Exception as e:
        # silently skip illiquid symbols (IDEA etc.) or log if you prefer
        st.warning(f"{symbol}: {e}")
        #return {"strike": None, "price": None, "iv": None}
        
    
