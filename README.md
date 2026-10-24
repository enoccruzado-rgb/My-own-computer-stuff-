# Trading toolkit for Claude Code

Day and swing trading setup for stocks, options, futures, crypto and meme coins: Python libraries, MCP servers Claude can call, and a `trade-plan` skill.

## Quick start

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # cloud sessions do this automatically
.venv/bin/python -m unittest discover -s tests                         # sanity check
cp .env.example .env          # add the broker keys you have
set -a; source .env; set +a
claude                        # MCP servers in .mcp.json load automatically
```

Then ask things like *"make a swing plan for AMD calls"*, *"check this Solana token: <address>"*, or *"what's SPY's expected move this week"*.

## What's included

### MCP servers (`.mcp.json`)

| Server | What it does | Keys needed | Safe default |
|---|---|---|---|
| `market-scout` (this repo) | Quotes, technicals (RSI/ATR/MACD/VWAP), option chains with greeks and expected move, unusual options activity, put/call ratio, DexScreener meme-coin search and red-flag check, position sizing | none | read-only |
| `alpaca` ([official](https://github.com/alpacahq/alpaca-mcp-server)) | Stocks, options (multi-leg), crypto: data, account, orders | Alpaca key | paper trading |
| `tastytrade` ([official](https://github.com/tastytrade/tastytrade-mcp)) | Options and futures: chains, positions, orders | tastytrade OAuth | sandbox |
| `ccxt` ([ccxt-mcp](https://www.npmjs.com/package/ccxt-mcp)) | 100+ crypto exchanges: tickers, order books, funding, OHLCV | optional | trading disabled |

### Python libraries (`requirements.txt`)

- **Data:** `yfinance`, `ccxt`
- **Brokers:** `alpaca-py`, `tastytrade`, `schwab-py` (thinkorswim), `ib_async` (Interactive Brokers, incl. futures)
- **Analysis/backtesting:** `pandas-ta-classic`, `vectorbt`, `backtrader`

### Market Scout CLI

```bash
.venv/bin/python tools/market_scout.py quote NVDA
.venv/bin/python tools/market_scout.py ta TSLA 5d 5m          # intraday technicals
.venv/bin/python tools/market_scout.py chain SPY --expiry 2026-11-21
.venv/bin/python tools/market_scout.py unusual AMD
.venv/bin/python tools/market_scout.py dex bonk
.venv/bin/python tools/market_scout.py risk solana <token_address>
.venv/bin/python tools/market_scout.py size 25000 1 4.20 2.10 100   # acct risk% entry stop multiplier
```

### Skill

`.claude/skills/trade-plan/` makes Claude produce a structured plan (entry, stop, targets, size, invalidation, risks) using the tools above, with options and meme-coin specific checks.

## Claude.ai connectors and plugins worth adding

Connect these at claude.ai → Settings → Connectors / Plugins (they can't be installed from code):

- **Connectors:** Alpha Vantage (stocks + options + indicators), CoinGecko and Crypto.com (free crypto data, no login), FMP and Financial Datasets (fundamentals, earnings), Webull (brokerage), TEXT TO QUANT (plain-English backtests), Coinversa Pulse (Hyperliquid whale flow).
- **Plugins:** TradingCalc (Black-Scholes, payoff, futures PnL/liquidation math), Crypto Spot Futures Analyzer, Crypto & Bitcoin Analyst.

## Safety

- Everything defaults to paper/sandbox/read-only. Flip `ALPACA_PAPER_TRADE`, `TASTYTRADE_USE_PRODUCTION` or `CCXT_MCP_TRADING` only on purpose.
- Use broker API keys with trading permission only on accounts you're willing to let an AI place orders in; withdrawal permission should always be off.
- Yahoo data is delayed ~15 min. Use broker data for live intraday levels.
- This is tooling for analysis, not financial advice.
