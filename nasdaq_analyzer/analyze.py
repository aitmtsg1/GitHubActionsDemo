#!/usr/bin/env python3
"""
nasdaq_analyzer/analyze.py

- Downloads NASDAQ symbol list
- Fetches historical data with yfinance
- Computes SMA (20,50,200), RSI(14), turnover indicators
- Produces buy/sell/hold signals with reasons
- Outputs CSV/JSON and a small HTML report
"""
import argparse
import io
import time
import math
import json
from datetime import datetime, timedelta
import requests
import pandas as pd
import numpy as np
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

NASDAQ_LIST_URL = "https://ftp.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"

# ---------- Indicators ----------
def sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -1 * delta.clip(upper=0.0)
    ma_up = up.ewm(com=(period - 1), adjust=False).mean()
    ma_down = down.ewm(com=(period - 1), adjust=False).mean()
    rs = ma_up / (ma_down + 1e-12)
    rsi_series = 100 - (100 / (1 + rs))
    return rsi_series

# ---------- Utilities ----------
def get_nasdaq_list() -> pd.DataFrame:
    resp = requests.get(NASDAQ_LIST_URL, timeout=30)
    resp.raise_for_status()
    txt = resp.text
    # The file ends with a footer line that starts with "File Creation Time"
    df = pd.read_csv(io.StringIO(txt), sep='|', comment='#')
    # Keep only Symbol column
    if 'Symbol' in df.columns:
        return df
    # fallback: try first column
    return pd.DataFrame({'Symbol': df.iloc[:,0]})


def batch_fetch_history(tickers, period='6mo', interval='1d', batch_size=80, pause=2.0):
    """Download history in batches using yfinance.download (vectorized)."""
    results = {}
    tickers = [t for t in tickers if t and isinstance(t, str)]
    for i in range(0, len(tickers), batch_size):
        group = tickers[i:i+batch_size]
        try:
            df = yf.download(group, period=period, interval=interval, progress=False, threads=True)
            # yfinance returns a multi-index columns when multiple tickers
            if isinstance(df.columns, pd.MultiIndex):
                for t in group:
                    try:
                        sub = df.xs(t, axis=1, level=1).dropna(how='all')
                        if not sub.empty:
                            results[t] = sub
                    except Exception:
                        continue
            else:
                # single ticker case
                if not df.empty:
                    results[group[0]] = df
        except Exception as e:
            print(f"Batch download error for {group[:5]}...: {e}")
        time.sleep(pause)
    return results


def analyze_ticker_hist(hist: pd.DataFrame):
    """
    Input: DataFrame with columns: Open, High, Low, Close, Adj Close, Volume
    Returns: dict with latest indicators and a simple signal
    """
    out = {}
    close = hist['Close'].astype(float)
    vol = hist['Volume'].astype(float)

    out['last_close'] = float(close.iloc[-1])
    out['last_volume'] = float(vol.iloc[-1])

    out['sma20'] = float(sma(close, 20).iloc[-1])
    out['sma50'] = float(sma(close, 50).iloc[-1])
    out['sma200'] = float(sma(close, 200).iloc[-1])

    out['rsi14'] = float(rsi(close, 14).iloc[-1])

    # Turnover: volume today / average volume (20)
    avg_vol20 = vol.rolling(window=20, min_periods=1).mean().iloc[-1]
    out['avg_vol20'] = float(avg_vol20) if not math.isnan(avg_vol20) else 0.0
    out['turnover_ratio'] = float(out['last_volume'] / (avg_vol20 + 1e-9)) if avg_vol20 > 0 else 0.0

    # Evaluate signal (simple rule-based system)
    reasons = []
    score = 0

    # SMA trend
    if out['sma20'] > out['sma50'] and out['sma50'] > out['sma200']:
        score += 2
        reasons.append('uptrend_sma')
    elif out['sma20'] < out['sma50'] and out['sma50'] < out['sma200']:
        score -= 2
        reasons.append('downtrend_sma')

    # Price above/below sma20
    if out['last_close'] > out['sma20']:
        score += 1
        reasons.append('price_above_sma20')
    else:
        score -= 1
        reasons.append('price_below_sma20')

    # RSI-based
    if out['rsi14'] < 30:
        score += 1
        reasons.append('rsi_oversold')
    elif out['rsi14'] > 70:
        score -= 1
        reasons.append('rsi_overbought')

    # Volume surge confirmation
    if out['turnover_ratio'] > 2.5:
        score += 1
        reasons.append('volume_spike')

    # Compose final signal
    if score >= 3:
        signal = 'STRONG_BUY'
    elif score == 2 or score == 1:
        signal = 'BUY'
    elif score == 0:
        signal = 'HOLD'
    elif score == -1 or score == -2:
        signal = 'SELL'
    else:
        signal = 'STRONG_SELL'

    out['signal'] = signal
    out['score'] = score
    out['reasons'] = reasons
    return out

