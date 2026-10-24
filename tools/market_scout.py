"""Market Scout: free, keyless market data for stocks, options and meme coins.

Runs two ways:
  * MCP server (default):   python tools/market_scout.py
  * CLI:                    python tools/market_scout.py quote NVDA
                            python tools/market_scout.py chain SPY --expiry 2026-11-21
                            python tools/market_scout.py dex pepe
                            python tools/market_scout.py boosted

Data sources: Yahoo Finance (via yfinance, delayed ~15 min) and the public
DexScreener API. Research only; nothing here places orders.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd
import requests
import yfinance as yf

DEX_API = "https://api.dexscreener.com"
RISK_FREE_RATE = 0.04
HTTP_TIMEOUT = 15


def _clean(value):
    """Make numpy/pandas values JSON-safe."""
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return None if math.isnan(value) or math.isinf(value) else round(float(value), 4)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    return value


def _norm_cdf(x):
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def _norm_pdf(x):
    return np.exp(-x * x / 2) / math.sqrt(2 * math.pi)


def bsm_greeks(spot, strike, years, vol, call: bool, rate: float = RISK_FREE_RATE) -> dict:
    """Black-Scholes-Merton greeks. theta is per calendar day, vega per 1 vol point."""
    strike, vol = np.asarray(strike, float), np.maximum(np.asarray(vol, float), 1e-4)
    sqrt_t = math.sqrt(years)
    d1 = (np.log(spot / strike) + (rate + vol**2 / 2) * years) / (vol * sqrt_t)
    d2 = d1 - vol * sqrt_t
    disc = math.exp(-rate * years)
    gamma = _norm_pdf(d1) / (spot * vol * sqrt_t)
    vega = spot * _norm_pdf(d1) * sqrt_t / 100
    decay = -spot * _norm_pdf(d1) * vol / (2 * sqrt_t)
    if call:
        delta = _norm_cdf(d1)
        theta = (decay - rate * strike * disc * _norm_cdf(d2)) / 365
    else:
        delta = _norm_cdf(d1) - 1
        theta = (decay + rate * strike * disc * _norm_cdf(-d2)) / 365
    return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}


def _last_price(ticker: yf.Ticker) -> float:
    hist = ticker.history(period="5d", interval="1d")
    if hist.empty:
        raise ValueError("no price data")
    return float(hist["Close"].iloc[-1])


# ---------------------------------------------------------------- stocks / ETFs


def quote(symbol: str) -> dict:
    """Price, day range, volume and key stats for a stock, ETF, index or crypto (e.g. BTC-USD)."""
    t = yf.Ticker(symbol)
    info = t.fast_info
    return _clean({
        "symbol": symbol.upper(),
        "last": info.get("lastPrice"),
        "previous_close": info.get("previousClose"),
        "open": info.get("open"),
        "day_high": info.get("dayHigh"),
        "day_low": info.get("dayLow"),
        "volume": info.get("lastVolume"),
        "avg_volume_10d": info.get("tenDayAverageVolume"),
        "year_high": info.get("yearHigh"),
        "year_low": info.get("yearLow"),
        "market_cap": info.get("marketCap"),
    })


def technicals(symbol: str, period: str = "6mo", interval: str = "1d") -> dict:
    """Trend and momentum snapshot: SMAs, EMA, RSI(14), ATR(14), MACD, VWAP (intraday), and relative volume."""
    df = yf.Ticker(symbol).history(period=period, interval=interval)
    if df.empty:
        raise ValueError(f"no history for {symbol}")
    close, high, low, vol = df["Close"], df["High"], df["Low"], df["Volume"]

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - 100 / (1 + gain / loss)

    prev_close = close.shift()
    true_range = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = true_range.ewm(alpha=1 / 14, adjust=False).mean()

    macd = close.ewm(span=12, adjust=False).mean() - close.ewm(span=26, adjust=False).mean()
    signal = macd.ewm(span=9, adjust=False).mean()

    out = {
        "symbol": symbol.upper(),
        "bars": len(df),
        "last_close": close.iloc[-1],
        "sma20": close.rolling(20).mean().iloc[-1],
        "sma50": close.rolling(50).mean().iloc[-1],
        "sma200": close.rolling(200).mean().iloc[-1] if len(df) >= 200 else None,
        "ema9": close.ewm(span=9, adjust=False).mean().iloc[-1],
        "rsi14": rsi.iloc[-1],
        "atr14": atr.iloc[-1],
        "atr_pct": atr.iloc[-1] / close.iloc[-1] * 100,
        "macd": macd.iloc[-1],
        "macd_signal": signal.iloc[-1],
        "macd_hist": (macd - signal).iloc[-1],
        "relative_volume": vol.iloc[-1] / vol.rolling(20).mean().iloc[-1],
        "period_high": high.max(),
        "period_low": low.min(),
    }
    if interval[-1] in ("m", "h"):
        typical = (high + low + close) / 3
        day = df.index.normalize() == df.index[-1].normalize()
        out["vwap_today"] = (typical[day] * vol[day]).sum() / vol[day].sum()
    return _clean(out)


# --------------------------------------------------------------------- options


def expirations(symbol: str) -> list[str]:
    """List available option expiration dates for a symbol."""
    return list(yf.Ticker(symbol).options)


def option_chain(symbol: str, expiry: str | None = None, strikes_around: int = 8) -> dict:
    """Option chain for one expiry with IV and greeks (delta, gamma, theta/day, vega per 1 vol pt).

    expiry: YYYY-MM-DD; defaults to the nearest expiration.
    strikes_around: how many strikes above and below the spot to return.
    """
    t = yf.Ticker(symbol)
    expiry = expiry or t.options[0]
    spot = _last_price(t)
    dte = max((datetime.strptime(expiry, "%Y-%m-%d").date() - date.today()).days, 0)
    years = max(dte, 0.5) / 365

    chain = t.option_chain(expiry)
    result = {"symbol": symbol.upper(), "spot": spot, "expiry": expiry, "dte": dte}
    for side, df in (("calls", chain.calls), ("puts", chain.puts)):
        df = df.copy()
        idx = (df["strike"] - spot).abs().idxmin()
        pos = df.index.get_loc(idx)
        df = df.iloc[max(pos - strikes_around, 0): pos + strikes_around + 1].reset_index(drop=True)
        mid = ((df["bid"] + df["ask"]) / 2).where((df["bid"] > 0) & (df["ask"] > 0), df["lastPrice"])
        greeks = bsm_greeks(spot, df["strike"], years, df["impliedVolatility"], call=side == "calls")
        df = df.assign(mid=mid, **greeks)
        cols = ["contractSymbol", "strike", "bid", "ask", "mid", "lastPrice", "volume", "openInterest",
                "impliedVolatility", "delta", "gamma", "theta", "vega", "inTheMoney"]
        result[side] = _clean(df[cols].to_dict(orient="records"))

    atm = min(result["calls"], key=lambda r: abs(r["strike"] - spot))
    put_atm = min(result["puts"], key=lambda r: abs(r["strike"] - spot))
    straddle = (atm["mid"] or 0) + (put_atm["mid"] or 0)
    result["atm_straddle"] = round(straddle, 2)
    result["expected_move_pct"] = round(straddle / spot * 100, 2)
    return result


def unusual_options(symbol: str, expiries: int = 3, min_vol_oi: float = 2.0, min_volume: int = 500) -> list[dict]:
    """Contracts trading far above their open interest (possible fresh positioning) in the next few expiries."""
    t = yf.Ticker(symbol)
    hits = []
    for expiry in t.options[:expiries]:
        chain = t.option_chain(expiry)
        for side, df in (("call", chain.calls), ("put", chain.puts)):
            df = df[(df["volume"] >= min_volume) & (df["volume"] >= min_vol_oi * df["openInterest"].clip(lower=1))]
            for row in df.itertuples():
                hits.append({
                    "expiry": expiry, "type": side, "strike": row.strike, "volume": row.volume,
                    "open_interest": row.openInterest, "vol_oi": row.volume / max(row.openInterest, 1),
                    "last": row.lastPrice, "iv": row.impliedVolatility,
                })
    return _clean(sorted(hits, key=lambda h: h["volume"], reverse=True))


def put_call_ratio(symbol: str, expiries: int = 4) -> dict:
    """Volume and open-interest put/call ratios across the nearest expiries."""
    t = yf.Ticker(symbol)
    cv = pv = coi = poi = 0
    for expiry in t.options[:expiries]:
        chain = t.option_chain(expiry)
        cv += chain.calls["volume"].fillna(0).sum()
        pv += chain.puts["volume"].fillna(0).sum()
        coi += chain.calls["openInterest"].fillna(0).sum()
        poi += chain.puts["openInterest"].fillna(0).sum()
    return _clean({
        "symbol": symbol.upper(), "expiries": t.options[:expiries],
        "call_volume": cv, "put_volume": pv, "pc_volume_ratio": pv / cv if cv else None,
        "call_oi": coi, "put_oi": poi, "pc_oi_ratio": poi / coi if coi else None,
    })


# ------------------------------------------------------------ meme coins (DEX)


def _pair_summary(p: dict) -> dict:
    return {
        "chain": p.get("chainId"),
        "dex": p.get("dexId"),
        "pair_address": p.get("pairAddress"),
        "base": f'{p["baseToken"]["symbol"]} ({p["baseToken"]["address"]})',
        "quote": p["quoteToken"]["symbol"],
        "price_usd": p.get("priceUsd"),
        "price_change_pct": p.get("priceChange"),
        "volume_usd": p.get("volume"),
        "txns": p.get("txns"),
        "liquidity_usd": (p.get("liquidity") or {}).get("usd"),
        "fdv": p.get("fdv"),
        "market_cap": p.get("marketCap"),
        "pair_created": datetime.fromtimestamp(p["pairCreatedAt"] / 1000).isoformat() if p.get("pairCreatedAt") else None,
        "url": p.get("url"),
    }


def dex_search(query: str, limit: int = 10) -> list[dict]:
    """Search DexScreener pairs by token name, symbol or address. Sorted by liquidity."""
    r = requests.get(f"{DEX_API}/latest/dex/search", params={"q": query}, timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    pairs = sorted(r.json().get("pairs") or [], key=lambda p: (p.get("liquidity") or {}).get("usd") or 0, reverse=True)
    return [_pair_summary(p) for p in pairs[:limit]]


def dex_token(chain: str, token_address: str) -> list[dict]:
    """All DEX pairs for a token on a chain (e.g. chain='solana', 'base', 'ethereum', 'bsc')."""
    r = requests.get(f"{DEX_API}/tokens/v1/{chain}/{token_address}", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    return [_pair_summary(p) for p in r.json()]


def dex_boosted(chain: str | None = None, limit: int = 20) -> list[dict]:
    """Tokens with the most active DexScreener boosts (paid promotion: a hype gauge, not a quality signal)."""
    r = requests.get(f"{DEX_API}/token-boosts/top/v1", timeout=HTTP_TIMEOUT)
    r.raise_for_status()
    rows = [b for b in r.json() if not chain or b.get("chainId") == chain]
    return [{k: b.get(k) for k in ("chainId", "tokenAddress", "totalAmount", "description", "url")} for b in rows[:limit]]


def meme_risk_check(chain: str, token_address: str) -> dict:
    """Quick red-flag scan for a meme coin from DEX data: liquidity, age, FDV/liquidity, buy/sell skew.

    Heuristics only; it cannot see mint/freeze authority, holder concentration or LP locks.
    """
    pairs = dex_token(chain, token_address)
    if not pairs:
        return {"error": "no pairs found"}
    main = max(pairs, key=lambda p: p["liquidity_usd"] or 0)
    flags = []
    liq = main["liquidity_usd"] or 0
    fdv = main["fdv"] or 0
    if liq < 50_000:
        flags.append(f"thin liquidity (${liq:,.0f}); large orders will slip hard")
    if fdv and liq and fdv / liq > 50:
        flags.append(f"FDV is {fdv / liq:.0f}x liquidity; price is easy to push around")
    if main["pair_created"]:
        age_h = (datetime.now() - datetime.fromisoformat(main["pair_created"])).total_seconds() / 3600
        if age_h < 24:
            flags.append(f"pair is only {age_h:.1f}h old")
    h1 = (main["txns"] or {}).get("h1") or {}
    if h1.get("sells", 0) and h1.get("buys", 0) / h1["sells"] < 0.5:
        flags.append("sellers outnumber buyers 2:1 over the last hour")
    if (main["price_change_pct"] or {}).get("h24", 0) > 300:
        flags.append("up >300% in 24h; late-entry risk")
    return {"pair": main, "pair_count": len(pairs), "red_flags": flags or ["none from DEX data"]}


# ------------------------------------------------------------------- risk math


def position_size(account_size: float, risk_pct: float, entry: float, stop: float, multiplier: float = 1) -> dict:
    """Shares/contracts to buy so a stop-out loses risk_pct of the account. multiplier=100 for options, 50 for ES, etc."""
    per_unit = abs(entry - stop) * multiplier
    risk_dollars = account_size * risk_pct / 100
    units = math.floor(risk_dollars / per_unit) if per_unit else 0
    return {"units": units, "risk_dollars": round(risk_dollars, 2), "risk_per_unit": round(per_unit, 2),
            "position_value": round(units * entry * multiplier, 2)}


TOOLS = [quote, technicals, expirations, option_chain, unusual_options, put_call_ratio,
         dex_search, dex_token, dex_boosted, meme_risk_check, position_size]


def serve() -> None:
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("market-scout")
    for fn in TOOLS:
        server.tool()(fn)
    server.run()


CLI = {
    "quote": lambda a: quote(a[0]),
    "ta": lambda a: technicals(*a),
    "expiries": lambda a: expirations(a[0]),
    "chain": lambda a: option_chain(a[0], a[2] if len(a) > 2 and a[1] == "--expiry" else None),
    "unusual": lambda a: unusual_options(a[0]),
    "pcr": lambda a: put_call_ratio(a[0]),
    "dex": lambda a: dex_search(" ".join(a)),
    "token": lambda a: dex_token(a[0], a[1]),
    "boosted": lambda a: dex_boosted(a[0] if a else None),
    "risk": lambda a: meme_risk_check(a[0], a[1]),
    "size": lambda a: position_size(*map(float, a)),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "serve":
        serve()
    elif sys.argv[1] in CLI:
        print(json.dumps(CLI[sys.argv[1]](sys.argv[2:]), indent=2, default=str))
    else:
        sys.exit(f"commands: serve, {', '.join(CLI)}")
