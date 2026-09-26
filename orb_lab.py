"""Vectorized per-day ORB lab: generalizes the Gold ORB 50% strategy over entry/bias/stop/target/
window/filter choices, for GC/NQ/ES. Dev = 2022-07..2024-12, holdout = 2025-01..2026-09."""
import pandas as pd, numpy as np, itertools, time, sys, json

SPEC = {  # $/pt, round-trip cost in pts (commission + slippage), min TP distance
    "GC": dict(point=100.0, cost=0.25, min_tp=1.0, file="out/GC_1m_4yr.parquet"),
    "NQ": dict(point=20.0,  cost=1.00, min_tp=5.0, file="out/NQ_1m_4yr.parquet"),
    "ES": dict(point=50.0,  cost=0.60, min_tp=1.0, file="out/ES_1m_4yr.parquet"),
}
DEV_END = pd.Timestamp("2025-01-01")

def prep(sym, tf="1min"):
    d = pd.read_parquet(SPEC[sym]["file"]).set_index("ts").sort_index()
    d = d[~d.index.duplicated()]
    if tf != "1min":
        d = d.resample(tf, label="left", closed="left").agg(open=("open","first"), high=("high","max"),
              low=("low","min"), close=("close","last"), volume=("volume","sum")).dropna(subset=["open"])
    d = d.reset_index()
    t = d.ts
    d["hm"] = (t.dt.hour*100 + t.dt.minute).astype(np.int32)
    d["date"] = t.dt.date
    d["dow"] = t.dt.dayofweek.astype(np.int8)
    sess = (t - pd.Timedelta(hours=18)).dt.date
    tp = (d.high + d.low + d.close)/3
    d["vwap"] = (tp*d.volume).groupby(sess).cumsum() / d.volume.groupby(sess).cumsum().replace(0, np.nan)
    d["sess_open"] = d.groupby(sess).open.transform("first")
    # day index table
    days = []
    for date, g in d.groupby("date", sort=True):
        days.append((date, g.index[0], g.index[-1]+1))
    arrs = {k: d[k].values for k in ["open","high","low","close","hm","vwap","sess_open"]}
    arrs["dow"] = d.dow.values
    return dict(sym=sym, tf=tf, arrs=arrs, days=days)

def build_days(D, orb, trade_end):
    """Per-day slices for a given ORB window; also trailing-20 median ORB range (excl. today)."""
    a = D["arrs"]; hm = a["hm"]; out = []; ranges = []
    for date, s, e in D["days"]:
        h = hm[s:e]
        om = (h >= orb[0]) & (h <= orb[1])
        if not om.any(): 
            out.append(None); ranges.append(np.nan); continue
        tm = (h > orb[1]) & (h <= trade_end)
        ti = np.where(tm)[0]
        if len(ti) < 2:
            out.append(None); ranges.append(np.nan); continue
        after = np.where(h > trade_end)[0]
        ts_i = int(after[0]) if len(after) else None   # time-stop bar (open)
        oh = a["high"][s:e][om].max(); ol = a["low"][s:e][om].min()
        out.append(dict(date=date, s=s, e=e, ti=ti, ts_i=ts_i, oh=oh, ol=ol, dow=a["dow"][s]))
        ranges.append(oh-ol)
    r = pd.Series(ranges)
    rel = r / r.rolling(20, min_periods=10).median().shift(1)
    for i, d_ in enumerate(out):
        if d_ is not None: d_["rel"] = rel.iloc[i]
    return out

