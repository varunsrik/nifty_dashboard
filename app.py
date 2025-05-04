import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
import yfinance as yf
import datetime as dt
from pandas.tseries.offsets import BDay   # business day helper
from plotly.subplots import make_subplots


DEFAULT_URL   = "https://1200-2406-7400-c8-ab81-20cf-a4ab-3f6-94c.ngrok-free.app"
DEFAULT_TOKEN = "1391"

API_URL   = st.secrets.get("api", {}).get("url",   DEFAULT_URL)
API_TOKEN = st.secrets.get("api", {}).get("token", DEFAULT_TOKEN)

st.set_page_config(page_title="📊 Market Breadth", layout="wide")

TODAY = dt.date.today()
TODAY_STR  = TODAY.strftime("%d %b %Y")

st.sidebar.title("⚙️ Settings")
USE_LIVE = st.sidebar.toggle("Include live (yfinance) candle", value=False, help="Adds today's bar via yfinance. Turn off to load faster.")

tabs = st.tabs(["📊 Market Breadth", "📈 Open Interest Analysis", "📉 Stock Explorer", "Sectoral Analysis"])




# ---------- util helpers ----------

@st.cache_data(show_spinner=False, ttl='6h')
def get_constituents():
    return pd.read_csv("data/nifty_500_constituents.csv")



def append_live_candle(df: pd.DataFrame, symbol: str, yfin_ticker: str | None = None):
    """
    Take an EOD dataframe (date-indexed) and attempt to
    append today's OHLC/volume candle from yfinance.
    If anything fails, the original df is returned untouched.
    """
    
    if not USE_LIVE:
       return df          
   
    try:
        # do nothing if we already have today's date in our SQL data
        today_ts = pd.Timestamp.today().normalize()
        if today_ts in df["date"].values:
            return df

        tick = yfin_ticker or symbol
        live = yf.download(
            tick, 
            start=TODAY, end=TODAY + BDay(1),
            progress=False, auto_adjust=False, interval="1d"
        )
        if live.empty:
            return df                         # market closed or ticker invalid

        live = live.reset_index()
        live.rename(columns=str.lower, inplace=True)
        live["symbol"] = symbol
        live["date"]   = pd.to_datetime(live["date"])
        live.columns = live.columns.get_level_values(0)

        # yfinance columns: open high low close adj close volume
        # keep only what's needed for each tab
        # merge with original df (avoid duplicates)
        cols_in_common = [c for c in df.columns if c in live.columns]
        df_today = live[cols_in_common]

        df_combined = (
            pd.concat([df, df_today], ignore_index=True)
              .drop_duplicates(subset=["date", "symbol"])
              .sort_values("date")
        )
        return df_combined

    except Exception as e:
        # silent fail → return original EOD dataframe
        print(f"yfinance fetch failed for {symbol}: {e}")
        return df
    
    

# ------------ ONE-TIME bulk pulls (cached) --------------------
@st.cache_data(ttl='6h', show_spinner=True)   
def get_bulk_data():
    hdr = {"Authorization": f"Bearer {API_TOKEN}"}

    cash_400   = requests.post(
        f"{API_URL}/cash_data",
        headers=hdr,
        json={"symbols": []}          # empty list → API returns *all* symbols
    ).json()
    cash_df = pd.DataFrame(cash_400)
    cash_df["date"] = pd.to_datetime(cash_df["date"])

    idx_400 = requests.post(
        f"{API_URL}/index_data",
        headers=hdr,
        json={"symbol": "ALL"}        # implement "ALL" to return all index rows
    ).json()
    idx_df  = pd.DataFrame(idx_400)
    idx_df["date"] = pd.to_datetime(idx_df["date"])

    fno_400 = requests.get(f"{API_URL}/fno_data", headers=hdr).json()
    fno_df  = pd.DataFrame(fno_400)
    fno_df["date"] = pd.to_datetime(fno_df["date"])

    return cash_df, idx_df, fno_df

cash_df, idx_df, fno_df = get_bulk_data()


