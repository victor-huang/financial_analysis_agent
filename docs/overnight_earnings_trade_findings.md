# Overnight Earnings Trade: Findings

Research notes from backtesting `over_night_eraning_trade.py` (as of 2026-10-20).

## Current rules (what survived)

For a long overnight trade on an after-close release, **sell at the open**:

| Rule | Conditions | Median at open, by quarter (Oct–Dec '25 / Jan–Mar '26 / Apr–Jun '26 / Jul–Sep '26) |
|---|---|---|
| **E** | $100M–$10B market cap, EPS and revenue beat, after-hours move **1–3× the stock's average daily range**, fresh entry | +0.77% / +0.78% / +0.57% / +2.49% (win 65% / 56% / 52% / 76%) |
| **F** | E + revenue surprise **above the company's usual** surprise | +0.44% / +1.50% / +1.00% / +2.60% (win 60% / 59% / 59% / 76%) |

These are the only rules with a positive median in all four quarters, including Oct–Dec 2025, when the earlier rule (beat + up after hours) was flat. They come from 15–46 trades per quarter and from testing many combinations, so treat them as candidates to confirm on new releases (finding 10).

The table above uses the spreadsheet's earnings history. Re-run by the script itself, with the "usual surprise" from FMP's earnings history (4,014-ticker universe, fresh entries, sell at the open):

| | Oct–Dec '25 | Jan–Mar '26 | Apr–Jun '26 | Jul–Sep '26 |
|---|---|---|---|---|
| Baseline: all $100M–$10B trades | 380, 42% win, -0.71% / median -0.58% | 414, 48%, +0.04% / -0.22% | 423, 51%, +0.27% / +0.05% | 429, 54%, +0.55% / +0.50% |
| Earlier rule: beat + up after hours | 74, 43%, -0.70% / -0.63% | 115, 51%, +0.30% / +0.66% | 142, 58%, +1.71% / +1.08% | 141, 71%, +2.09% / +1.69% |
| **Rule E** | 27, 52%, +0.69% / +0.16% | 50, 52%, +0.20% / +0.41% | 63, 52%, +1.45% / +0.68% | 68, 71%, +2.51% / +2.25% |
| **Rule F** | 21, 52%, +0.85% / +0.16% | 37, 54%, +0.81% / +0.78% | 49, 55%, +1.92% / +1.00% | 57, 68%, +2.28% / +1.77% |

Both rules keep a positive median in every quarter with this independent source; F beats each quarter's baseline by +0.8 to +1.7 points. Holding to +40m or the close is again mixed (rule E lost at both in Jan–Mar 2026).

**Avoid:** misses, which keep falling after the release; large caps, which show no edge; and large caps near their 52-week highs as shorts (they get bought).

```bash
# rule E
python over_night_eraning_trade.py --tickers-file tickers.txt --min-market-cap 0.1 --max-market-cap 10 \
  --min-eps-surprise 0 --min-revenue-surprise 0 --min-ah-move-x-range 1 --max-ah-move-x-range 3 \
  --max-entry-staleness 15 --summary-only
# rule F: add --min-revenue-vs-usual 0
```

Every edge here is roughly 1–2% before spreads, slippage and (for shorts) borrowing costs, measured over one year of data, and **whether the trade makes money depends on the market environment** (finding 5).

## Strategy

For an earnings release **after the close (amc)**:

- **Entry:** last trade before 19:45 ET on the report day (15 min before the after-hours close).
- **Exits:** official opening auction, first regular-session trade, every 5 min up to +40m, and the day-0 regular close.
- **Before-open (bmo) releases** are excluded: buying the evening before means buying ahead of the report.
- **Short variant (`--short`):** short at the entry, buy back at the same exits.

Gap follow-through is studied separately for every release (amc or bmo) whose reaction session gapped up at least 2%.

## Data

| Source | Used for |
|---|---|
| FMP historical earnings calendar | release dates, bmo/amc timing, EPS and revenue estimate vs actual |
| FMP quotes | current market cap (for `--min/--max-market-cap`) |
| Alpaca 5-min bars (SIP feed, split/dividend adjusted) | extended-hours intraday data, T-2..T+2 around each release |
| yfinance daily bars | T-5..T+10 windows, 20/50/200-day SMAs, 52-week high/low, sector ETF and SPY |
| yfinance `eps_trend` | consensus EPS 0/7/30/60/90 days ago, a proxy for guidance changes (latest release only) |
| Earnings spreadsheet, tabs "Q1 26 earning" / "Q2 26 earning" | adjusted-EPS and revenue beat %, growth, `hot?`, `Fast grow?`, guidance vs consensus, `2nd day gain %` |

