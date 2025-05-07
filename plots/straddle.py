#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May  6 14:56:18 2025

@author: varun
"""

from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd


def straddle_figure(ts_df, price_df, title):
    # ── pre‑compute range‑breaks (skip Sat/Sun + missing trading days) ──────
    start, end = ts_df["date"].min(), ts_df["date"].max()
    all_bdays   = pd.date_range(start, end, freq="B")
    missing_days = all_bdays.difference(price_df["date"].unique())

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        specs=[[{"secondary_y": True}], [{}]],
        row_heights=[0.55, 0.45], vertical_spacing=0.06
    )

    # Row‑1 : straddle price + IV
    fig.add_trace(
        go.Scatter(x=ts_df["date"], y=ts_df["price"],
                   mode="lines+markers", name="Straddle Price"),
        row=1, col=1, secondary_y=False
    )
    fig.add_trace(
        go.Scatter(x=ts_df["date"], y=ts_df["iv"],
                   mode="lines", line=dict(dash="dot", color="orange"),
                   name="ATM IV (%)"),
        row=1, col=1, secondary_y=True
    )
    fig.update_yaxes(title_text="Price", secondary_y=False, row=1, col=1)
    fig.update_yaxes(title_text="IV %", secondary_y=True,  row=1, col=1)

    # Row‑2 : cash OHLC or close line
    if {"open","high","low","close"}.issubset(price_df.columns):
        fig.add_trace(
            go.Candlestick(
                x=price_df["date"],
                open=price_df["open"], high=price_df["high"],
                low=price_df["low"], close=price_df["close"],
                name="Cash Candles"
            ),
            row=2, col=1
        )
    else:
        fig.add_trace(
            go.Scatter(x=price_df["date"], y=price_df["close"],
                       mode="lines", name="Cash Close"),
            row=2, col=1
        )

    # ── global x‑axis settings ─────────────────────────────────────────────
    fig.update_xaxes(
        rangeslider_visible=False,                    # hide slider
        rangebreaks=[
            dict(bounds=["sat", "mon"]),              # skip weekends
            dict(values=missing_days)                 # skip holidays / missing
        ]
    )

    fig.update_layout(
        height=550,
        title=title,
        margin=dict(t=50, b=40, l=20, r=20),
        legend=dict(orientation="h"),
    )
    return fig