import pandas as pd, numpy as np
from news_gold import d, shock_table, FOMC
from news_gold_tests import st, both, bars, DEV_END
POINT=100.0
def fade_trades(dates, hm0, w, k_stop, tend, cost, tgt="o0"):
    rows=[]
    for dt in dates:
        g=bars(dt); hm=g.hm.values; i0=np.searchsorted(hm,hm0)
        if i0>=len(hm) or hm[i0]!=hm0: continue
        ie=i0+w
        if ie>=len(hm): continue
        o0=g.open.values[i0]; c_imp=g.close.values[ie-1]; dir_=np.sign(c_imp-o0); size=abs(c_imp-o0)
        if dir_==0 or size<=0: continue
        ent=g.open.values[ie]; side=-dir_                      # fade
        tp = o0 if tgt=="o0" else ent+side*float(tgt)*size
        sl = ent - side*k_stop*size                             # k x impulse beyond entry, in impulse direction
        risk=(ent-sl)*side; 
        if risk<=0 or (tp-ent)*side<=0: continue
        j_end=min(np.searchsorted(hm,tend),len(hm)-1)
        H=g.high.values[ie:j_end]; L=g.low.values[ie:j_end]; O=g.open.values[ie:j_end]
        if side==1: hs=L<=sl; ht=H>=tp
        else: hs=H>=sl; ht=L<=tp
        ks=np.argmax(hs) if hs.any() else 10**9; kt=np.argmax(ht) if ht.any() else 10**9
        if ks==10**9 and kt==10**9: px=g.open.values[j_end]; why="time"
        elif ks<=kt: px=sl if ((O[ks]>sl) if side==1 else (O[ks]<sl)) else O[ks]; why="sl"
        else: px=tp; why="tp"
        gross=(px-ent)*side
        rows.append(dict(date=dt,side=side,entry=ent,tp=tp,sl=sl,exit=px,why=why,gross=gross,net=gross-cost,risk=risk,R=(gross-cost)/risk,imp=size))
    return pd.DataFrame(rows)

s830=shock_table(830)
print("################ PRIMARY (pre-registered): fade 08:30 impulse, ratio>=3, w=2m, target=pre-news open, stop=1x impulse, time stop 10:00")
dates=s830[s830.ratio>=3].index
for cost in [0.25,0.75,1.5]:
    t=fade_trades(dates,830,2,1.0,1000,cost)
    print(f"-- cost {cost}pt RT"); print(st(t.R,"  all")); print(both(t,""))
    if cost==0.75:
        print("   by year:")
        for y,g in t.groupby(pd.to_datetime(t.date).dt.year): print(st(g.R,f"     {y}")+f"  net$={g.net.sum()*POINT:+.0f}  reasons tp/sl/time={(g.why=='tp').mean()*100:.0f}/{(g.why=='sl').mean()*100:.0f}/{(g.why=='time').mean()*100:.0f}%")
        print(f"   median impulse {t.imp.median():.1f}pt, median risk {t.risk.median():.1f}pt, total net ${t.net.sum()*POINT:+.0f}, maxDD ${((t.net.cumsum()-t.net.cumsum().cummax()).min())*POINT:.0f}")
        t.to_csv("out/news_fade_primary.csv",index=False)

print("\n################ ROBUSTNESS (cost 0.75): threshold x window x stop x time-stop")
for th in [2,3,4,6]:
    dates=s830[s830.ratio>=th].index
    for w in [1,2,5]:
        for k in [0.5,1.0,2.0]:
            for tend in [1000,1359]:
                t=fade_trades(dates,830,w,k,tend,0.75)
                dv,ho=t[pd.to_datetime(t.date)<DEV_END],t[pd.to_datetime(t.date)>=DEV_END]
                f=lambda x:(f"n={len(x):3d} R={x.R.mean():+.3f} t={x.R.mean()/x.R.std()*np.sqrt(len(x)):+.2f}" if len(x)>5 else "n<6")
                print(f"  th>={th} w={w} stop={k}x end={tend}:  all {f(t)} | dev {f(dv)} | ho {f(ho)}")

print("\n################ target variants (th>=3,w=2,stop 1x,end 10:00, cost .75): target = fraction of impulse instead of full retrace")
dates=s830[s830.ratio>=3].index
for tgt in ["0.5","1.0","1.5"]:
    t=fade_trades(dates,830,2,1.0,1000,0.75,tgt=tgt); print(st(t.R,f"  tgt {tgt}x impulse")); print(both(t,""))

print("\n################ same fade at 10:00 (ratio>=3) and 14:00 FOMC (calendar) — small n, for completeness")
s10=shock_table(1000)
for hm0,dates,lab in [(1000,s10[s10.ratio>=3].index,"10:00 th>=3"),(1400,[x for x in FOMC if x in set(d.date)],"14:00 FOMC")]:
    for w in [1,2,5]:
        t=fade_trades(dates,hm0,w,1.0,hm0+200 if hm0==1000 else 1630,0.75); print(st(t.R,f"  {lab} w={w}"))

print("\n################ NON-shock days control (ratio<2): does the fade 'work' on quiet days too? (if yes, it's not a news effect)")
dates=s830[s830.ratio<2].index
t=fade_trades(dates,830,2,1.0,1000,0.75); print(st(t.R,"  quiet-day fade w=2")); print(both(t,""))