Covers each ticker's last 4 releases, roughly 2025-10 to 2026-09: **one market regime**.

| Set | Tickers | Overnight trades |
|---|---|---|
| TradingView earnings store (`tradingview_scraper/company_earnings_data`) | 1,741 | 5,693 |
| QQQ (Nasdaq-100) | 101 | 261 |
| S&P 500 (all constituents) | 503 | 860 |
| Spreadsheet Q1 + Q2 2026 seasons | ~3,250 per season | 6,160 releases (4,257 with `2nd day gain %`) |
| User picks: beat + raised guidance, selected at report time | 27 | 100 |

**Liquid** below means at least 300K shares traded after hours, with a trade between 19:30 and 19:45. Otherwise the 19:45 "entry price" can be a stale print from hours earlier.

## Findings

### 1. Unfiltered, the overnight trade is a coin flip

Sell at the auction open:

| Set | Win | Avg | Median |
|---|---|---|---|
| TradingView | 49% | +0.06% | 0.00% |
| QQQ | 44% | -0.12% | -0.28% |
| S&P 500, 200 nearest 52-week high | 59% | +0.40% | +0.36% |

The S&P near-high result is selection bias: those stocks are near highs *because* their reactions were good. With liquid trades only it drops to 51% and -0.04%.

### 2. After-hours direction helps a little, mostly in small and mid caps

Liquid trades, sell at the open:

| Set | Up after hours | Down after hours | Up more than 10% |
|---|---|---|---|
| TradingView | 54%, +0.87% | 48%, -0.27% | 55%, +1.49% |
| QQQ | 46%, +0.08% | 40%, -0.50% | 44%, -0.61% |
| S&P near high | 55%, +0.21% | 48%, -0.32% | (4 trades) |

### 3. Earnings beat + raised guidance is the core filter

With no guidance feed, the stand-in is "consensus estimates raised": next-quarter EPS estimate up more than 2% and current fiscal year up. General set, latest release only:

| Filter | Trades | Win at open | Avg at open | Avg at +40m |
|---|---|---|---|---|
| All | 1,462 | 53% | +0.49% | +0.52% |
| Beat (EPS and revenue) | 758 | 60% | +1.05% | +1.18% |
| Estimates raised | 316 | 59% | +1.02% | +1.28% |
| **Beat + raised** | **224** | **62%** | **+1.28%** | **+1.68%** |
| **Beat + raised + up after hours** | **144** | **65%** | **+1.62%** | **+1.95%** |
| Beat but estimates cut | 184 | 58% | +0.67% | +0.50% (median -0.42%) |
| Miss or in line, estimates cut | 232 | 47% | +0.20% | -0.27% |

The stand-in is optimistic: it's measured 7–30 days after the release, so it partly includes analysts reacting to the price move. The user's picks are selected on beat + raised guidance at report time, not in hindsight.

### 4. The technical score: informative, but the "hold past the open" rule did not replicate

Each trade gets one point for each condition, all known at the 19:45 entry (`technical_score` column):

1. Report-day close above the 20-day SMA.
2. Positive 5-day run-up into the report.
3. More than 10% room to the next resistance: the nearest 20/50/200-day SMA or 52-week high above the entry price. No resistance above counts as room.
4. After-hours volume at least 0.3× the average daily volume.
5. Report-day close less than 20% above the 200-day SMA (not overextended).

