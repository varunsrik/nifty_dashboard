
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd

def breadth_figure(breadth_df, pct_df, nifty_df):
    # create secondary‑y subplot in *one* row
    fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])

    # ── EMA percentage lines (primary y) ───────────────────────────
    for span, col in zip((20,50,100,200), pct_df.columns):
        fig.add_trace(
            go.Scatter(
                x=pct_df.index, y=pct_df[col],
                name=f"%> EMA{span}", mode="lines",
                line=dict(width=1, dash="dot")
            ),
            secondary_y=False
        )

    fig.update_yaxes(title_text="% Above EMA", secondary_y=False)

    # ── NIFTY close line (secondary y) ─────────────────────────────
    fig.add_trace(
        go.Scatter(
            x=nifty_df["date"], y=nifty_df["close"],
            name="NIFTY 50 Close", mode="lines",
            line=dict(color="green")
        ),
        secondary_y=True
    )
    fig.update_yaxes(title_text="NIFTY Price", secondary_y=True)

    # ── slider + skip weekends/holidays ────────────────────────────
    bdays   = pd.date_range(breadth_df["date"].min(), breadth_df["date"].max(), freq="B")
    missing = bdays.difference(nifty_df["date"].unique())

    fig.update_xaxes(
        rangeslider=dict(visible=True, thickness=0.05),
        rangebreaks=[dict(bounds=["sat","mon"]), dict(values=missing)]
    )

    fig.update_layout(
        title="Market Breadth – last 3 months",
        legend=dict(orientation="h", y=-0.15),
        height=500,
        margin=dict(t=70, b=60, l=20, r=20)
    )
    return fig

# ───────────────────────── A/D ratio + Nifty candles ────────────────────────
def advdec_figure(breadth_df, nifty_df):
    fig = make_subplots(rows=1, cols=1, specs=[[{"secondary_y": True}]])

    # A/D ratio
    fig.add_trace(
        go.Scatter(
            x=breadth_df["date"], y=breadth_df["adv_dec_ratio"],
            mode="lines", line=dict(width=2), name="A/D Ratio"
        ),
        secondary_y=False
    )
    fig.update_yaxes(title_text="A/D Ratio", secondary_y=False)

    # Nifty close line
    fig.add_trace(
        go.Scatter(
            x=nifty_df["date"], y=nifty_df["close"],
            mode="lines", name="NIFTY 50 Close",
            line=dict(color="green")
        ),
        secondary_y=True
    )
    fig.update_yaxes(title_text="NIFTY Price", secondary_y=True)

    # shared slider
    bdays = pd.date_range(breadth_df["date"].min(), breadth_df["date"].max(), freq="B")
    missing = bdays.difference(nifty_df["date"].unique())

    fig.update_xaxes(
        rangeslider=dict(visible=True, thickness=0.05),
        rangebreaks=[dict(bounds=["sat","mon"]), dict(values=missing)]
    )

    fig.update_layout(
        title="Advance‑Decline Ratio – last 3 months",
        showlegend=True,
        legend=dict(orientation="h", y=-0.15),
        height=480,
        margin=dict(t=70, b=60, l=20, r=20)
    )
    return fig