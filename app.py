import pandas as pd
import streamlit as st
import datetime as dt
from core.fetch import index_all, fno_stock_all, get_constituents
from core.straddles import straddle_tables, straddle_timeseries, price_timeseries
from core.preprocess import (
    cash_with_live,
    compute_adv_decl,
    official_sector,
    equal_weight_sector,
    fno_oi_processing,
    stock_explorer_processing
)
from plots.breadth import breadth_figure, advdec_figure
from plots.stock_explorer import stock_explorer_figure
from plots.sector import sector_figure
from plots.straddle import straddle_figure
from core.sector import constituent_returns


DEFAULT_URL   = "https://1200-2406-7400-c8-ab81-20cf-a4ab-3f6-94c.ngrok-free.app"
DEFAULT_TOKEN = "1391"

API_URL   = st.secrets.get("api", {}).get("url",   DEFAULT_URL)
API_TOKEN = st.secrets.get("api", {}).get("token", DEFAULT_TOKEN)

st.set_page_config(page_title="📊 Market Breadth", layout="wide")

TODAY = dt.date.today()
TODAY_STR  = TODAY.strftime("%d %b %Y")

st.sidebar.title("⚙️ Settings")
USE_LIVE = st.sidebar.toggle("Include live (yfinance) candle", value=False, help="Adds today's bar via yfinance. Turn off to load faster.")

tabs = st.tabs(["📊 Market Breadth", "📈 Open Interest Analysis", "📉 Stock Explorer", "Sectoral Analysis", "Straddle Prices"])

cash_df = cash_with_live(USE_LIVE)
idx_df  = index_all()
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

    st.plotly_chart(breadth_figure(breadth_df, pct_df, nifty_price_df),
                use_container_width=True)
    
    st.plotly_chart(advdec_figure(breadth_df, nifty_price_df),
                    use_container_width=True)
    
with tabs[1]:
    st.header(f"📈 Open Interest Analysis — {TODAY_STR}")
    
    combined, prev_expiry = fno_oi_processing(fno_df, cash_df)
    

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
        st.write(label)
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
    sector_list = const_df["Sector"].unique().tolist()
    
    
    rel_official_df, official_table, official_syms = official_sector(idx_df)
    
    eq_sector_rel, eq_table = equal_weight_sector(cash_df, const_df)

        
    st.header(f"📊 Sectoral Analysis — {TODAY_STR}")

    st.subheader("Official Nifty Sector Indices vs Nifty (Relative)")
    st.dataframe(official_table.style.format("{:.1f}%").background_gradient(cmap="RdYlGn"))

    st.subheader("Granular Equal-Weight Sector Indices vs Nifty (Relative)")
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
            ts_df["date"].max()
        )
    
        st.plotly_chart(
            straddle_figure(ts_df, price_df, f"{chosen_sym} — Current Expiry"),
            use_container_width=True
        )