@st.cache_data(ttl=900)            # 15 min cache; keyed by USE_LIVE
def build_cash_df(use_live: bool):
    df = cash_df.copy()            # cash_df came from get_bulk_data()

    if not use_live:
        return df                  # just SQL snapshot

    # ─ add today's candle for every Nifty‑500 symbol ───────────
    frames = []
    for sym in get_constituents()["Symbol"].unique():
        df_sym = df[df["symbol"] == sym]
        frames.append(
            append_live_candle(
                df_sym,
                symbol=sym,
                yfin_ticker=sym + ".NS",
            )
        )
    df_live = pd.concat(frames, ignore_index=True)
    df_live.sort_values(["symbol", "date"], inplace=True)
    return df_live


# ---------- Market Breadth tab ----------
with tabs[0]:
    st.header(f"📊 Market Breadth — {TODAY_STR}")

    constituents = get_constituents()
    symbols = constituents["Symbol"].unique().tolist()
    data = cash_df[cash_df['symbol'].isin(symbols)]
    if data.empty:
        st.warning("No cash data returned.")
        st.stop()
    data["date"] = pd.to_datetime(data["date"]) 
    
    
    
    # add today's candle for every symbol (loop once; still < 5 s)
    data = build_cash_df(USE_LIVE)           
 
    # --- compute advance‑decline & EMA stats ---

    # 20/50/100/200‑day EMAs
    for span in (20, 50, 100, 200):
        data[f"ema{span}"] = (
            data.groupby("symbol")["close"].transform(lambda x: x.ewm(span=span).mean())
        )

    # latest 12‑month window
    cutoff = data["date"].max() - pd.DateOffset(months=12)
    data_12m = data[data["date"] >= cutoff]

    # 1️⃣  Advance/Decline counts for each day
    data_12m["direction"] = data_12m.groupby("symbol")["close"].diff()
    breadth = (
        data_12m.groupby("date")["direction"]
        .agg(
            advancers=lambda x: (x > 0).sum(),
            decliners=lambda x: (x < 0).sum(),
        )
        .reset_index()
    )
    breadth["adv_dec_ratio"] = breadth["advancers"] - breadth["decliners"].replace(0, pd.NA)
    
    # 2️⃣  % of stocks above each EMA per day
    pct_above = {}
    for span in (20, 50, 100, 200):
        pct = (
            (data_12m["close"] > data_12m[f"ema{span}"])
            .groupby(data_12m["date"])
            .mean()
            * 100
        )
        pct_above[f"above_{span}"] = pct

    pct_df = pd.DataFrame(pct_above)

    # --- Plotly figure ---
    fig = go.Figure()

    # secondary axis for EMA percentages
    for span, col in zip((20, 50, 100, 200), pct_df.columns):
        fig.add_trace(go.Scatter(
            x=pct_df.index, y=pct_df[col],
            name=f"%> EMA{span}", mode="lines", line=dict(width=1, dash="dot")
        ))

    fig.update_layout(
        title="Market Breadth – last 12 months",
        yaxis_title="Percentage above EMAs",
        yaxis2=dict(
            title="% Above EMA",
            overlaying="y",
            side="right",
            showgrid=False,
        ),
        legend=dict(orientation="h"),
        height=450,
        margin=dict(t=50, b=20, l=20, r=20)
    )

    st.plotly_chart(fig, use_container_width=True)
    
    fig_ratio = go.Figure()
    fig_ratio.add_trace(
        go.Scatter(
            x=breadth["date"],
            y=breadth["adv_dec_ratio"],
            mode="lines",
            line=dict(width=2),
            name="Advance‑Decline Ratio",
        )
    )
    fig_ratio.update_layout(
        title="Advance‑Decline Ratio – last 12 months",
        yaxis_title="A/D Ratio",
        height=350,
        margin=dict(t=50, b=20, l=20, r=20),
        showlegend=False,
    )
    st.plotly_chart(fig_ratio, use_container_width=True)
                    


