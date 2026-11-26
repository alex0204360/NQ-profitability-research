"""Bundle standalone minute inference, exact weights, outcomes and the offline inspector."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

HERE=Path(__file__).resolve().parent

def build():
    with ZipFile(HERE/"volume-auction-kit.zip","w",ZIP_DEFLATED) as z:
        for n in ["README.md","network.py","cascade.py","impulse.py","timing.py","latest.py","test_network.py","weights.json",
                  "cascade_weights.json","impulse_weights.json","auction-replay.html","protocol.md","cascade_protocol.md",
                  "impulse_protocol.md","november25-protocol.md"]:
            z.write(HERE/n,n)
        for p in sorted((HERE/"results").rglob("*.json")): z.write(p,p.relative_to(HERE))
        for p in sorted((HERE/"results"/"postfreeze").glob("*.csv*")):z.write(p,p.relative_to(HERE))


if __name__=="__main__": build()
