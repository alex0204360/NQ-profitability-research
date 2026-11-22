import numpy as np
import pandas as pd

import neuron
import erasure


def check_encoder(encoder):
    rng = np.random.default_rng(493)
    close = 100 + rng.normal(0, 60, 330).cumsum()
    bars = pd.DataFrame(dict(close=close, open=np.r_[100,close[:-1]]),
                        index=pd.date_range('2026-09-14 09:30', periods=len(close),
                                            freq='min', tz='America/New_York'))
    state = encoder(bars)
    pd.testing.assert_frame_equal(state.iloc[:153], encoder(bars.iloc[:153]))
    reflected = encoder(500-bars)
    np.testing.assert_array_equal(state.iloc[:,-3:], -reflected.iloc[:,-3:])
    assert (state.iloc[:,-3:] != 0).any().all()


def test_future_mutations_and_reflection():
    for encoder in [neuron.encode, erasure.encode]:
        check_encoder(encoder)


if __name__ == '__main__':
    test_future_mutations_and_reflection()
