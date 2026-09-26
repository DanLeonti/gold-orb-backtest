import pandas as pd, numpy as np
pd.set_option("display.width",250); pd.set_option("display.max_columns",30)
allr=[]
for sym in ["GC","NQ","ES"]:
    for tf in ["1min","5min"]:
        r=pd.read_csv(f"out/orb_lab_{sym}_{tf}.csv"); r["sym"]=sym; r["tf"]=tf; allr.append(r)
        ok=r[(r.dev_n>=80)]
        gate=ok[(ok.dev_t>2)&(ok.dev_avgR>0)]
        surv=gate[(gate.ho_t>1)&(gate.ho_avgR>0)]
        base=(ok.ho_t>1).mean()
        print(f"{sym} {tf}: n>=80:{len(ok)} dev-gate:{len(gate)} survive:{len(surv)} [chance≈{len(gate)*base:.1f}] median ho_t of gated={gate.ho_t.median() if len(gate) else float('nan'):.2f}  spearman dev/ho={ok[['dev_avgR','ho_avgR']].corr('spearman').iloc[0,1]:+.2f}")
R=pd.concat(allr); R.to_csv("out/orb_lab_all.csv",index=False)
ok=R[(R.dev_n>=80)&(R.ho_n>=40)]
gate=ok[(ok.dev_t>2)&(ok.dev_avgR>0)]
surv=gate[(gate.ho_t>1)&(gate.ho_avgR>0)].copy()
surv["score"]=np.minimum(surv.dev_t,surv.ho_t)
cols=["sym","tf","orb","entry","bias","sl","tp","cutoff","relmin","dl","dev_n","dev_avgR","dev_t","ho_n","ho_avgR","ho_t","ho_pf"]
print("\n=== survivors sorted by min(dev_t,ho_t) ===")
print(surv.sort_values("score",ascending=False)[cols].round(3).head(30).to_string(index=False))
print("\n=== gated config structure ===")
for f in ["sym","tf","orb","entry","bias","sl","tp","cutoff","relmin","dl"]:
    print(f, gate[f].value_counts().to_dict())
# cross-TF consistency: for each survivor, the same config on the other TF
key=["sym","orb","entry","bias","sl","tp","cutoff","relmin","dl"]
other=R.set_index(key+["tf"])
print("\n=== survivors: same config on the other timeframe ===")
rows=[]
for _,s in surv.sort_values("score",ascending=False).head(30).iterrows():
    otf="5min" if s.tf=="1min" else "1min"
    try:
        o=other.loc[tuple(s[k] for k in key)+(otf,)]
        rows.append(dict(sym=s.sym,tf=s.tf,orb=s.orb,entry=s.entry,bias=s.bias,sl=s.sl,tp=s.tp,cut=s.cutoff,rel=s.relmin,dl=s.dl,
                         dev_t=s.dev_t,ho_t=s.ho_t,other_tf=otf,o_dev_avgR=o.dev_avgR,o_dev_t=o.dev_t,o_ho_avgR=o.ho_avgR,o_ho_t=o.ho_t))
    except KeyError: pass
print(pd.DataFrame(rows).round(2).to_string(index=False))
