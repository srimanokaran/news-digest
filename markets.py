import logging

from config import MARKET_INDICES, SECTION_ETFS


def fetch_markets():
    """Fetch daily % change for market indices and sector ETFs."""
    import yfinance as yf

    results = {"indices": {}, "sectors": {}}

    all_tickers = {**{name: ticker for name, ticker in MARKET_INDICES.items()},
                   **{section: ticker for section, ticker in SECTION_ETFS.items()}}

    for name, ticker in all_tickers.items():
        try:
            hist = yf.Ticker(ticker).history(period="2d")
            if len(hist) >= 2:
                prev_close = float(hist["Close"].iloc[-2])
                last_close = float(hist["Close"].iloc[-1])
                change_pct = round((last_close - prev_close) / prev_close * 100, 2)
                entry = {
                    "ticker": ticker,
                    "close": round(last_close, 2),
                    "change_pct": change_pct,
                }
                if name in MARKET_INDICES:
                    results["indices"][name] = entry
                else:
                    results["sectors"][name] = entry
        except Exception as e:
            logging.error(f"Failed to fetch market data for {name} ({ticker}): {e}")

    return results
