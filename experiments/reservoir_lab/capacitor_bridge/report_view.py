"""Export a self-contained, prefix-bounded inspection of every recorded risk call."""
import json
from pathlib import Path

import pandas as pd

HERE=Path(__file__).resolve().parent


def export(out):
    days=[]
    for risk,signal in [("clock","feedback"),("replication-clock","replication-feedback")]:
        base=HERE/"results"
        r=pd.read_csv(base/risk/"observations.csv.gz")
        s=pd.read_csv(base/signal/"traces.csv.gz",index_col=0)
        r=r.merge(s[["close","original","loaded","bridge"]],left_on="origin",right_index=True,validate="one_to_one")
        for day,g in r.groupby(r.origin.str[:10]):
            rows=[]
            for x in g.itertuples():
                rows.append([x.origin[11:16],x.matures[11:16],*[round(float(v),3) for v in
                              [x.close,x.original,x.bridge,x.band,x.physical,x.travel]]])
            days.append(dict(day=day,panel=g.panel.iloc[0],rows=rows))
    page=(HERE/"view.html").read_text().replace("__SESSIONS__",json.dumps(sorted(days,key=lambda d:d["day"]),separators=(",",":")))
    out.write_text(page)


if __name__=="__main__": export(HERE/"risk-replay.html")
