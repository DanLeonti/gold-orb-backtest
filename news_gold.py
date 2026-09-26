import pandas as pd, numpy as np
d = pd.read_parquet("out/GC_1m_4yr.parquet").set_index("ts").sort_index(); d=d[~d.index.duplicated()]
d["hm"]=d.index.hour*100+d.index.minute; d["date"]=d.index.date
d["rng"]=d.high-d.low
FOMC = pd.to_datetime(["2022-07-27","2022-09-21","2022-11-02","2022-12-14","2023-02-01","2023-03-22","2023-05-03","2023-06-14",
 "2023-07-26","2023-09-20","2023-11-01","2023-12-13","2024-01-31","2024-03-20","2024-05-01","2024-06-12","2024-07-31","2024-09-18",
 "2024-11-07","2024-12-18","2025-01-29","2025-03-19","2025-05-07","2025-06-18","2025-07-30","2025-09-17","2025-10-29","2025-12-10",
 "2026-01-28","2026-03-18","2026-04-29","2026-06-17","2026-07-29","2026-09-16"]).date

def shock_table(hm0):
    b = d[d.hm==hm0].copy(); b["date"]=b.index.date; b=b.set_index("date")
    base = b.rng.rolling(20,min_periods=10).median().shift(1)
    vbase = b.volume.rolling(20,min_periods=10).median().shift(1)
    return pd.DataFrame(dict(rng=b.rng, ratio=b.rng/base, vratio=b.volume/vbase, open=b.open, close=b.close))

if __name__=="__main__":
    for hm0 in [830,1000,1400]:
        s=shock_table(hm0).dropna()
        print(f"\n== {hm0} bar: n days={len(s)}  ratio pctls 50/80/90/95/99 = {np.percentile(s.ratio,[50,80,90,95,99]).round(1)}")
        for th in [2,3,4,6]:
            k=s[s.ratio>=th]; idx=pd.to_datetime(k.index)
            print(f"   ratio>={th}: {len(k)} days ({len(k)/len(s)*100:.0f}%)  dow share Mon-Fri={np.bincount(idx.dayofweek,minlength=5)[:5]}  "
                  f"first-Fri={((idx.dayofweek==4)&(idx.day<=7)).sum()}  FOMC-day={sum(x in set(FOMC) for x in k.index)}/{len([f for f in FOMC if f in s.index])}")
        print("   top 8:", s.ratio.sort_values(ascending=False).head(8).round(1).to_dict())
