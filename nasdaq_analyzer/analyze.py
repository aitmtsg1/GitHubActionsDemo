from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import os, io
import requests
import pandas as pd

NASDAQ_LIST_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
LOCAL_CACHE_PATHS = [
    os.path.join(os.path.dirname(__file__), 'nasdaqlisted.txt'),
    os.path.join(os.path.dirname(__file__), 'nasdaq_cached_symbols.txt'),
]

def requests_session_with_retries(total_retries=5, backoff_factor=1.0,
                                 status_forcelist=(429, 500, 502, 503, 504)):
    session = requests.Session()
    retries = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session

def parse_nasdaq_text(txt: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.StringIO(txt), sep='|', comment='#')
        if 'Symbol' in df.columns:
            return df
    except Exception:
        pass
    # fallback parsing
    lines = txt.splitlines()
    symbols = []
    for line in lines:
        if line.startswith('File Creation Time'):
            break
        parts = line.split('|')
        if parts:
            sym = parts[0].strip()
            if sym and sym != 'Symbol':
                symbols.append(sym)
    return pd.DataFrame({'Symbol': symbols})

def get_nasdaq_list() -> pd.DataFrame:
    # Try network fetch with retries/backoff
    session = requests_session_with_retries(total_retries=5, backoff_factor=1)
    try:
        resp = session.get(NASDAQ_LIST_URL, timeout=20)
        resp.raise_for_status()
        df = parse_nasdaq_text(resp.text)
        if not df.empty:
            return df
    except Exception as e:
        print(f"Warning: network fetch of NASDAQ list failed: {e}")

    # Try local cache files bundled with repository/runner
    for path in LOCAL_CACHE_PATHS:
        try:
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as fh:
                    df = parse_nasdaq_text(fh.read())
                if not df.empty:
                    print(f"Using local cached NASDAQ list at: {path}")
                    return df
        except Exception:
            continue

    # Last-resort: small hardcoded set for test runs
    fallback = ['AAPL','MSFT','AMZN','GOOG','META','NVDA','TSLA','INTC','CSCO','AMD','NFLX']
    print("Warning: falling back to small hardcoded symbol list (network unreachable and no local cache).")
    return pd.DataFrame({'Symbol': fallback})