with tabs[1]:
    st.header(f"📈 Open Interest Analysis — {TODAY_STR}")
    
    fno_df['date'] = pd.to_datetime(fno_df['date'])
    fno_df.sort_values(["symbol", "date"], inplace=True)
  
    latest_date = fno_df['date'].max()
    fno_syms = fno_df[fno_df['date']==latest_date]['symbol'].to_list()
    latest_expiry = fno_df[fno_df['date'] == latest_date]['front_expiry'].mode().iloc[0]
     
     # Previous expiry is the max expiry date before the latest expiry
    prev_expiry = fno_df[fno_df['front_expiry'] < latest_expiry]['front_expiry'].max()
     
    st.write(f"Latest Expiry: {latest_expiry}| Previous Expiry Type: {prev_expiry}")
     
     # Filter data for the two expiry dates
    latest_df = fno_df[fno_df['date'] == latest_date].set_index('symbol')
    prev_df = fno_df[fno_df['front_expiry'] == prev_expiry].groupby('symbol').last()
    
    combined = latest_df[['combined_open_interest']].join(
    prev_df[['combined_open_interest']],
    lsuffix='_latest', rsuffix='_prev',
    how='inner'
    ).dropna()
    
    #cash_data = data[data['symbol'].isin(fno_syms)]      
    
    cash_data = build_cash_df(USE_LIVE)
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
    
     # ---------------------------------------------------------------------------

    
     # 2) Pull CASH OHLC for all symbols over that window
    symbols_needed = combined.index.tolist()      # the same symbols present in combined
    
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
            return "price_below_prev_exp_low"
        elif row["cash_close_latest"] < row["prev_expiry_close"]:
            return "price_below_prev_exp_close"
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
    
    # Show each quadrant
    for label in labels:
        st.subheader(label)
        st.dataframe(combined[combined['quadrant'] == label][[
        'cash_close_prev', 'cash_close_latest', 'price_change',
        'combined_open_interest_prev', 'combined_open_interest_latest', 'oi_change', 'price_signal'
        ]].sort_values('price_change', ascending=False))
        
    
    labels = ['price_above_prev_expiry_high', 'price_below__prev_expiry_low', 'price_above_prev_expiry_close', 'price_below_prev_expiry_close']
    
    for label in labels:
        label_str = label.replace('_', ' ').replace('prev', 'previous').title()
        st.subheader(label_str)
        st.dataframe(combined[combined['price_signal']==label])


# ----------------------------------------------------------------- Stock Explorer