def run(D, days, cfg):
    a = D["arrs"]; sp = SPEC[D["sym"]]; cost = sp["cost"]; min_tp = sp["min_tp"]
    entry, bias_m, sl_m, tp_m = cfg["entry"], cfg["bias"], cfg["sl"], cfg["tp"]
    cutoff, relmin, dowset = cfg["cutoff"], cfg["relmin"], cfg["days"]
    tbuf = 0.1 if D["sym"]=="GC" else 0.25
    res = []
    for dd in days:
        if dd is None or dd["dow"] not in dowset: continue
        if relmin and not (dd["rel"] >= relmin): continue
        s, e, ti = dd["s"], dd["e"], dd["ti"]
        O,H,L,C = a["open"][s:e], a["high"][s:e], a["low"][s:e], a["close"][s:e]
        V, SO, HM = a["vwap"][s:e], a["sess_open"][s:e], a["hm"][s:e]
        oh, ol = dd["oh"], dd["ol"]; mid = (oh+ol)/2; rng = oh-ol
        if rng <= 0: continue
        i0 = ti[0]; c0 = C[i0]
        # ---- bias at window open
        if bias_m == "mid_vwap": b = 1 if (c0>mid and c0>V[i0]) else (-1 if (c0<mid and c0<V[i0]) else 0)
        elif bias_m == "mid":    b = 1 if c0>mid else (-1 if c0<mid else 0)
        elif bias_m == "vwap":   b = 1 if c0>V[i0] else (-1 if c0<V[i0] else 0)
        elif bias_m == "on":     b = 1 if (c0>mid and c0>SO[i0]) else (-1 if (c0<mid and c0<SO[i0]) else 0)
        elif bias_m == "none":   b = 0
        if bias_m != "none" and b == 0: continue
        # ---- entry signal: index of signal bar (fill next bar open) or fill index for limit
        cand = ti[HM[ti] <= cutoff] if cutoff else ti
        if len(cand) == 0: continue
        side = b; fi = None; ent = None; sig_i = None
        if entry == "retrace":
            if b == 0: side = 1 if c0 > mid else (-1 if c0 < mid else 0)
            if side == 0: continue
            if side == 1: m = (L[cand] <= mid+tbuf) & (C[cand] > mid) & ((oh - C[cand]) >= min_tp)
            else:         m = (H[cand] >= mid-tbuf) & (C[cand] < mid) & ((C[cand] - ol) >= min_tp)
            w = np.where(m)[0]
            if len(w)==0: continue
            sig_i = cand[w[0]]; fi = sig_i+1
            if fi >= e-s: continue
            ent = O[fi]
        elif entry == "limit":
            if b == 0: side = 1 if c0 > mid else (-1 if c0 < mid else 0)
            if side == 0: continue
            cand2 = cand[cand > i0]
            if side == 1: m = L[cand2] <= mid
            else:         m = H[cand2] >= mid
            w = np.where(m)[0]
            if len(w)==0: continue
            fi = cand2[w[0]]; sig_i = fi
            ent = min(mid, O[fi]) if side==1 else max(mid, O[fi])
        elif entry == "breakout":
            up = C[cand] > oh; dn = C[cand] < ol
            if b == 1: dn[:] = False
            if b == -1: up[:] = False
            wu = np.where(up)[0]; wd = np.where(dn)[0]
            if len(wu)==0 and len(wd)==0: continue
            iu = wu[0] if len(wu) else 10**9; idn = wd[0] if len(wd) else 10**9
            side = 1 if iu < idn else -1
            sig_i = cand[min(iu, idn)]; fi = sig_i+1
            if fi >= e-s: continue
            ent = O[fi]
        # ---- stop / target
        if sl_m == "edge":   sl = ol if side==1 else oh
        elif sl_m == "mid":  sl = mid
        elif sl_m.startswith("frac"): f=float(sl_m[4:]); sl = ent - side*f*rng
        risk = (ent - sl)*side
        if risk <= 0: continue
        if tp_m == "edge":   tp = oh if side==1 else ol
        elif tp_m.startswith("R"): tp = ent + side*float(tp_m[1:])*risk
        elif tp_m.startswith("range"): tp = ent + side*float(tp_m[5:])*rng
        if (tp-ent)*side <= 0: continue
        # ---- exit sim from fill bar
        last = dd["ts_i"] if dd["ts_i"] is not None else (e-s-1)
        j = np.arange(fi, last)   # bars where bracket is live (time-stop bar excluded)
        if len(j)==0:
            ex, why, xi = O[last], "time", last
        else:
            if side==1: hs = L[j] <= sl; ht = H[j] >= tp
            else:       hs = H[j] >= sl; ht = L[j] <= tp
            if entry == "limit": ht[0] = False   # no same-bar target on a limit fill (intrabar order unknown)
            ks = np.argmax(hs) if hs.any() else 10**9; kt = np.argmax(ht) if ht.any() else 10**9
            if ks == 10**9 and kt == 10**9:
                ex, why, xi = O[last], "time", last
            elif ks <= kt:
                xi = j[ks]; why="sl"
                ex = sl if ((O[xi] > sl) if side==1 else (O[xi] < sl)) else O[xi]
            else:
                xi = j[kt]; why="tp"
                ex = tp if ((O[xi] < tp) if side==1 else (O[xi] > tp)) else O[xi]
        gross = (ex-ent)*side
        res.append((dd["date"], side, ent, sl, tp, ex, why, gross, gross-cost, risk, (gross-cost)/risk, rng, dd["rel"]))
    return pd.DataFrame(res, columns=["date","side","entry","sl","tp","exit","why","gross","net","risk","R","rng","rel"])