# ---------- Main ----------
def main(argv=None):
    p = argparse.ArgumentParser(description="NASDAQ Analyzer — compute SMA/RSI/Turnover and simple signals")
    p.add_argument('--period', default='6mo', help='history period for yfinance (eg 6mo, 1y)')
    p.add_argument('--interval', default='1d', help='interval (1d, 1wk)')
    p.add_argument('--sample', type=int, default=0, help='limit to N tickers (0 = all)')
    p.add_argument('--out-prefix', default='output/nasdaq', help='output prefix for CSV/JSON')
    p.add_argument('--batch-size', type=int, default=60, help='number of tickers per yfinance batch')
    p.add_argument('--pause', type=float, default=1.5, help='seconds pause between batches')
    args = p.parse_args(argv)

    print("Downloading NASDAQ list...")
    df_symbols = get_nasdaq_list()
    symbols = df_symbols['Symbol'].tolist()
    # filter out non-tradable markers e.g. symbols containing ^ or . or test symbols
    clean = [s for s in symbols if s and s.isalnum()]
    if args.sample and args.sample > 0:
        clean = clean[:args.sample]
    print(f"Symbols count to analyze: {len(clean)}")

    print("Fetching price history in batches...")
    histories = batch_fetch_history(clean, period=args.period, interval=args.interval, batch_size=args.batch_size, pause=args.pause)
    print(f"Fetched {len(histories)} ticker histories.")

    results = []
    # Use a small thread pool to compute analysis in parallel
    with ThreadPoolExecutor(max_workers=8) as exe:
        futures = {}
        for ticker, hist in histories.items():
            if hist is None or len(hist) < 5:
                continue
            futures[exe.submit(analyze_ticker_hist, hist)] = ticker
        for fut in as_completed(futures):
            t = futures[fut]
            try:
                res = fut.result()
                res['ticker'] = t
                results.append(res)
            except Exception as e:
                print(f"Error analyzing {t}: {e}")

    if not results:
        print("No results, exiting.")
        return

    out_df = pd.DataFrame(results).set_index('ticker').sort_values(by='score', ascending=False)

    timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    csv_path = f"{args.out_prefix}_{timestamp}.csv"
    json_path = f"{args.out_prefix}_{timestamp}.json"
    out_df.to_csv(csv_path)
    out_df.to_json(json_path, orient='index', indent=2)
    print(f"Wrote CSV: {csv_path}")
    print(f"Wrote JSON: {json_path}")

    # Small HTML summary
    top_buy = out_df[out_df['signal'].isin(['STRONG_BUY','BUY'])].head(50)
    html = "<html><head><meta charset='utf-8'><title>NASDAQ Analyzer</title></head><body>"
    html += f"<h1>NASDAQ Analyzer Results — {timestamp} UTC</h1>"
    html += "<h2>Top Buys</h2>"
    html += top_buy[['last_close','sma20','sma50','rsi14','turnover_ratio','score','signal']].to_html()
    html += "</body></html>"
    with open(f"{args.out_prefix}_{timestamp}.html", "w", encoding="utf-8") as fh:
        fh.write(html)
    print("Done.")

if __name__ == '__main__':
    main()
