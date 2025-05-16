import pandas as pd
import streamlit as st
import datetime as dt
import re
from core.fetch import fno_stock_all, get_constituents, read_intraday, get_intraday_symbols
from core.straddles import straddle_tables, straddle_timeseries, price_timeseries
from core.preprocess import (
    cash_with_live,
    index_with_live,
    compute_adv_decl,
    official_sector,
    equal_weight_sector,
    fno_oi_processing,
    stock_explorer_processing
)
from core.live_zerodha import live_index_quotes, live_quotes, atm_straddle
from plots.breadth import breadth_figure, advdec_figure
from plots.stock_explorer import stock_explorer_figure
from plots.sector import sector_figure
from plots.straddle import straddle_figure
from core.sector import constituent_returns
from core.fno_utils import classify_futures
from app_config import INDEX_SYMBOLS
import plotly.graph_objects as go




DEFAULT_URL   = "https://1200-2406-7400-c8-ab81-20cf-a4ab-3f6-94c.ngrok-free.app"
DEFAULT_TOKEN = "1391"

API_URL   = st.secrets.get("api", {}).get("url",   DEFAULT_URL)
API_TOKEN = st.secrets.get("api", {}).get("token", DEFAULT_TOKEN)


st.set_page_config(page_title="📊 Market Breadth", layout="wide")

TODAY = dt.date.today()
TODAY_STR  = TODAY.strftime("%d %b %Y")

st.sidebar.title("⚙️ Settings")
USE_LIVE = st.sidebar.toggle("Include live (Kite) quotes", value=False,
                             key="use_live")


if "last_update" not in st.session_state:
    st.session_state["last_update"] = dt.datetime.now()

if st.sidebar.button("🔄 Update prices", help="Clear live caches and refresh"):
    for fn in [
        cash_with_live,
        index_with_live,
        compute_adv_decl,
        official_sector,
        equal_weight_sector,
        fno_oi_processing,
        stock_explorer_processing,
        live_index_quotes,
        live_quotes,
        atm_straddle
        ]:
        fn.clear()                     # flush the cache
    st.session_state["last_update"] = dt.datetime.now()
    st.rerun()            # immediately rerun app with fresh data
    
# =============================================================================

tabs = st.tabs(["📊 Market Breadth", "📈 Open Interest Analysis", "📉 Stock Explorer", "Sectoral Analysis", "Straddle Prices", "⏱️ Intraday"])

cash_df = cash_with_live(USE_LIVE)
idx_df  = index_with_live(USE_LIVE)
fno_df  = fno_stock_all()



# ---------- Market Breadth tab ----------
with tabs[0]:
    st.header(f"📊 Market Breadth — {TODAY_STR}")

    breadth_df, pct_df = compute_adv_decl(cash_df)
    nifty_price_df = idx_df[idx_df["symbol"] == "NIFTY 50"][["date", "open", "high", "low", "close"]]
    start, end = breadth_df["date"].min(), breadth_df["date"].max()
    nifty_price_df = nifty_price_df[
    (nifty_price_df["date"] >= start) & (nifty_price_df["date"] <= end)
    ]
    todays_date = breadth_df['date'].iloc[-1].strftime('%Y-%m-%d')
    st.write(f'* Prices are for {todays_date}')
    st.plotly_chart(breadth_figure(breadth_df, pct_df, nifty_price_df),
                use_container_width=True)
    
    st.plotly_chart(advdec_figure(breadth_df, nifty_price_df),
                    use_container_width=True)
    
with tabs[1]:
    st.header(f"📈 Open Interest Analysis — {TODAY_STR}")
    st.write(fno_df.iloc[-3:    ])

    
    combined, prev_expiry, front_expiry, cash_latest_date = fno_oi_processing(fno_df, cash_df)
    
    st.write(f'* Prices are for {cash_latest_date.strftime("%Y-%m-%d")}')
    
    labels = [
    "OI Up / Price Up",
    "OI Up / Price Down",
    "OI Down / Price Up",
    "OI Down / Price Down"
    ]
    for label in labels:
        st.subheader(label)
        st.dataframe(combined[combined['quadrant'] == label][[
        'cash_close_prev', 'cash_close_latest', 'price_change',
        'combined_open_interest_prev', 'combined_open_interest_latest', 'oi_change', 'price_signal'
        ]].sort_values('price_change', ascending=False))
        
    
    labels = ['price_above_prev_expiry_high', 'price_below_prev_expiry_low', 'price_above_prev_expiry_close', 'price_below_prev_expiry_close']
    
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

    all_syms      = sorted(set(nifty500_syms) | set(fno_syms))
        
    choice        = st.selectbox("Choose a stock", all_syms, index=all_syms.index("RELIANCE") if "RELIANCE" in all_syms else 0)

    # window slider (radio buttons)
    win_label = st.radio("Select window", ["1 M", "3 M", "6 M", "12 M", "All"], horizontal=True)

    win_map = {"1 M": 30, "3 M": 90, "6 M": 180, "12 M": 365, "All": 400}
    win_days = win_map[win_label]
    
    price_df, ind_df, rebased_stock, rebased_index, prev_close_price = stock_explorer_processing(cash_df, choice, fno_df, win_days, nifty_df, prev_expiry)
   
    # ----------- build Plotly figure ----------------------------------------
    
    st.plotly_chart(stock_explorer_figure(choice, price_df, ind_df, rebased_stock, rebased_index, prev_close_price, win_label), use_container_width=True)
    

