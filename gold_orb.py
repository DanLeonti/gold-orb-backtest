"""Port of 'Gold ORB 50% - Dual SL Strategy' (Pine v6) to Python.
ORB 08:20-08:49 NY, trade window 08:50-13:59, bias = close vs ORB mid AND session VWAP at
window open, entry = 50% retrace touch that closes back on the bias side, TP = ORB edge,
SL = opposite ORB edge (conservative) or signal-bar wick +/- 0.2 (aggressive), time stop 14:00.
Fills: next-bar open (TV default), stop wins ties, one trade per day."""
import pandas as pd, numpy as np, sys

POINT = 100.0          # $ per 1.0 pt per GC contract
COST_PTS = 0.25        # $2.5 comm/side + 1 tick (0.1 = $10) slippage/side = $25 RT

def load(tf):
    d = pd.read_parquet("out/GC_1m_4yr.parquet").set_index("ts").sort_index()
    if tf != "1min":
        d = d.resample(tf, label="left", closed="left").agg(open=("open","first"), high=("high","max"),
              low=("low","min"), close=("close","last"), volume=("volume","sum")).dropna(subset=["open"])
    d = d.reset_index()
    t = d.ts
    hm = t.dt.hour*100 + t.dt.minute
    d["in_orb"] = (hm >= 820) & (hm <= 849)
    d["in_trade"] = (hm >= 850) & (hm <= 1359)
    d["dow"] = t.dt.dayofweek            # 0=Mon
    # session VWAP anchored at 18:00 NY (CME gold session), like TV's ta.vwap on GC1!
    sess = (t - pd.Timedelta(hours=18)).dt.date
    tp = (d.high + d.low + d.close)/3
    pv = (tp*d.volume).groupby(sess).cumsum(); vv = d.volume.groupby(sess).cumsum()
    d["vwap"] = pv/vv.replace(0, np.nan)
    return d

def run(d, sl_type="cons", days=(0,1,2,3), aggr_buf=0.2, min_tp=1.0, tick_buf=0.1, stop_wins=True):
    o,h,l,c = d.open.values, d.high.values, d.low.values, d.close.values
    in_orb, in_trade, dow, vwap, ts = d.in_orb.values, d.in_trade.values, d.dow.values, d.vwap.values, d.ts.values
    orb_hi=orb_lo=orb_mid=np.nan; bias=0; taken=False
    pos=0; entry=tp=sl=np.nan; ent_i=None; sig_close=np.nan
    trades=[]
    def close_trade(i, px, why):
        nonlocal pos
        gross = (px-entry)*pos
        risk = abs(entry-sl)
        trades.append(dict(ts=ts[ent_i], exit_ts=ts[i], side=pos, entry=entry, tp=tp, sl=sl, exit=px, why=why,
                           gross_pts=gross, net_pts=gross-COST_PTS, risk=risk,
                           R=(gross-COST_PTS)/risk if risk>0 else np.nan, bars=i-ent_i,
                           orb_rng=orb_hi-orb_lo, sig_close=sig_close))
        pos=0
    pend=0  # pending entry to fill at this bar's open: +1/-1
    for i in range(1,len(d)):
        # --- fill pending entry at open
        if pend!=0:
            pos=pend; entry=o[i]; ent_i=i; pend=0
        # --- manage open position on this bar
        if pos!=0:
            trade_end = (not in_trade[i]) and in_trade[i-1]
            if trade_end:
                close_trade(i, o[i], "time")
            else:
                hit_sl = l[i]<=sl if pos==1 else h[i]>=sl
                hit_tp = h[i]>=tp if pos==1 else l[i]<=tp
                if hit_sl and hit_tp:
                    if stop_wins: close_trade(i, sl if (o[i]>sl if pos==1 else o[i]<sl) else o[i], "sl")
                    else: close_trade(i, tp, "tp")
                elif hit_sl:
                    px = sl if (o[i]>sl if pos==1 else o[i]<sl) else o[i]   # gap through stop fills at open
                    close_trade(i, px, "sl")
                elif hit_tp:
                    close_trade(i, tp, "tp")
        # --- ORB state
        new_orb = in_orb[i] and not in_orb[i-1]
        new_trade = in_trade[i] and not in_trade[i-1]
        if new_orb:
            orb_hi, orb_lo = h[i], l[i]; bias=0; taken=False
        elif in_orb[i]:
            orb_hi=max(orb_hi,h[i]); orb_lo=min(orb_lo,l[i])
        if new_trade:
            orb_mid=(orb_hi+orb_lo)/2
            if c[i]>orb_mid and c[i]>vwap[i]: bias=1
            elif c[i]<orb_mid and c[i]<vwap[i]: bias=-1
            else: bias=0
        # --- entry signal (evaluated at bar close, filled next open)
        if in_trade[i] and dow[i] in days and not taken and pos==0 and pend==0:
            if bias==1 and l[i]<=orb_mid+tick_buf and c[i]>orb_mid and (orb_hi-c[i])>=min_tp:
                taken=True; pend=1; tp=orb_hi; sl=(l[i]-aggr_buf) if sl_type=="aggr" else orb_lo; sig_close=c[i]
            elif bias==-1 and h[i]>=orb_mid-tick_buf and c[i]<orb_mid and (c[i]-orb_lo)>=min_tp:
                taken=True; pend=-1; tp=orb_lo; sl=(h[i]+aggr_buf) if sl_type=="aggr" else orb_hi; sig_close=c[i]
    return pd.DataFrame(trades)

def stats(t, label=""):
    if len(t)==0: return f"{label:40s} n=0"
    net = t.net_pts*POINT
    eq = net.cumsum(); dd = (eq-eq.cummax()).min()
    wins = net[net>0].sum(); loss = -net[net<=0].sum()
    pf = wins/loss if loss>0 else np.inf
    tstat = t.R.mean()/t.R.std()*np.sqrt(len(t)) if len(t)>1 else np.nan
    return (f"{label:40s} n={len(t):4d} win={ (net>0).mean()*100:4.1f}% avgR={t.R.mean():+.3f} t={tstat:+.2f} "
            f"avg$={net.mean():+7.1f} tot$={net.sum():+9.0f} PF={pf:.2f} maxDD$={dd:8.0f} "
            f"tp={ (t.why=='tp').mean()*100:3.0f}% sl={(t.why=='sl').mean()*100:3.0f}% time={(t.why=='time').mean()*100:3.0f}%")

if __name__=="__main__":
    out=[]
    for tf in ["1min","5min","15min"]:
        d=load(tf)
        for sl in ["cons","aggr"]:
            for days,dl in [((0,1,2,3),"Mon-Thu"),((0,1,2,3,4),"Mon-Fri")]:
                t=run(d, sl_type=sl, days=days)
                t.to_csv(f"out/gold_orb_{tf}_{sl}_{dl}.csv", index=False)
                out.append(stats(t, f"{tf} {sl} {dl}"))
                if dl=="Mon-Thu":
                    for y,g in t.groupby(pd.to_datetime(t.ts).dt.year):
                        out.append(stats(g, f"   {y}"))
        print("\n".join(out), flush=True); out=[]
