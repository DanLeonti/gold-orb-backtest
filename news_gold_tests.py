import pandas as pd, numpy as np
from news_gold import d, shock_table, FOMC
COST=0.25; DEV_END=pd.Timestamp("2025-01-01")
def st(R, label):
    R=pd.Series(R).dropna()
    if len(R)<5: return f"{label:52s} n={len(R):3d}"
    return f"{label:52s} n={len(R):3d} avgR={R.mean():+.3f} t={R.mean()/R.std()*np.sqrt(len(R)):+.2f} win={(R>0).mean()*100:3.0f}%"
def both(df, label):
    dt=pd.to_datetime(df.date); return st(df.R[dt<DEV_END],"  dev "+label)+"\n"+st(df.R[dt>=DEV_END],"  ho  "+label)

# per-day bar matrix: close/open/high/low by hm
day = {k: g for k,g in d.groupby("date")}
def bars(date): return day[date]

def impulse_trades(dates, hm0, w, exits, brackets, cost=COST):
    rows=[]
    for dt in dates:
        g=bars(dt); hm=g.hm.values
        i0=np.searchsorted(hm,hm0)
        if i0>=len(hm) or hm[i0]!=hm0: continue
        ie=i0+w
        if ie>=len(hm): continue
        o0=g.open.values[i0]; c_imp=g.close.values[ie-1]
        dir_=np.sign(c_imp-o0); size=abs(c_imp-o0)
        if dir_==0 or size<=0: continue
        ent=g.open.values[ie]
        for ex in exits:   # time exit at open of bar hm==ex
            j=np.searchsorted(hm,ex)
            if j>=len(hm) or j<=ie: continue
            px=g.open.values[j]; gross=(px-ent)*dir_
            rows.append(dict(date=dt,kind=f"time{ex}",w=w,R=(gross-cost)/size,dir=dir_,imp=size))
        for k,tend in brackets:  # stop at pre-news open, target k*size, time stop
            sl=o0; tp=ent+dir_*k*size; risk=(ent-sl)*dir_
            if risk<=0: continue
            j_end=np.searchsorted(hm,tend); j_end=min(j_end,len(hm)-1)
            H=g.high.values[ie:j_end]; L=g.low.values[ie:j_end]; O=g.open.values[ie:j_end]
            if dir_==1: hs=L<=sl; ht=H>=tp
            else: hs=H>=sl; ht=L<=tp
            ks=np.argmax(hs) if hs.any() else 10**9; kt=np.argmax(ht) if ht.any() else 10**9
            if ks==10**9 and kt==10**9: px=g.open.values[j_end]
            elif ks<=kt: px=sl if ((O[ks]>sl) if dir_==1 else (O[ks]<sl)) else O[ks]
            else: px=tp
            gross=(px-ent)*dir_
            rows.append(dict(date=dt,kind=f"brk{k}R",w=w,R=(gross-cost)/risk,dir=dir_,imp=size))
    return pd.DataFrame(rows)

import sys
if "skip1" in sys.argv: pass
print("################ TEST 1: original ORB strategy by 08:30 news regime (1m, conservative SL)")
s830=shock_table(830)
for dl in ["Mon-Thu","Mon-Fri"]:
    t=pd.read_csv(f"out/gold_orb_1min_cons_{dl}.csv"); t["date"]=pd.to_datetime(t.ts).dt.date
    t["ratio"]=t.date.map(s830.ratio)
    print(f"-- {dl}")
    for lo,hi,lab in [(0,2,"quiet <2x"),(2,4,"mild 2-4x"),(4,99,"shock >=4x"),(6,99,"shock >=6x")]:
        g=t[(t.ratio>=lo)&(t.ratio<hi)]
        print(st(g.R,f"  all {lab}")); print(both(g,lab))

print("\n################ TEST 2: 08:30 impulse continuation (+) / fade (-); R unit = impulse size (time exits) or stop at pre-news open (brackets)")
for th in [3,4,6]:
    dates=s830[s830.ratio>=th].index
    for w in [1,2,5]:
        tr=impulse_trades(dates,830,w,exits=[900,1000,1200,1359],brackets=[(1,1359),(2,1359)])
        print(f"-- ratio>={th}, impulse window {w}m, n days={len(dates)}, median impulse={tr[tr.kind=='time900'].imp.median():.1f}pt")
        for kind,g in tr.groupby("kind"): print(st(g.R,f"  all {kind}")); print(both(g,kind))

print("\n################ TEST 3a: 10:00 impulse (ratio>=3)")
s10=shock_table(1000); dates=s10[s10.ratio>=3].index
for w in [1,2,5]:
    tr=impulse_trades(dates,1000,w,exits=[1030,1200,1359],brackets=[(1,1359),(2,1359)])
    print(f"-- w={w}m n days={len(dates)}")
    for kind,g in tr.groupby("kind"): print(st(g.R,f"  all {kind}")); print(both(g,kind))

print("\n################ TEST 3b: 14:00 FOMC statement impulse (calendar days) and 14:30 presser")
fd=[x for x in FOMC if x in day]
for hm0,ws,exits in [(1400,[1,2,5,15],[1430,1500,1630]),(1430,[5,15],[1500,1530,1630])]:
    for w in ws:
        tr=impulse_trades(fd,hm0,w,exits=exits,brackets=[(1,1630),(2,1630)])
        print(f"-- {hm0} w={w}m n={len(fd)}")
        for kind,g in tr.groupby("kind"): print(st(g.R,f"  all {kind}"))