with tabs[2]:
    st.header(f"📉 Stock Explorer — {TODAY_STR}")
    
    nifty500_syms = get_constituents()["Symbol"].unique().tolist()
    
    nifty_df = idx_df[idx_df['symbol']=='NIFTY 50']
    nifty_df["date"]  = pd.to_datetime(nifty_df["date"])
    
    latest_date = fno_df['date'].max()
    fno_syms = fno_df[fno_df['date']==latest_date]['symbol'].to_list()
    #fno_syms      = get_fno_symbols()
    all_syms      = sorted(set(nifty500_syms) | set(fno_syms))
        
    choice        = st.selectbox("Choose a stock", all_syms, index=all_syms.index("RELIANCE") if "RELIANCE" in all_syms else 0)

    # window slider (radio buttons)
    win_label = st.radio("Select window", ["1 M", "3 M", "6 M", "12 M", "All"], horizontal=True)

    win_map = {"1 M": 30, "3 M": 90, "6 M": 180, "12 M": 365, "All": 400}
    win_days = win_map[win_label]


    #price_df = cash_df[cash_df['symbol']==choice.upper()]
    
    price_df = build_cash_df(USE_LIVE)
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
    
    prev_close_price = price_df.loc[price_df["date"] == prev_expiry, "close"].squeeze()

    # align index close to price dates
    index_series = (
        select_nifty_df.groupby("date")["close"].mean()
        .reindex(price_df["date"])
        .fillna(method="ffill")
    )
    
    st.write(price_df)
    st.write(index_series)

    # --- rebasing to 100 at window start ------------------------------------
    reb_base_stock  = price_df["close"].iloc[0]
    reb_base_index  = index_series.iloc[0]

    rebased_stock  = (price_df["close"] / reb_base_stock) * 100
    rebased_index  = (index_series / reb_base_index) * 100

    # ----------- build Plotly figure ----------------------------------------
    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        specs=[[{"secondary_y": False}],
               [{"secondary_y": False}],
               [{"secondary_y": False}],
               [{"secondary_y": True}]],
        # ←  raise the spacing + tweak height ratios
        vertical_spacing = 0.07,          # was 0.03
        row_heights = [0.45, 0.25, 0.15, 0.15]
    )
    # Row-1: Candlestick
    fig.add_trace(
        go.Candlestick(
            x=price_df["date"],
            open=price_df["open"], high=price_df["high"],
            low=price_df["low"], close=price_df["close"],
            name=f"{choice} Candles",
            increasing_line_color="green", decreasing_line_color="red",
            showlegend=False
        ),
        row=1, col=1
    )
    

    # Row-2: rebased close lines
    fig.add_trace(
        go.Scatter(x=price_df["date"], y=rebased_stock,
                   name=f"{choice} (Rebased 100)", mode="lines"),
        row=2, col=1
    )
    fig.add_trace(
        go.Scatter(x=price_df["date"], y=rebased_index,
                   name="Nifty (Rebased 100)", mode="lines", line=dict(dash="dot")),
        row=2, col=1
    )
    
    fig.add_hline(
    y=prev_close_price,
    line_dash="dash",
    line_color="orange",
    annotation_text="Prev Expiry Close",
    annotation_position="top left",
    row=1, col=1
    )
    
    # remove Sat/Sun gaps + any other blank days
    fig.update_xaxes(
        rangebreaks=[
            dict(bounds=["sat", "mon"]),           # hide weekends
            dict(values=pd.date_range("1900-01-01", "2100-01-01", freq="C")
                         .difference(price_df["date"]))  # hide missing trading days
        ]
    )

    fig.update_yaxes(title_text="Rebased Price", row=2, col=1)
    fig.update_xaxes(rangeslider_visible=False)   # ← hides Plotly’s default slider

    # Row-3: Combined OI (if available)
    if not ind_df.empty:
        fig.add_trace(
            go.Bar(x=ind_df["date"], y=ind_df["combined_open_interest"],
                   name="Combined OI", marker_color="blue"),
            row=3, col=1
        )
        fig.update_yaxes(title_text="Open Interest", row=3, col=1)
    else:
        fig.add_annotation(text="No F&O data",
                           xref="paper", yref="paper",
                           x=0.02, y=0.12, showarrow=False)

  
    
    fig.add_trace(
    go.Scatter(
        x=price_df["date"],
        y=price_df["deliv_pct_smooth"],
        name="Delivery %",
        mode="lines",
        line=dict(width=2, color="purple", dash="dot"),
    ),
    row=4, col=1, secondary_y=True
    )
    
    colors = price_df["close"].diff().apply(lambda x: "green" if x > 0 else "red")
    
    fig.add_trace(
        go.Bar(
            x=price_df["date"],
            y=price_df["volume"],
            marker_color=colors,
            name="Volume",
        ),
        row=4, col=1, secondary_y=False
    )
    
    fig.update_yaxes(title_text="Volume", row=4, col=1, secondary_y=False)
    fig.update_yaxes(title_text="Deliv %", row=4, col=1, secondary_y=True)
            
    
        # after every trace has been added, just before update_layout
    min_vol = price_df["volume"].min()
    max_vol = price_df["volume"].max()
    
    fig.update_yaxes(
        rangemode="normal",                # stop forcing to zero
        range=[min_vol * 0.8, max_vol * 1.1],   # add ±20 % padding
        row=4, col=1, secondary_y=False
    )
    
    min_deliv = price_df["deliv_pct_smooth"].min()
    max_deliv = price_df["deliv_pct_smooth"].max()
    
    fig.update_yaxes(
        rangemode="normal",
        range=[min_deliv * 0.9, max_deliv * 1.05],
        row=4, col=1, secondary_y=True
    )
    
    
    if not ind_df.empty:
        min_oi = ind_df["combined_open_interest"].min()
        max_oi = ind_df["combined_open_interest"].max()
    
        fig.update_yaxes(
            rangemode="normal",
            range=[min_oi * 0.9, max_oi * 1.05],
            row=3, col=1
        )
    
    # final cosmetics
    fig.update_layout(
        height=800,
        title=f"{choice} – last {win_label} (slider re-bases prices)",
        legend=dict(orientation="h"),
        margin=dict(t=40, b=40, l=20, r=20)
    )
    st.plotly_chart(fig, use_container_width=True)

