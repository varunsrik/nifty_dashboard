#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May  5 10:17:38 2025

@author: varun
"""

# config.py
API_URL   = "https://dashboard.varunsrik.org"
API_TOKEN = "1391"

CACHE_SQL_TTL  = "6h"   # long cache for SQL API pulls
CACHE_LIVE_TTL = 900    # 15 min cache for live calls