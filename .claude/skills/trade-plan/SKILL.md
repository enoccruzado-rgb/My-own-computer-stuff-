---
name: trade-plan
description: Build a written trade plan for a day or swing trade in stocks, options, futures, crypto or meme coins. Use when the user asks to analyze a ticker or token, find an options play, size a position, check a meme coin, or "should I buy/sell X". Pulls data from the market-scout, alpaca, tastytrade and ccxt MCP servers when they are connected.
---

# Trade plan

Produce a plan the user can act on or reject, not a prediction. Every plan names its exit before its entry.

## 1. Pin down the setup

Ask only for what is missing:
- Instrument and direction (long / short / neutral).
- Timeframe: day trade (closes today), swing (2 days to 6 weeks).
- Account size and max risk per trade (default 1% if unstated; say you assumed it).

## 2. Gather data (use tools, never guess prices)

| Need | Tool |
|---|---|
| Price, range, volume | `market-scout.quote` |
| Trend / momentum | `market-scout.technicals` (`interval="5m", period="5d"` for day trades; `1d`/`6mo` for swings) |
| Option chain + greeks + expected move | `market-scout.option_chain` |
| Positioning | `market-scout.unusual_options`, `market-scout.put_call_ratio` |
| Meme coin | `market-scout.dex_search` -> `market-scout.meme_risk_check` |
| Crypto CEX order book, funding, OI | `ccxt` tools |
| Live account, positions, buying power | `alpaca` or `tastytrade` tools |

Yahoo data is ~15 min delayed. Say so when giving intraday levels and prefer broker data when connected.

## 3. Options-specific rules

- Compare the trade's breakeven with the chain's `expected_move_pct`. A long option that needs more than the expected move to profit is a lottery ticket; say so.
- IV high relative to recent realized move (ATR% x sqrt(days)) favours selling premium (credit spreads, iron condors); low IV favours buying (debit spreads, long calls/puts).
- Prefer defined-risk spreads over naked short options. Never suggest naked short calls.
- Day trades: avoid contracts with bid/ask spread > 10% of mid or open interest < 500.
- Swings: avoid holding long options inside 21 DTE unless that is the thesis; theta accelerates.
- Flag earnings, FOMC, CPI dates inside the holding window when known.

## 4. Meme coin rules

- Run `meme_risk_check` first. Any red flag goes at the top of the plan, not buried.
- Size so that a 100% loss is acceptable; meme coins can and do go to zero within hours.
- Note that DEX data cannot see mint/freeze authority, holder concentration or LP locks; tell the user to check those on a tool such as RugCheck or Solscan before buying.

## 5. Size it

Call `market-scout.position_size(account_size, risk_pct, entry, stop, multiplier)`. Multiplier: 1 shares/crypto, 100 equity options, 50 ES, 5 MES, 20 NQ, 2 MNQ.

## 6. Output format

```
SETUP      <instrument> <direction> <timeframe>
THESIS     one or two sentences on why, with the data that supports it
ENTRY      price or trigger
STOP       price, and why there
TARGETS    T1 / T2 with R-multiples
SIZE       units, $ at risk, % of account
INVALIDATION  what would make you skip or exit early
RISKS      events, liquidity, red flags
```

## 7. Placing orders

Only place an order when the user explicitly asks to, after showing the exact order (symbol, side, qty, type, limit, time-in-force) and getting a yes. Confirm whether the account is paper or live before every order.

This is analysis, not financial advice; the user makes the call.
