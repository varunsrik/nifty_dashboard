#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun 10 18:19:58 2025

@author: varun
"""

from plotly.subplots import make_subplots
import plotly.graph_objects as go

def basis_daily_figure(symbol, price_df, basis_df):
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        specs=[[{}],[{"secondary_y":True}]],
                        row_heights=[0.6,0.4], vertical_spacing=0.04)

    # Row-1 OHLC
    fig.add_trace(
        go.Candlestick(
            x=price_df.index, open=price_df["open"], high=price_df["high"],
            low=price_df["low"], close=price_df["close"],
            name=f"{symbol} spot"
        ),
        row=1,col=1
    )

    # Row-2 basis pct (secondary y) & spot line (primary y)
    # fig.add_trace(
    #     go.Scatter(x=price_df.index, y=price_df["close"],
    #                name="Spot close", line=dict(color="black")),
    #     row=2,col=1, secondary_y=False
    # )
    colors = {"front_pct":"blue","back_pct":"orange","far_pct":"green"}
    for col,c in colors.items():
        if col in basis_df:
            fig.add_trace(
                go.Scatter(x=basis_df.index, y=basis_df[col],
                           name=col.replace("_pct"," basis %"),
                           line=dict(color=c, dash="dot")),
                row=2,col=1, secondary_y=False
            )

    #fig.update_yaxes(title_text="Price", row=2,col=1, secondary_y=False)
    fig.update_yaxes(title_text="Basis %", row=2,col=1, secondary_y=False)
    # -------- turn OFF the default range-slider ----------------------------
    fig.update_xaxes(rangeslider_visible=False)
    
    fig.update_layout(
        title=f"{symbol}: Price & Basis (last {len(price_df)} days)",
        height=600,                         # overall figure height 
        legend=dict(orientation="h")
    )
    return fig