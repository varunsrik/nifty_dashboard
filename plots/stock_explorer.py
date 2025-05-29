#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May  6 09:32:34 2025

@author: varun
"""

from plotly.subplots import make_subplots
import plotly.graph_objects as go
import pandas as pd


def stock_explorer_figure(choice, price_df, ind_df, rebased_stock, rebased_index, prev_close_price, win_label):
        # ---------- make prev_close a clean scalar ---------------------------
    if isinstance(prev_close_price, pd.Series):
        # take first non-NA value, else set None
        prev_close_price = (
            prev_close_price.dropna().iloc[0]
            if not prev_close_price.dropna().empty else None
        )
    elif pd.isna(prev_close_price):
        prev_close_price = None
        
        
    
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
    
    if prev_close_price is not None:
        fig.add_hline(
        y=float(prev_close_price),
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
    return fig