with tabs[3]:
    
    ## Calculations
    
    const_df = pd.read_csv("data/nifty_500_constituents.csv")
    const_df["Sector"] = const_df["Sector"].str.strip()
    sector_list = const_df["Sector"].sort_values().unique().tolist()
    
    
    rel_official_df, official_table, official_syms = official_sector(idx_df)
    
    eq_sector_rel, eq_table = equal_weight_sector(cash_df, const_df, idx_df)
    
        
    st.header(f"📊 Sectoral Analysis — {TODAY_STR}")
    st.subheader("Official Nifty Sector Indices vs Nifty (Relative)")
    st.write('*Prices are for ', rel_official_df.index[-1].strftime('%Y-%m-%d'))
    st.dataframe(official_table.style.format("{:.1f}%").background_gradient(cmap="RdYlGn"))

    st.subheader("Granular Equal-Weight Sector Indices vs Nifty (Relative)")
    st.write('*Prices are for ', eq_sector_rel.index[-1].strftime('%Y-%m-%d'))
    st.dataframe(eq_table.style.format("{:.1f}%").background_gradient(cmap="RdYlGn"))
        
    # ───────────────────── Sector‑constituent returns ──────────────────────
    st.subheader("Sector Constituents – look‑back returns")

    dropdown_sectors = sector_list
    chosen_sector = st.selectbox("Choose a sector", dropdown_sectors, index=0)

    tbl_const = constituent_returns(chosen_sector, cash_df, idx_df, const_df)

    if tbl_const is None:
        st.info("Constituent mapping for official Nifty sector indices isn't linked yet.")
    else:
        st.dataframe(
            tbl_const.style.format("{:.1f}%").background_gradient(cmap="RdYlGn"),
            height=min(400, 30 + 24 * len(tbl_const))
        )

    st.subheader("Relative Time-Series (select)")
        # 1️⃣  choose window
    win_label = st.radio(
        "Look‑back window",
        ["1 M", "3 M", "6 M", "12 M", "All"],
        horizontal=True,
        index=3# default = 12 M
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
    st.write(combined_rel)
    sel_df = combined_rel[chosen]
    rebased = (sel_df / sel_df.iloc[0]) * 100
    
    st.plotly_chart(sector_figure(rebased), use_container_width=True)


with tabs[4]:
    st.header(f"🎯 Straddle Prices — {TODAY_STR}")

    idx_tbl, stk_tbl = straddle_tables()

    st.subheader("Index Straddles – last 5 sessions")
    st.dataframe(
        idx_tbl.style.format("{:.2f}")
                 .background_gradient(cmap="RdYlGn", subset=list(idx_tbl.columns).remove('Straddle'))
    )

    st.subheader("Stock Straddles – last 5 sessions")
    st.dataframe(
        stk_tbl.style.format("{:.2f}")
                 .background_gradient(cmap="RdYlGn", subset=list(stk_tbl.columns).remove('Straddle'))
    )

        # ── Interactive time‑series plot ──────────────────────────────────
    st.subheader("Straddle Price + Cash Candles")

    symbols_dropdown = idx_tbl.index.tolist() + stk_tbl.index.tolist()
    chosen_sym = st.selectbox("Choose straddle symbol", symbols_dropdown, index=0)

    ts_df = straddle_timeseries(chosen_sym)
    if ts_df.empty:
        st.info("No straddle data for this symbol / expiry.")
    else:
        price_df = price_timeseries(
            chosen_sym,
            ts_df["date"].min(),
            ts_df["date"].max(),
            cash_df,
            idx_df
            )
        
        st.plotly_chart(
            straddle_figure(ts_df, price_df, f"{chosen_sym} — Current Expiry"),
            use_container_width=True
        )
        


# ─────────────────── Intraday tab ───────────────────────────────
with tabs[5]:
    st.header(f"⏱️ Intraday – {TODAY_STR}")
    st.markdown(f"**Last live update:** {st.session_state['last_update'].strftime('%H:%M:%S')}")

    available_syms = get_intraday_symbols()
        
    front_fut, back_fut, far_fut = classify_futures(available_syms)
    all_fut = front_fut + back_fut + far_fut

    index_symbols = INDEX_SYMBOLS
    
    # 1️⃣  fetch bars ---------------------------------------------------------
    syms_needed = ["NIFTY 50", "NIFTY"]          # spot + fut for basis
    cash_bars   = read_intraday([*get_constituents()["Symbol"].unique(),])
    index_bars = read_intraday(index_symbols)
    fut_bars = read_intraday(all_fut)

    nifty_bars  = index_bars[index_bars["symbol"] == "NIFTY 50"]
    nifty_fut_bars = fut_bars[fut_bars["symbol"] == "NIFTY25MAYFUT"]


    # ------------------------------------------------------------------
    # 3️⃣  Intraday Advance / Decline  vs  Nifty spot
    # ------------------------------------------------------------------
    
    # ---- 3.1  yesterday’s closes -------------------------------------
    if USE_LIVE:
        prev_eod_date = cash_df["date"].iloc[:-1].max()   # cash_df is your 400-day EOD frame
    else:
        prev_eod_date = cash_df["date"].max()
    prev_closes = (
        cash_df[cash_df["date"] == prev_eod_date]
        .set_index("symbol")["close"]
    )
    
    # keep only symbols that also appear in today’s minute feed
    cash_bars = cash_bars[cash_bars["symbol"].isin(prev_closes.index)]
    cash_bars["prev_close"] = cash_bars["symbol"].map(prev_closes)
    
    # ---- 3.2  classify each minute -----------------------------------
    cash_bars["dir"] = cash_bars["close"] - cash_bars["prev_close"]  # +, 0, −
    
    adv = (
        cash_bars.groupby("datetime")["dir"]
                 .apply(lambda s: (s > 0).sum())
    )
    dec = (
        cash_bars.groupby("datetime")["dir"]
                 .apply(lambda s: (s < 0).sum())
    )
    ad_ratio = (adv - dec).rename("A/D").reset_index()
    
    # ---- 3.3  plot ---------------------------------------------------
    fig2 = go.Figure()
    fig2.add_trace(
        go.Scatter(x=ad_ratio["datetime"], y=ad_ratio["A/D"],
                   name="Advance-Decline", yaxis="y1")
    )
    fig2.add_trace(
        go.Scatter(x=nifty_bars["datetime"], y=nifty_bars["close"],
                   name="Nifty spot", yaxis="y2", line=dict(dash="dot"))
    )
    fig2.update_layout(
        title="Intraday A/D vs Nifty (vs yesterday’s close)",
        yaxis=dict(title="A-D"),                        # primary axis
        yaxis2=dict(title="Nifty", overlaying="y", side="right"),
        height=300, legend=dict(orientation="h")
    )
    st.plotly_chart(fig2, use_container_width=True)
    
    # 4️⃣  Basis chart --------------------------------------------------------
  

# ---- 4.1  pick a future symbol ------------------------------------
    all_futs = sorted(fut_bars["symbol"].unique())          # e.g.  RELIANCE25JUNFUT
    sel_fut  = st.selectbox("Choose a future", all_futs, index=0)

# ---- 4.2  derive the spot/underlying symbol -----------------------
    def underlying(sym_fut: str) -> str:
        """
        Strip the YYMONFUT suffix, then map index aliases to cash symbol.
        """
        base = re.sub(r"\d{2}[A-Z]{3}FUT$", "", sym_fut)   # RELIANCE, NIFTY,…
    
        index_map = {
            "NIFTY": "NIFTY 50",
            "BANKNIFTY": "NIFTY BANK",
            "FINNIFTY": "NIFTY FIN SERVICE",
        }
        return index_map.get(base, base)                  # stocks stay unchanged

    spot_sym = underlying(sel_fut)

# ---- 4.3  slice todays minute bars -------------------------------
    fut_sel  = fut_bars[fut_bars["symbol"] == sel_fut]
    spot_sel = (index_bars if spot_sym in index_symbols else cash_bars)
    spot_sel = spot_sel[spot_sel["symbol"] == spot_sym]
    
    if fut_sel.empty or spot_sel.empty:
        st.warning("No intraday data for that selection yet.")
        st.stop()
    
    # Align on common timestamps
    merged = pd.merge(
        fut_sel[["datetime", "close"]],
        spot_sel[["datetime", "close"]],
        on="datetime", how="inner", suffixes=("_fut", "_spot")
    )
    merged["basis"] = merged["close_fut"] - merged["close_spot"]

    # ---- 4.4  plot basis (y1) + spot price (y2) ----------------------
    fig3 = go.Figure()
    
    fig3.add_trace(
        go.Scatter(
            x=merged["datetime"], y=merged["basis"],
            mode="lines", name=f"{sel_fut} basis", yaxis="y1"
        )
    )
    fig3.add_trace(
        go.Scatter(
            x=merged["datetime"], y=merged["close_spot"],
            mode="lines", line=dict(dash="dot"),
            name=f"{spot_sym} spot", yaxis="y2"
        )
    )
    
    fig3.update_layout(
        title=f"Intraday Basis – {sel_fut} vs {spot_sym}",
        yaxis=dict(title="Basis (₹)"),
        yaxis2=dict(title="Spot", overlaying="y", side="right", showgrid=False),
        height=300,
        legend=dict(orientation="h"),
        margin=dict(t=40, b=20, l=20, r=20),
    )
    
    st.plotly_chart(fig3, use_container_width=True)