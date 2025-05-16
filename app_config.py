#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May  5 10:17:38 2025

@author: varun
"""

# config.py
API_URL   = "https://dashboard.varunsrik.org"
API_TOKEN = "1391"



DB_CONFIG = {
    "DB_NAME": "trading_data",
    "DB_USER": "varun",
    "DB_PASSWORD": "071023",  # move to env var later
    "DB_HOST": "localhost",
    "DB_PORT": "5432"
}


CACHE_SQL_TTL  = "6h"   # long cache for SQL API pulls
CACHE_LIVE_TTL = 900    # 15 min cache for live calls
CACHE_INTRADAY_LIVE_TTL = 60


INDEX_SYMBOLS = ['NIFTY FIN SERVICE',
 'NIFTY MEDIA',
 'NIFTY OIL AND GAS',
 'NIFTY REALTY',
 'NIFTY 50',
 'NIFTY BANK',
 'NIFTY AUTO',
 'NIFTY FMCG',
 'NIFTY HEALTHCARE',
 'NIFTY IT',
 'NIFTY METAL',
 'NIFTY PHARMA',
 'NIFTY PVT BANK',
 'NIFTY PSU BANK',
 'NIFTY MIDCAP 100',
 'NIFTY SMALLCAP 250',
 'NIFTY 500']
