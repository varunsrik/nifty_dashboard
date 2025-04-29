import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go


DEFAULT_URL   = "https://1200-2406-7400-c8-ab81-20cf-a4ab-3f6-94c.ngrok-free.app"
DEFAULT_TOKEN = "1391"

API_URL   = st.secrets.get("api", {}).get("url",   DEFAULT_URL)
API_TOKEN = st.secrets.get("api", {}).get("token", DEFAULT_TOKEN)


st.set_page_config(page_title="📊 Market Breadth", layout="wide")

# Replace with your actual ngrok URL

#API_URL = ' https://1200-2406-7400-c8-ab81-20cf-a4ab-3f6-94c.ngrok-free.app'
#API_TOKEN = "1391"  # same token used in api_server.py

tabs = st.tabs(["📊 Market Breadth", "📈 Open Interest Analysis", "📉 Stock Explorer"])

BREADTH_URL = API_URL+"/cash_data"  

# ---------- util helpers ----------

@st.cache_data(show_spinner=False, ttl=3600)
def get_constituents():
    return pd.read_csv("data/nifty_500_constituents.csv")


@st.cache_data(show_spinner=True, ttl=3600)
def fetch_cash(symbol_list):
    hdr = {"Authorization": f"Bearer {API_TOKEN}"}
    r = requests.post(
        f"{BREADTH_URL}",
        headers=hdr,
        json={"symbols": symbol_list},
        timeout=60,
    )
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df["date"] = pd.to_datetime(df["date"])
    return df

