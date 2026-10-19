# Overnight Earnings Trade: Findings

Research notes from backtesting `over_night_eraning_trade.py` (as of 2026-10-18).

## Strategy

For an earnings release **after the close (amc)**:

- **Entry:** last trade before 19:45 ET on the report day (15 min before the after-hours close).
- **Exits:** official opening auction, first regular-session trade, every 5 min up to +40m, and the day-0 regular close.
- **Before-open (bmo) releases** are excluded: buying the evening before means buying ahead of the report.

Gap follow-through is studied separately for every release (amc or bmo) whose reaction session gapped up at least 2%.

## Data

| Source | Used for |
|---|---|
| FMP historical earnings calendar | release dates, bmo/amc timing, EPS and revenue estimate vs actual |
| Alpaca 5-min bars (SIP feed, split/dividend adjusted) | extended-hours intraday data, T-2..T+2 around each release |
| yfinance daily bars | T-5..T+10 windows, 20/50/200-day SMAs, 52-week high/low, sector ETF and SPY |
| yfinance `eps_trend` | consensus EPS 0/7/30/60/90 days ago, a proxy for guidance changes (latest release only) |

Covers each ticker's last 4 releases, roughly 2025-10 to 2026-09: **one market regime**.

| Set | Tickers | Overnight trades |
|---|---|---|
| TradingView earnings store (`tradingview_scraper/company_earnings_data`) | 1,741 | 5,693 |
| QQQ (Nasdaq-100) | 101 | 261 |
| S&P 500, 200 closest to 52-week high (2026-10-17) | 200 | 317 |
| User picks: beat + raised guidance, selected at report time | 27 | 100 |

**Liquid** below means at least 300K shares traded after hours, with a trade between 19:30 and 19:45. Otherwise the 19:45 "entry price" can be a stale print from hours earlier.

## Findings

### 1. Unfiltered, the overnight trade is a coin flip

Sell at the auction open:

| Set | Win | Avg | Median |
|---|---|---|---|
| TradingView | 49% | +0.06% | 0.00% |
| QQQ | 44% | -0.12% | -0.28% |
| S&P near 52-week high | 59% | +0.40% | +0.36% |

The S&P near-high result is selection bias: those stocks are near highs *because* their reactions were good. With liquid trades only it drops to 51% and -0.04%.

### 2. After-hours direction helps a little, mostly in small and mid caps

Liquid trades, sell at the open:

| Set | Up after hours | Down after hours | Up more than 10% |
|---|---|---|---|
| TradingView | 54%, +0.87% | 48%, -0.27% | 55%, +1.49% |
| QQQ | 46%, +0.08% | 40%, -0.50% | 44%, -0.61% |
| S&P near high | 55%, +0.21% | 48%, -0.32% | (4 trades) |

The direction is consistent across all three sets, but the edge is under 1–1.5% before spreads and slippage.

### 3. Earnings beat + raised guidance is the core filter

There's no guidance feed yet, so the stand-in is "consensus estimates raised": next-quarter EPS estimate up more than 2% and current fiscal year up. General set, latest release only:

| Filter | Trades | Win at open | Avg at open | Avg at +40m |
|---|---|---|---|---|
| All | 1,462 | 53% | +0.49% | +0.52% |
| Beat (EPS and revenue) | 758 | 60% | +1.05% | +1.18% |
| Estimates raised | 316 | 59% | +1.02% | +1.28% |
| **Beat + raised** | **224** | **62%** | **+1.28%** | **+1.68%** (median +1.08%) |
| **Beat + raised + up after hours** | **144** | **65%** | **+1.62%** | **+1.95%** (median +1.47%) |
| Beat but estimates cut | 184 | 58% | +0.67% | +0.50% (median -0.42%) |
| Miss or in line, estimates cut | 232 | 47% | +0.20% | -0.27% |

- **Guidance matters more than the beat.** A beat with estimates cut fades through the morning.
- **The stand-in is optimistic.** It's measured 7–30 days after the release, so it partly includes analysts reacting to the price move.
- **The user's picks** are selected on beat + raised guidance at report time, not in hindsight.

### 4. The technical score: with the catalyst, it decides whether to hold past the open

Each trade gets one point for each condition, all known at the 19:45 entry. This is the `technical_score` column in the script:

1. Report-day close above the 20-day SMA.
2. Positive 5-day run-up into the report.
3. More than 10% room to the next resistance: the nearest 20/50/200-day SMA or 52-week high above the entry price. No resistance above counts as room.
4. After-hours volume at least 0.3× the average daily volume.
5. Report-day close less than 20% above the 200-day SMA (not overextended).

| Score | User picks (100): open / +40m / day-0 close | General beat + raised (224): open / +40m / day-0 close |
|---|---|---|
| 0–2 | +0.61% / -0.59% / +0.81% | +1.32% / +0.72% / +0.90% (median ≈ 0 after the open) |
| 3 | +1.39% / +1.45% / +1.71% | +1.41% / **+2.38%** / **+3.56%** (median +2.8% at close) |
| 4–5 | **+4.37% / +7.09% / +7.20%** | +1.05% / **+2.58%** / +2.55% |