On the first data (the user's picks and the latest-quarter beat + raised set), a score of 3 or more favored holding to +40m or the close:

| Score | User picks (100): open / +40m / day-0 close | General beat + raised (224): open / +40m / day-0 close |
|---|---|---|
| 0–2 | +0.61% / -0.59% / +0.81% | +1.32% / +0.72% / +0.90% |
| 3 | +1.39% / +1.45% / +1.71% | +1.41% / +2.38% / +3.56% |
| 4–5 | +4.37% / +7.09% / +7.20% | +1.05% / +2.58% / +2.55% |

**It did not hold up across seasons.** Using the spreadsheet's beats on $100M–$10B stocks (double beat + up after hours, fresh entries):

| Score ≥ 3 | Q1 2026 season | Q2 2026 season |
|---|---|---|
| Sell at open | 32 trades, 53% win, +1.22% | 46 trades, 74% win, +2.28% |
| Hold to +40m | 44% win, -0.56% (median -2.11%) | 52% win, +2.73% |

So the score is kept as information, but the rule is **sell at the open**. Without a catalyst the score has no edge at all (general beats: +0.3% to +0.5% at every score).

### 5. Market cap: the edge sits in $100M–$10B

Overnight trade, double beat (spreadsheet) + up after hours, fresh entries, sell at the open:

| Market cap | Q1 2026 season | Q2 2026 season |
|---|---|---|
| **$100M–$10B** | **57 trades, 54% win, +0.80% (median +0.45%)** | **71 trades, 72% win, +1.73% (median +1.14%)** |
| >$10B | 35 trades, 49% win, -0.17% | 41 trades, 51% win, +0.99% (median +0.02%) |
| <$100M | 1–4 trades per season | too few |

The reaction itself (`2nd day gain %`, reaction-day close vs prior close) shows the same split:

| Rule | $100M–$10B, Q1 | $100M–$10B, Q2 | >$10B, Q1 / Q2 |
|---|---|---|---|
| Double beat + revenue beat >3% | 59% up, +3.1% | 68% up, +5.6% | +2.5% / +0.0% |
| EPS or revenue miss | 32% up, -3.6% | 35% up, -3.2% | -0.0% / -0.8% |

Large caps barely react to beats or misses; mid caps react strongly in both directions. Market cap here is the current value at collection time, not on each release date.

**Correction: the spreadsheet's two seasons were the two best quarters.** Its "Q1/Q2 2026" seasons were reported in Apr–Jun and Jul–Sep 2026. Using FMP beats for all four calendar quarters (sell at the open):

| | Oct–Dec '25 | Jan–Mar '26 | Apr–Jun '26 | Jul–Sep '26 |
|---|---|---|---|---|
| $100M–$10B + beat + up after hours | 77 trades, 44% win, -0.65% / median -0.57% | 113, 51%, +0.30% / +0.66% | 141, 58%, +1.75% / +1.17% | 140, 72%, +2.33% / +1.84% |
| All fresh trades (baseline) | -0.71% | -0.13% | +0.18% | +0.16% |

The rule beat the baseline every quarter (+0.1 to +2.2 points), but in absolute terms it lost money in late 2025. Overnight earnings trades as a whole drift with the market environment.

### 6. What the spreadsheet adds: it predicts the reaction, but the reaction is priced within minutes

The spreadsheet's `2nd day gain %` is the reaction-day close vs the prior close (correlation 0.91 with price data; not the following day, 0.06).

- **The spreadsheet's beat columns predict the reaction.** A model trained on one season and tested on the other ranked releases with a correlation of 0.14–0.17; its top 10% averaged +2.8% to +3.2% (34–37% gained more than 5%, vs 17–22% overall). Double beat + revenue beat >3% averaged +2.9% / +3.9% across the two seasons; misses -2.9% / -3.2%.
- **The spreadsheet's adjusted-EPS beats work better than FMP's.** Where they disagree, FMP-only beats returned less (+0.68% vs +1.62% at the open, with after-hours up).
- **`hot?` and `Fast grow?` don't predict the reaction** (correlation ≈ 0). `hot?` names did well at the open but faded by +40m.
- **After the news is priced in, there's no consistent edge.** Buying $100M–$10B after-close reporters at 16:30 or 17:00 and selling at the reaction-day close: double beat + revenue beat >3% was +1.0% to +1.9% in Q1 but -0.1% to +0.5% average (median -1.3% to -1.8%) in Q2. By 16:30 the median double beat had already done nearly its whole reaction. Capturing it would require entering within minutes of the release.
- **Misses keep drifting down** after the release in both seasons ($100M–$10B: -0.6% to -2.7% from 16:30 to the close).

### 7. Short variant (`--short`)

| Set | Setup 1: short every double miss (EPS ≤ -2%, revenue ≤ -0.5%) | Setup 2: double miss + **up** after hours (relief rally) |
|---|---|---|
| TradingView, fresh entries | 316 trades, 56% win, +0.41% at open | **51 trades, 61% win, +1.25% at open, +1.32% at +40m** |
| QQQ | 6 trades, 67% win, +3.5% (mostly HONA, DASH) | 2 trades, 1 win |
| S&P 500, all | 39 trades, 41% win, -0.33% | 7 trades, 43% win, -1.05% |
| S&P 500, within 5% of 52-week high | 8 trades, 12% win, -1.83% | — |

- The relief-rally short is a **small/mid-cap** pattern. In large caps, misses get bought, especially near the 52-week high, where shorts lost 7 of 8.
- Many of the 51 small/mid-cap trades are hard to borrow, especially after hours.

### 8. Gap follow-through on the reaction day

For gap-ups of at least 2%, a 10-minute opening range, and buying **at the breakout level** (no lookahead):

| Set | Long on opening-range break up | After break down |
|---|---|---|
| TradingView (1,011 / 1,033) | 51% win, +0.78% avg, +0.18% median | -0.35% |
| QQQ (69 / 79) | 64% win, +0.89% avg, +0.79% median | -0.26% |
| S&P near high (131 / 127) | 49%, +0.05% | +0.13% |

Judged from 10:00 to the close, gap size, opening above the 52-week high, VWAP and T+1 drift were weak or didn't generalize; first-30-minute volume vs earlier earnings days gave a small edge in TradingView and QQQ (about +0.9% vs +0.1%).

### 9. Trades up 10% or more: volatility, not direction

About 11–14% of fresh-entry trades each quarter gain at least 10% by the day-0 open or close. Compared with other trades, they are consistently smaller (median market cap $0.9–2.0B vs $2.1–2.9B), cheaper, more volatile (average daily range 5–6% vs 4.4–5.3%), less traded, and further below their 52-week high. But the same traits produce as many or more **losses of 10% or more**: market cap <$2B gave 12–18% big winners vs 15–24% big losers. They predict the *size* of the move, not its direction. A walk-forward model (train on earlier quarters, test on the next) picked big winners only modestly better than chance: 19–25% of its top 10% vs a 13–14% base rate.

### 10. Earnings consistency, surprise size and move size

From the spreadsheet's 8-quarter history ("ERN DataBase" tab; 1,639 trades where its EPS matches FMP's for the release). Cells are the excess over each quarter's baseline average, sell at the open:

