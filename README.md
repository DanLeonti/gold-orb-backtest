# Gold ORB 50% — backtest and range-filtered Pine script

Strategy: opening range 08:20–08:49 NY on GC (COMEX gold futures), trade window 08:50–13:59.
Bias at 08:50 = close vs ORB midpoint **and** session VWAP. Entry when price touches the 50% line
and closes back on the bias side; target = ORB edge, stop = opposite edge ("conservative") or
signal-bar wick ±0.2 ("aggressive"); time stop 14:00; one trade per day; Mon–Thu by default.

## Files
- `gold_orb_filtered.pine` — the strategy with the **ORB range filter** added (`Min ORB Range`, in points or % of price). Paste into TradingView on GC1! 1m or 5m.
- `gold_orb_original.pine` — the script as originally written, for reference.
- `gold_orb.py` — bar-by-bar Python port used for the numbers below (matches the Pine logic; fills next bar open, stop wins ties, costs 0.25 pt round trip = $25/contract).
- `orb_lab.py`, `orb_analyze.py` — vectorized 17k-config search (GC/NQ/ES, dev/holdout). Nothing in the family beats chance; see `results/orb_lab_grid_GC_NQ_ES.csv`.
- `news_gold*.py`, `news_fade.py` — 08:30 / 10:00 / FOMC news-impulse tests. No edge either way.
- `results/` — summary text files and trade lists.

Data: Databento `GLBX.MDP3`, `GC.v.0` (volume-rolled continuous), `ohlcv-1m`, 2022-07-01 → 2026-09-24,
expected at `out/GC_1m_4yr.parquet` (not in the repo — licensed data). Do **not** use `GC.c.0`: the
calendar roll picks illiquid serial months for gold.

## Result: unfiltered (as written)
1m, conservative stop, Mon–Thu, Jul 2022 → Sep 2026: n=490, 55% win, **−0.08R/trade**, t=−2.0.
Gross edge before costs is −0.02R — the 55% win rate is what a 1:1 bracket from the midpoint gives by chance.
5m: −0.11R. Aggressive wick stop is worse everywhere. Only 2026 is positive in $.

## Result: with ORB range ≥ 15 pt (the config chosen to trade)
| | n | win | avg R | t | PF | net $ (1 GC) | max DD $ |
|---|---|---|---|---|---|---|---|
| 1m, Mon–Thu, all 4 yr | 117 | 61% | +0.075 | 1.0 | 1.32 | +18.1k | −10.4k |
| 1m, Mon–Thu, 2025→2026-09 | 89 | 65% | +0.154 | 1.8 | 1.62 | +24.9k | −10.4k |
| 1m, Mon–Thu, last 6 mo | 36 | 69% | +0.219 | 1.6 | 1.92 | +11.7k | −5.0k |
| 5m, Mon–Thu, all 4 yr | 114 | 67% | +0.075 | 1.1 | 1.50 | +23.7k | −8.3k |
| 5m, Mon–Thu, 2025→2026-09 | 88 | 73% | +0.154 | 2.0 | 1.92 | +30.8k | −4.8k |
| 5m, Mon–Fri, 2025→2026-09 | 109 | 72% | +0.136 | 1.9 | 1.78 | +34.8k | −4.9k |

Trade profile (1m): median risk 12 pt ($1,220/contract), ~2.3 trades/month, 45% of Mon–Thu days qualify
at today's prices, 61% of entries before 09:30, median hold 27 min, longest losing streak 4, max DD −7.4R.
Longs and shorts contribute equally.

**Caveat (read before trading).** 77% of the filtered trades come from 2025–2026 because gold went
1,700 → 4,800 and a fixed 15 pt cutoff was rare before. Inside the filter, 2022/2023/2024 are −0.30 /
−0.38 / −0.04R. Normalizing the cutoff by price level (bps, or vs trailing-20-day median range) brings
the edge back to ~0R at every threshold. So the filter is partly a "2025–2026 regime" proxy. What it
verifiably does: it lifts risk from ~5 pt to ~12 pt per trade, which removes the cost drag. Whether the
+0.15R of the current regime persists is the open question the forward test below answers.

## Forward test (pre-registered)
Paper or 1-contract, 1m or 5m (pick one and don't switch), conservative stop, Mon–Thu, ORB ≥ 15 pt
(or 0.33% of price). Log every trade.
- **Confirm:** after 60 trades (~2 years at this rate, so consider MNQ-style micro sizing on MGC to run
  it live earlier), avg R > +0.10 and PF > 1.3.
- **Kill:** at any point after 30 trades, avg R < 0, or a drawdown worse than −10R (the backtest's worst
  is −7.4R), or three consecutive months negative.
- Don't add or tune parameters mid-test. If the rules change, the count restarts.

TradingView numbers will differ somewhat from the Python ones: TV fills without bar magnifier assume
an intrabar order, its GC1! data rolls differently from the volume-rolled continuous used here, and
slippage/commission must be set in the strategy properties (used here: 1 tick each side + $2.50/side).

## Trade list for the chosen config
`results/trades_1min_cons_MonThu_ORB15.csv` — all 117 trades (1m, conservative stop, Mon–Thu, ORB ≥ 15 pt), NY time,
with ORB levels, stop/target, exit reason, points and $ net of costs (0.25 pt = $25 round trip per GC), R and cumulative $.
