# app_config.py

CACHE_SQL_TTL  = "6h"   # long cache for SQL API pulls
CACHE_LIVE_TTL = 900    # 15 min cache for live calls
CACHE_INTRADAY_LIVE_TTL = 60


INDEX_SYMBOLS = [
    'NIFTY FIN SERVICE',
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
    'NIFTY 500',
]