| Signal | Oct–Dec '25 | Jan–Mar '26 | Apr–Jun '26 | Jul–Sep '26 |
|---|---|---|---|---|
| Beat + **prior beat streak 3+** | -0.13 | -0.86 | +0.30 | +0.28 |
| Beat + **streak 0** (first beat after misses) | -0.10 | +1.18 | +1.07 | +1.07 |
| Beat, **EPS surprise above the company's usual** | **+0.75** | **+0.94** | **+0.80** | **+0.79** |
| Beat, EPS surprise below usual | -0.15 | -0.96 | +0.07 | -0.09 |
| Beat, **revenue surprise above usual** | **+0.44** | **+0.68** | **+1.02** | **+0.77** |
| After-hours move **1–3× daily range** | **+1.11** | **+1.29** | **+1.02** | **+1.83** |
| After-hours move 0–1× daily range | -0.18 | -0.02 | -0.15 | +0.10 |
| After-hours move down | -0.55 | -0.44 | -0.60 | -1.32 |

- **Consistent beaters do worse:** the market expects their beat. A beat that is **bigger than the company usually delivers** beat the baseline in every quarter.
- **Move size matters relative to volatility:** 1–3× the stock's normal daily range worked every quarter; small moves added nothing, and moves over 3× were hit or miss.
- Holding to the day-0 close still lost money in Oct–Dec 2025 for every combination, so sell at the open.
- Adding these features to the walk-forward model didn't improve it; simple rules (E, F) did better.

The script computes the same signals from FMP's earnings history (median of the previous 4 releases' surprises, capped at ±100% EPS / ±50% revenue): `eps_vs_usual_pts`, `revenue_vs_usual_pts`, `prior_beat_streak` and `ah_move_x_range`.

## Pitfalls hit along the way

- **Validating on the best quarters.** The rules from the spreadsheet's two seasons looked strong because those were the two best calendar quarters. Always check every quarter available and compare with that quarter's baseline.
- **Volatility looks like a winner signal.** Traits of +10% winners (small, cheap, volatile) also produce -10% losers. Check both tails before calling a trait predictive.

