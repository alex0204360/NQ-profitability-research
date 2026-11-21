import hashlib
import pandas as pd
import pytest

from prospective import load_panel


def test_prospective_contract_date_checksum(tmp_path):
    spec = {"sessions": {"2026-11-23": "MNQZ26", "2026-12-14": "MNQH27"}}
    raw = pd.DataFrame({"timestamp_utc": ["2026-11-23T14:30:00Z","2026-12-14T14:30:00Z"],
                        "contract": ["MNQZ26","MNQH27"], "open": 100., "low": 99.,
                        "high": 101., "close": 100.5, "volume": 20})
    path = tmp_path/"bars.csv"
    raw.to_csv(path, index=False)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(load_panel(path, digest, spec)) == 2
    with pytest.raises(ValueError, match="checksum"):
        load_panel(path, "incorrect", spec)
    with pytest.raises(ValueError, match="contract mismatch"):
        load_panel(path, digest, {"sessions": dict.fromkeys(spec["sessions"],"MNQZ26")})
