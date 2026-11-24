import numpy as np
import pandas as pd

from evidence import evidence


def test_largest_surviving_release_matches_literal_deletion_at_each_close():
    dec=7/8
    releases=[3.,-2.,1.,0.,-6.,0.,4.,3.,1.]
    ages=[1,2,3,4,5,1,2,3,4]
    scale=[1,2,3,2,1,4,2,1,3]
    history=[]
    forecasts=[]
    expected=[]
    for release,age,unit in zip(releases,ages,scale,strict=True):
        if age==1:
            history=[]
        history=[dec*x for x in [*history,release]]
        raw=unit*sum(history)
        forecasts.append(raw)
        direction=np.sign(raw)
        worst=min(direction*(raw-unit*x) for x in [0.,*history])
        expected.append(direction*max(0.,worst))
    a=pd.DataFrame(dict(signed_release=releases,age=ages,scale=scale,reservoir=forecasts))
    np.testing.assert_allclose(evidence(a).corroborated,expected)
    a.loc[0,"reservoir"]=np.nan
    assert np.isnan(evidence(a).corroborated.iloc[0])