**Rule of thumb, with beat + raised guidance:** at score 3 or higher, hold to +40m or the close; at score 0–2, sell at the open.

**Without the catalyst the score has no edge.** Among general EPS-and-revenue beats with no guidance information (2,645 trades), scores 0–4 all sit around +0.3% to +0.5% at the open, and the liquid-only results are flat. Technical setup amplifies a fundamental catalyst; it doesn't replace one.

How consistent each signal is:

| Signal | User picks | General beats | General beat + raised | Verdict |
|---|---|---|---|---|
| Room to resistance >10% | ✅ | ✅ | ✅ (+1.67% vs +1.00%) | most reliable |
| Not overextended (<20% above SMA200) | ✅ | ✅ | ✅ (+1.47% vs +1.00%) | most reliable |
| Above SMA20 | ✅ | ✅ | neutral | useful |
| 5-day run-up > 0 | ✅ | ✅ | higher win rate | useful |
| After-hours volume ≥ 0.3× average | ✅ | ✅ at open | reverses | weakest; in the score for consistency with the picks |
| Big after-hours move / holding near after-hours high | ✅ | reverses | — | only works with the catalyst |
| After-hours break above the 52-week high | ✅ (16) | -1.42% (198) | — | avoid without the catalyst |

### 5. Gap follow-through on the reaction day

For gap-ups of at least 2%, a 10-minute opening range, and buying **at the breakout level** (no lookahead):

| Set | Long on opening-range break up | After break down |
|---|---|---|
| TradingView (1,011 / 1,033) | 51% win, +0.78% avg, +0.18% median | -0.35% |
| QQQ (69 / 79) | 64% win, +0.89% avg, +0.79% median | -0.26% |
| S&P near high (131 / 127) | 49%, +0.05% | +0.13% |

Judged from 10:00 to the close, the other signals were weak or didn't generalize:

- **Gap size:** no effect in the large set.
- **Opening above the 52-week high:** no effect.
- **First-30-minute volume vs earlier earnings days:** small edge in TradingView and QQQ (about +0.9% vs +0.1%).
- **VWAP at 10:00:** weak.
- **T+1 drift:** about 0.

Typical gap-up day range from the open: TradingView +5.8% / -5.5%, QQQ +3.7% / -3.9%, S&P near high +3.0% / -2.7%.

## Pitfalls hit along the way

- **Small hand-picked samples mislead.** The first 15 picks showed 66% wins and +2.9% at the open. About half of that came from their profile (liquid, volatile, big after-hours moves) and the rest from the guidance catalyst. A broad sample is required before trusting any filter.
- **Lookahead in opening-range tests.** Grouping by "broke up" and measuring from 9:40 uses future information; measure from the breakout price instead. The same applies to volume and VWAP measured "from the open": judge them from the time they're known (10:00).
- **Stale after-hours prints.** Illiquid names can show a "19:45 price" from 16:30. The `entry_staleness_min` column shows how old the entry trade was; `--max-entry-staleness 15` skips stale entries. On the user picks, the edge held with fresh entries only: 78 trades, 63% win, +1.91% at the open, vs 100 trades, 65%, +1.96% unfiltered.
- **Full-day volume isn't an early signal.** `day_vol_vs_prior_earnings` is only known at the close, so it's reported as an outcome. Use `early_vol_vs_prior_earnings` (first 30 minutes) as the setup signal.
- **Unknown release timing** makes the reaction session ambiguous, so those releases are excluded from gap follow-through, as they already are from the overnight trade.
- **EPS surprise % is meaningless for tiny estimates** (2¢ estimate, 5¢ actual shows as +150%). Use revenue surprise there.
- **FMP timeouts** used to fall back silently to yfinance earnings dates, which are stale (they stop in 2025). The collector now retries FMP once and logs a warning on fallback.

## Reproduce

```bash
# collect + backtest a list (6 parallel workers, resumable, summaries only)
python over_night_eraning_trade.py --tickers-file tickers.txt --collect --resume --workers 6 --summary-only --output out.csv

# per-ticker detail: earnings results, technical setup, per-trade returns, levels, forecast revision, gap follow-through
python over_night_eraning_trade.py MDB PL --collect
```

Per-trade CSVs (`out.csv`, `out_follow_through.csv`) include every column used above, including `technical_score`.

## Next steps

- **Guidance from the spreadsheet:** when it's added, filter beat + guidance raised directly across all quarters, and re-check the technical-score rule.
- **Costs:** add spread and slippage assumptions; most edges here are 1–2%.
- **More history:** extend to 8+ quarters (`--quarters 8`) to cover more than one market regime.
- **Forward test:** log picks before each report and compare outcomes.