with tabs[3]:
    
    ## Calculations
    
    const_df = pd.read_csv("data/nifty_500_constituents.csv")
    const_df["Sector"] = const_df["Sector"].str.strip()
    sector_list = const_df["Sector"].unique().tolist()
    
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
    
    cash_400 = data[data["date"] >= data["date"].max() - pd.Timedelta(days=400)]
    cash_400 = cash_400.merge(const_df[["Symbol", "Sector"]], left_on="symbol", right_on="Symbol")
    
    # 1️⃣  Prices matrix  (rows = date, cols = symbol)
    prices = (
        cash_400
        .pivot(index="date", columns="symbol", values="close")
        .sort_index()
    )
    rets = prices.pct_change().dropna(axis=0, how = 'all')   
    sector_map = const_df.set_index("Symbol")["Sector"].to_dict()

    sector_returns = {}
    for sec, syms in const_df.groupby("Sector")["Symbol"]:
        syms = [s for s in syms if s in rets.columns]  # keep only symbols with data
        if len(syms):
            sector_returns[sec] = rets[syms].mean(axis=1)
    
    sector_rets_df = pd.DataFrame(sector_returns)   # rows = date, cols = Sector
    
    # 5️⃣  Turn daily returns into an index, base 100
    eq_sector_index = (1 + sector_rets_df).cumprod() * 100
    
    nifty_rets  = nifty_close.pct_change().dropna()
    nifty_index = (1 + nifty_rets).cumprod() * 100
    eq_sector_rel = eq_sector_index.divide(nifty_index, axis=0) * 100    
    
    tbl_eq = {
    sec: [pct_return(eq_sector_rel[sec].dropna(), d) for d in lookbacks]
    for sec in sector_list
    }
    
    eq_table = pd.DataFrame(tbl_eq, index=[f"{d}-day" for d in lookbacks]).T
        
    st.header(f"📊 Sectoral Analysis — {TODAY_STR}")

    st.subheader("Official Nifty Sector Indices vs Nifty (Relative)")
    st.dataframe(official_table.style.format("{:.1f}%").background_gradient(cmap="RdYlGn"))

    st.subheader("Granular Equal-Weight Sector Indices vs Nifty (Relative)")
    st.dataframe(eq_table.style.format("{:.1f}%").background_gradient(cmap="RdYlGn"))

    st.subheader("Relative Time-Series (select)")
        # 1️⃣  choose window
    win_label = st.radio(
        "Look‑back window",
        ["1 M", "3 M", "6 M", "12 M", "All"],
        horizontal=True,
        index=3,     # default = 12 M
    )
    win_map = {"1 M":30, "3 M":90, "6 M":180, "12 M":365, "All":None}
    days_back = win_map[win_label]
    
    # 2️⃣  combined options list
    all_options = official_syms + sector_list
    default_sel = all_options[:3]   # show a few lines by default
    chosen = st.multiselect("Select up to 10 indices / sectors", all_options,
                            default=default_sel, max_selections=10)
    if not chosen:
        st.info("Choose at least one index / sector.")
        st.stop()
    
    # 3️⃣  build combined dataframe (relative already vs Nifty)
    combined_rel = pd.concat(
        [rel_official_df, eq_sector_rel], axis=1, join="inner"
    )
    
    # 4️⃣  slice by date window
    if days_back:
        date_cut = combined_rel.index.max() - pd.Timedelta(days=days_back)
        combined_rel = combined_rel[combined_rel.index >= date_cut]
    
    # 5️⃣  select & rebase to 100 at window start
    sel_df = combined_rel[chosen]
    rebased = (sel_df / sel_df.iloc[0]) * 100
        
    sel_df = combined_rel[chosen]
    rebased = (sel_df / sel_df.iloc[0]) * 100
    
    # build a simple Plotly figure
    fig_sec = go.Figure()
    for col in rebased.columns:
        fig_sec.add_trace(
            go.Scatter(x=rebased.index, y=rebased[col], mode="lines", name=col)
        )
    
    # tighten y‑axis around data
    ymin = rebased.min().min()
    ymax = rebased.max().max()
    fig_sec.update_yaxes(rangemode="normal", range=[ymin * 0.98, ymax * 1.02])
    
    fig_sec.update_layout(height=400, legend=dict(orientation="h"))
    st.plotly_chart(fig_sec, use_container_width=True)