def summ(t):
    if len(t)==0: return dict(n=0)
    n=len(t); R=t.R
    return dict(n=n, avgR=R.mean(), t=(R.mean()/R.std()*np.sqrt(n)) if n>1 else np.nan, win=(t.net>0).mean(),
                pf=t.net[t.net>0].sum()/max(1e-9,-t.net[t.net<=0].sum()), net_pts=t.net.sum())

def split(t):
    if len(t)==0: return t, t
    dt = pd.to_datetime(t.date)
    return t[dt < DEV_END], t[dt >= DEV_END]

if __name__ == "__main__":
    sym = sys.argv[1]; tf = sys.argv[2] if len(sys.argv)>2 else "1min"
    D = prep(sym, tf)
    windows = {"GC": [(820,849,1359),(830,859,1359),(930,959,1559)],
               "NQ": [(820,849,1359),(930,959,1559),(930,944,1559)],
               "ES": [(820,849,1359),(930,959,1559),(930,944,1559)]}[sym]
    rows = []; t0=time.time()
    for orb0, orb1, tend in windows:
        days = build_days(D, (orb0,orb1), tend)
        for entry in ["retrace","limit","breakout"]:
            sls = ["edge","frac0.5","frac1.0"] if entry!="breakout" else ["mid","edge","frac0.5"]
            tps = ["edge","R2","R3"] if entry!="breakout" else ["range1","R2","R3"]
            for bias, sl, tp, cutoff, relmin, dl in itertools.product(
                    ["mid_vwap","mid","vwap","on","none"], sls, tps,
                    [0, (orb1//100)*100 + (orb1%100) + 100 - 49], [0, 1.0], ["MonThu","MonFri"]):
                if entry=="breakout" and sl=="edge": continue   # opposite edge = 1 full range, covered by frac
                cfg = dict(orb=f"{orb0}-{orb1}", tend=tend, entry=entry, bias=bias, sl=sl, tp=tp, cutoff=cutoff,
                           relmin=relmin, days=(0,1,2,3) if dl=="MonThu" else (0,1,2,3,4), dl=dl)
                t = run(D, days, cfg); dv, ho = split(t)
                r = {k:v for k,v in cfg.items() if k!="days"}
                r.update({f"dev_{k}":v for k,v in summ(dv).items()}); r.update({f"ho_{k}":v for k,v in summ(ho).items()})
                rows.append(r)
        print(f"{sym} {tf} window {orb0}-{orb1} done, {len(rows)} cfgs, {time.time()-t0:.0f}s", flush=True)
    pd.DataFrame(rows).to_csv(f"out/orb_lab_{sym}_{tf}.csv", index=False)
    print("saved", flush=True)
