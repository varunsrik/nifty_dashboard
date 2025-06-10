#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Jun 10 18:19:58 2025

@author: varun
"""

# plots/basis.py
import plotly.graph_objects as go

def basis_figure(symbol, spot_s, fut_dict):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=spot_s.index, y=spot_s, name=f"{symbol} spot", line=dict(color="black")
    ))

    colors = ["blue","orange","green"]
    for (sym, ser), col in zip(fut_dict.items(), colors):
        fig.add_trace(go.Scatter(
            x=ser.index, y=ser, name=sym, line=dict(color=col)
        ))

    # add basis line for front contract
    if fut_dict:
        front_name, front_ser = next(iter(fut_dict.items()))
        basis = (front_ser - spot_s.reindex(front_ser.index)).dropna()
        fig.add_trace(go.Scatter(
            x=basis.index, y=basis, name="Front basis", line=dict(dash="dot", color="red"),
            yaxis="y2"
        ))

    fig.update_layout(
        title=f"{symbol}: spot vs futures (today)",
        yaxis=dict(title="Price"),
        yaxis2=dict(title="Basis pts", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h"),
        height=320
    )
    return fig