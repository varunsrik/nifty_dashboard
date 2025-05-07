#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May  6 10:18:57 2025

@author: varun
"""
import plotly.graph_objects as go


def sector_figure(rebased):
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
    return fig_sec