# ---------- Market Breadth tab ----------
with tabs[0]:
    st.header("📊 Market Breadth")

    constituents = get_constituents()
    symbols = constituents["Symbol"].unique().tolist()
    data = fetch_cash(symbols)
    if data.empty:
        st.warning("No cash data returned.")
        st.stop()

    # --- compute advance‑decline & EMA stats ---
    data.sort_values(["symbol", "date"], inplace=True)

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
    st.header("📈 Open Interest Analysis")
    
    FNO_URL = API_URL + "/fno_data"
    headers = {"Authorization": "Bearer 1391"}
    r = requests.get(FNO_URL, headers=headers)
    
    if r.status_code != 200:
        st.error("❌ Failed to fetch F&O data.")
    else:
        df = pd.DataFrame(r.json())
        df['date'] = pd.to_datetime(df['date'])
        df['front_expiry'] = pd.to_datetime(df['front_expiry'])
    
        # Get latest date and corresponding expiry
        latest_date = df['date'].max()
        latest_expiry = df[df['date'] == latest_date]['front_expiry'].mode().iloc[0]
    
        # Previous expiry is the max expiry date before the latest expiry
        prev_expiry = df[df['front_expiry'] < latest_expiry]['front_expiry'].max()
    
        st.write(f"Latest Expiry: `{latest_expiry.date()}` | Previous Expiry: `{prev_expiry.date()}`")
    
        # Filter data for the two expiry dates
        latest_df = df[df['date'] == latest_date].set_index('symbol')
        prev_df = df[df['front_expiry'] == prev_expiry].groupby('symbol').last()
    
        # existing code above ...
        combined = latest_df[['combined_open_interest']].join(
            prev_df[['combined_open_interest']],
            lsuffix='_latest', rsuffix='_prev',
            how='inner'
        ).dropna()
        
        # --- NEW: pull cash closes for the exact two dates --------------------------
        symbols_needed = combined.index.tolist()
        cash_df = fetch_cash(symbols_needed)          # uses the POST /cash_data
    
        cash_latest = (
            cash_df[cash_df["date"] == latest_date]
            .set_index("symbol")["close"]
            .rename("cash_close_latest")
        )
        cash_prev = (
            cash_df[cash_df["date"] == prev_expiry]
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
        prev_dates   = df[df["front_expiry"] == prev_expiry]["date"].unique()
        window_start = prev_dates.min()
        window_end   = prev_expiry
   
        # ---------------------------------------------------------------------------
        # 2) Pull CASH OHLC for all symbols over that window
        symbols_needed = combined.index.tolist()      # the same symbols present in combined
        cash_all = fetch_cash(symbols_needed)         # uses POST /cash_data (cached 30-min)
        
        cash_window = cash_all[
            (cash_all["date"] >= window_start) & (cash_all["date"] <= window_end)
        ]
        
        # high & low of CASH closes within that window
  
        prev_high  =(
            cash_window.groupby("symbol")["close"]
            .max()
            .rename("prev_high")
        )
        

        prev_low = (
            cash_window.groupby("symbol")["close"]
            .min()
            .rename("prev_low")
        )
        
        # cash close on previous expiry day (already built earlier as `cash_prev`)
        prev_close = cash_prev.rename("prev_close")
        
        # ---------------------------------------------------------------------------
        # 3) Join these reference prices into combined
        combined = combined.join([prev_high, prev_low, prev_close])
        
        # ---------------------------------------------------------------------------
        # 4) Recompute the price_signal column based on CASH prices
        def classify(row):
            if row["cash_close_latest"] > row["prev_high"]:
                return "price_above_high"
            elif row["cash_close_latest"] > row["prev_close"]:
                return "price_above_close"
            elif row["cash_close_latest"] < row["prev_low"]:
                return "price_below_low"
            elif row["cash_close_latest"] < row["prev_close"]:
                return "price_below_close"
            else:
                return None
        
        combined["price_signal"] = combined.apply(classify, axis=1)

            
        # # Join and compare
        # combined = latest_df[['front_fut_close', 'combined_open_interest']].join(
        #     prev_df[['front_fut_close', 'combined_open_interest']],
        #     lsuffix='_latest', rsuffix='_prev',
        #     how='inner'
        # ).dropna()
    
        # # Calculate percentage changes
        # combined['price_change'] = round(100*((combined['front_fut_close_latest'] / combined['front_fut_close_prev']) - 1),1)
        # combined['oi_change'] = round(100*((combined['combined_open_interest_latest'] / combined['combined_open_interest_prev']) - 1),1)
    
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
            
            
        labels = ['price_above_high', 'price_below_low', 'price_above_close', 'price_below_close']
        
        for label in labels:
            st.subheader(label)
            st.dataframe(combined[combined['price_signal']==label])
            

from plotly.subplots import make_subplots

STOCK_URL   = API_URL + "/cash_ohlc"
INDIC_URL   = API_URL + "/fno_indicators"
INDEX_URL    = API_URL + "/index_data"
INDEX_SYMBOL = "NIFTY 50"


# ----------------------------------------------------------------- Stock Explorer

with tabs[2]:
    st.header("📉 Stock Explorer")
    
    # ↓ dropdown combines Nifty-500 and F&O names
    nifty500_syms = get_constituents()["Symbol"].unique().tolist()
    fno_syms      = df["symbol"].unique().tolist()        # from F&O tab earlier
    all_syms      = sorted(set(nifty500_syms) | set(fno_syms))
    choice        = st.selectbox("Choose a stock", all_syms, index=all_syms.index("RELIANCE") if "RELIANCE" in all_syms else 0)

    # window slider (radio buttons)
    win_label = st.radio("Select window", ["1 M", "3 M", "6 M", "12 M", "All"], horizontal=True)

    win_map = {"1 M": 30, "3 M": 90, "6 M": 180, "12 M": 365, "All": 400}
    win_days = win_map[win_label]

    # ----------- cached fetch ------------------------------------------------
    @st.cache_data(show_spinner=True, ttl=1800)
    def load_stock(sym):
        headers = {"Authorization": "Bearer 1391"}
        price = requests.post(STOCK_URL,  headers=headers, json={"symbol": sym}).json()
        ind   = requests.post(INDIC_URL,  headers=headers, json={"symbol": sym}).json()
        index = requests.post(INDEX_URL,  headers=headers, json={"symbol": INDEX_SYMBOL}).json()
        return (pd.DataFrame(price), pd.DataFrame(ind), pd.DataFrame(index))

    price_df, ind_df, index_df = load_stock(choice.upper())
    if price_df.empty:
        st.warning("No price data found for this symbol.")
        st.stop()

    # ----------- prep & filtering -------------------------------------------
    price_df["date"]  = pd.to_datetime(price_df["date"])
    index_df["date"]  = pd.to_datetime(index_df["date"])
    ind_df["date"]    = pd.to_datetime(ind_df["date"])
    
    price_df["deliv_pct_smooth"] = (
    price_df["deliv_pct"]
    .ewm(span=3, adjust=False)
    .mean()
    )

    # window filter
    cutoff = price_df["date"].max() - pd.Timedelta(days=win_days)
    price_df = price_df[price_df["date"] >= cutoff]
    index_df = index_df[index_df["date"] >= cutoff]
    ind_df   = ind_df[ind_df["date"] >= cutoff]
    
    prev_close_price = price_df.loc[price_df["date"] == prev_expiry, "close"].squeeze()

    # align index close to price dates
    index_series = (
        index_df.groupby("date")["close"].mean()
        .reindex(price_df["date"])
        .fillna(method="ffill")
    )

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
               [{"secondary_y": False}]],
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

  
     # Row-4: Volume and delivery pct
    fig.add_trace(
    go.Bar(
        x=price_df["date"],
        y=price_df["volume"],
        name="Volume",
        marker_color="grey",
    ),
    row=4, col=1, secondary_y=False
    )
    
    
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
        
    # final cosmetics
    fig.update_layout(
        height=800,
        title=f"{choice} – last {win_label} (slider re-bases prices)",
        legend=dict(orientation="h"),
        margin=dict(t=40, b=40, l=20, r=20)
    )
    st.plotly_chart(fig, use_container_width=True)