- **Small hand-picked samples mislead.** The first 15 picks showed 66% wins and +2.9% at the open; the broad sample was a coin flip. A filter has to survive a large sample and a second season.
- **A rule that works in one season may not in the next.** The technical-score hold rule worked on the latest quarter and the user's picks, then lost money in the Q1 2026 season.
- **Selectively filled columns create fake predictors.** The spreadsheet's guidance columns were filled for ~3% of rows, mostly stocks that then moved big: filled rows averaged +14% on the reaction day vs -0.5% for blank rows, and even "guidance at/below consensus" averaged +9%. Guidance must be recorded for every ticker at report time before its effect can be measured.
- **Entering before the news is out.** A 16:15 entry looked strong (+3% to +6%) because at 16:15 the price had barely moved (+0.01 pts of a +3.3% median reaction): many releases weren't priced yet. Test entries from when the news is reliably out (16:30+), or use the exact release time.
- **Lookahead through derived features.** "Room to resistance" measured from a later price (the 9:25 pre-open price) leaked the pre-open move into a supposedly earlier signal. Every feature must be computed from the price at the entry time.
- **Mismatched rows.** About 24% of spreadsheet `2nd day gain %` values differ from price data by more than 3 points (e.g. BZFD: sheet -1%, actual +90%). Those rows are dropped.
- **Price-scale mismatches between sources.** A reverse split adjusted in only one source (OPAD 10×, CTVA ~6.7×) produced a fake +765% after-hours move. Trades whose intraday and daily closes differ by more than 15% are now skipped.
- **Lookahead in opening-range tests.** Grouping by "broke up" and measuring from 9:40 uses future information; measure from the breakout price instead.
- **Stale after-hours prints.** Illiquid names can show a "19:45 price" from 16:30. Use `entry_staleness_min` / `--max-entry-staleness 15`.
- **Full-day volume isn't an early signal** (`day_vol_vs_prior_earnings` is reported as an outcome).
- **Unknown release timing** makes the reaction session ambiguous; those releases are excluded.
- **EPS surprise % is meaningless for tiny estimates** (2¢ estimate, 5¢ actual shows as +150%). Use revenue surprise there.
- **FMP timeouts** used to fall back silently to stale yfinance earnings dates. The collector now retries FMP once and logs a warning on fallback.

## Reproduce

```bash
# collect + backtest a list (6 parallel workers, resumable, summaries only), $100M-$10B, fresh entries
python over_night_eraning_trade.py --tickers-file tickers.txt --collect --resume --workers 6 --summary-only \
  --min-market-cap 0.1 --max-market-cap 10 --max-entry-staleness 15 --output out.csv

# rule F: mid cap, double beat, revenue surprise above the company's usual, after-hours move 1-3x daily range
python over_night_eraning_trade.py --tickers-file tickers.txt --min-market-cap 0.1 --max-market-cap 10 \
  --min-eps-surprise 0 --min-revenue-surprise 0 --min-revenue-vs-usual 0 \
  --min-ah-move-x-range 1 --max-ah-move-x-range 3 --max-entry-staleness 15

# relief-rally short: double miss, up after hours
python over_night_eraning_trade.py --tickers-file tickers.txt --short --max-eps-surprise -2 --max-revenue-surprise -0.5 \
  --min-after-hours-move 0 --max-entry-staleness 15

# per-ticker detail: earnings results, technical setup, per-trade returns, peak/low, levels, forecast revision, gap follow-through
python over_night_eraning_trade.py MDB PL --collect
```

Per-trade CSVs (`out.csv`, `out_follow_through.csv`) include every column used above.

## Next steps

- **Spreadsheet data quality:** record guidance (`Rev/EPS next Q FC` and consensus, `Rev Q/Y FC up %`) for every ticker at report time; record release date, time and bmo/amc; fix `#DIV/0!`, `#VALUE!` and ±100% placeholder cells.
- **Immediate entries:** test entering within minutes of the release with 1-minute bars and estimated release times.
- **Costs:** add spread, slippage and borrowing assumptions; most edges here are 1–2%.
- **More history:** extend to 8+ quarters (`--quarters 8`) to cover more than one market regime.
- **Forward test rules E and F** on the Q3 2026 season (Oct–Nov 2026) and every season after, on releases that didn't exist when the rules were found.
- **Market-environment filter:** test whether trading only when recent earnings reactions are positive (or SPY is above its 50-day average) avoids quarters like Oct–Dec 2025.
