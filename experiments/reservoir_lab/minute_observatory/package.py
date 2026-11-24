"""Bundle the observer, frozen dependencies and reviewed sessions for local use."""
import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CORE=ROOT/"experiments/path_order"


def build(replay,snapshot,target):
    manifest=json.loads((CORE/"prospective.json").read_text())
    core=[CORE/name for name in manifest["frozen_files"]]
    core+=[CORE/"prospective.json",CORE/"workbench"/"session.py"]
    with ZipFile(target,"w",ZIP_DEFLATED) as archive:
        for p in [*core,HERE/"observer.py",HERE/"dashboard.html"]:
            archive.write(p,str(p.relative_to(ROOT)))
        archive.write(HERE/"README.md","README.md")
        for name in ["protocol.md","evidence.py","weights.json","results/results.json","results/risk-bounds.json","results/host-latency.json"]:
            archive.write(HERE/name,name)
        archive.write(replay,"November-23-replay.html")
        archive.write(snapshot,"November-24-snapshot.html")
        archive.writestr("monitor.py","from pathlib import Path\nimport runpy\nrunpy.run_path(str(Path(__file__).parent/'experiments/reservoir_lab/minute_observatory/observer.py'), run_name='__main__')\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ["replay","snapshot","target"]: parser.add_argument(k,type=Path)
    a=parser.parse_args()
    build(a.replay,a.snapshot,a.target)
