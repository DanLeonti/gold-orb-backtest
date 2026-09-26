"""Second-stage lab for the ORB>=15 gold config: structural variants only."""
import pandas as pd, numpy as np, itertools, time, sys
from orb_lab import prep, build_days, SPEC, summ
COST=0.25
def run2(D, days, cfg):
    a=D["arrs"]; rows=[]
    entry,bias_m,sl_m,tp_m,cutoff,filt,dowset,hold,be = (cfg[k] for k in ["entry","bias","sl","tp","cutoff","filt","days","hold","be"])
    for dd in days:
        if dd is None or dd["dow"] not in dowset: continue
        s,e,ti=dd["s"],dd["e"],dd["ti"]
        O,H,L,C,V,HM=a["open"][s:e],a["high"][s:e],a["low"][s:e],a["close"][s:e],a["vwap"][s:e],a["hm"][s:e]
        oh,ol=dd["oh"],dd["ol"]; mid=(oh+ol)/2; rng=oh-ol
        if rng<=0: continue
        i0=ti[0]; c0=C[i0]
        if filt=="pts15" and rng<15: continue
        if filt=="pct033" and rng/c0*100<0.33: continue
        if filt=="rel15" and not (dd["rel"]>=1.5): continue
        if bias_m=="mid_vwap": b=1 if (c0>mid and c0>V[i0]) else (-1 if (c0<mid and c0<V[i0]) else 0)
        elif bias_m=="mid": b=1 if c0>mid else (-1 if c0<mid else 0)
        elif bias_m=="vwap": b=1 if c0>V[i0] else (-1 if c0<V[i0] else 0)
        if b==0: continue
        cand=ti[HM[ti]<=cutoff] if cutoff else ti
        if entry=="retrace":
            if b==1: m=(L[cand]<=mid+0.1)&(C[cand]>mid)&((oh-C[cand])>=1.0)
            else: m=(H[cand]>=mid-0.1)&(C[cand]<mid)&((C[cand]-ol)>=1.0)
            w=np.where(m)[0]
            if len(w)==0: continue
            fi=cand[w[0]]+1
            if fi>=e-s: continue
            ent=O[fi]
        else:
            cand2=cand[cand>i0]; m=(L[cand2]<=mid) if b==1 else (H[cand2]>=mid); w=np.where(m)[0]
            if len(w)==0: continue
            fi=cand2[w[0]]; ent=min(mid,O[fi]) if b==1 else max(mid,O[fi])
        side=b
        d_edge_tp=(oh-ent) if side==1 else (ent-ol); d_edge_sl=(ent-ol) if side==1 else (oh-ent)
        if d_edge_tp<=0 or d_edge_sl<=0: continue
        if sl_m=="edge": rsk=d_edge_sl
        elif sl_m=="cap1R": rsk=min(d_edge_sl,d_edge_tp)
        elif sl_m=="half": rsk=rng/2
        if tp_m=="edge": rew=d_edge_tp
        elif tp_m=="half": rew=rng/2
        elif tp_m=="R1.5": rew=1.5*rsk
        sl=ent-side*rsk; tp=ent+side*rew
        after=np.where(HM>hold)[0]; last=int(after[0]) if len(after) else e-s-1
        j=np.arange(fi,last)
        if entry=="limit": j=j  # limit fill: no same-bar TP
        if len(j)==0: px=O[last]; why="time"
        else:
            Hj,Lj,Oj=H[j],L[j],O[j]
            hs=(Lj<=sl) if side==1 else (Hj>=sl); ht=(Hj>=tp) if side==1 else (Lj<=tp)
            if entry=="limit": ht[0]=False
            ks=np.argmax(hs) if hs.any() else 10**9; kt=np.argmax(ht) if ht.any() else 10**9
            if be>0:
                hb=(Hj>=ent+be*rsk) if side==1 else (Lj<=ent-be*rsk); kb=np.argmax(hb) if hb.any() else 10**9
                if kb<ks and kb<kt:   # BE armed before either level hit: from kb+1 on, stop=entry
                    hs2=(Lj<=ent) if side==1 else (Hj>=ent); hs2[:kb+1]=False
                    ks2=np.argmax(hs2) if hs2.any() else 10**9
                    if kt<=ks2 and kt<10**9: px=tp; why="tp"
                    elif ks2<10**9: px=ent; why="be"
                    else: px=O[last]; why="time"
                    gross=(px-ent)*side; rows.append(dict(date=dd["date"],side=side,why=why,net=gross-COST,risk=rsk,R=(gross-COST)/rsk)); continue
            if ks==10**9 and kt==10**9: px=O[last]; why="time"
            elif ks<=kt: px=sl if ((Oj[ks]>sl) if side==1 else (Oj[ks]<sl)) else Oj[ks]; why="sl"
            else: px=tp; why="tp"
        gross=(px-ent)*side
        rows.append(dict(date=dd["date"],side=side,why=why,net=gross-COST,risk=rsk,R=(gross-COST)/rsk))
    return pd.DataFrame(rows)

def evaluate(t):
    if len(t)==0: return dict(n=0)
    dt=pd.to_datetime(t.date); R=t.R
    def s(x): return dict(n=len(x), avgR=x.mean() if len(x) else np.nan, t=(x.mean()/x.std()*np.sqrt(len(x))) if len(x)>2 else np.nan)
    eq=t.net.cumsum(); dd=(eq-eq.cummax()).min()*100
    out=dict(n=len(t),avgR=R.mean(),t=R.mean()/R.std()*np.sqrt(len(t)),pf=t.net[t.net>0].sum()/max(1e-9,-t.net[t.net<=0].sum()),net_usd=t.net.sum()*100,maxdd_usd=dd,win=(t.net>0).mean())
    for lab,mask in [("y2224",dt<"2025-01-01"),("y25",(dt>="2025-01-01")&(dt<"2026-01-01")),("y26",dt>="2026-01-01"),("cur",dt>="2025-01-01")]:
        x=s(R[mask]); out[f"{lab}_n"]=x["n"]; out[f"{lab}_avgR"]=x["avgR"]; out[f"{lab}_t"]=x["t"]
    return out

if __name__=="__main__":
    rows=[]; t0=time.time()
    for tf in ["1min","5min"]:
        D=prep("GC",tf); days=build_days(D,(820,849),1359)
        for entry,bias,sl,tp,cutoff,filt,dl,hold,be in itertools.product(["retrace","limit"],["mid_vwap","mid","vwap"],["edge","cap1R","half"],["edge","half","R1.5"],[0,1100],["pts15","pct033","rel15"],["MonThu","MonFri"],[1359,1659],[0,0.5]):
            cfg=dict(entry=entry,bias=bias,sl=sl,tp=tp,cutoff=cutoff,filt=filt,days=(0,1,2,3) if dl=="MonThu" else (0,1,2,3,4),hold=hold,be=be)
            t=run2(D,days,cfg); r=dict(tf=tf,entry=entry,bias=bias,sl=sl,tp=tp,cutoff=cutoff,filt=filt,dl=dl,hold=hold,be=be); r.update(evaluate(t)); rows.append(r)
        print(tf,"done",len(rows),f"{time.time()-t0:.0f}s",flush=True)
    pd.DataFrame(rows).to_csv("out/orb_lab2_GC.csv",index=False)
