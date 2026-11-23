"""Create a reproducible portable archive from frozen sources and the rendered chart."""
import argparse
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

HERE = Path(__file__).resolve().parent


def package(chart, output):
    files = {name: (HERE.parent/name).read_bytes() for name in
             ["area.json","reservoir.json","brain.py","execution.py","data.py","prospective.json"]}
    for name in ["paper_day.py","quote_audit.py","session.py","viewer.html","session-protocol.md",
                 "historical-results.json","test_session.py","test_quote_audit.py"]:
        files["workbench/"+name] = (HERE/name).read_bytes()
    files["README.md"] = (HERE/"HANDOFF.md").read_bytes()
    files["requirements.txt"] = b"numpy==2.3.5\npandas==2.2.3\n"
    files["MNQ-trade-chart.html"] = chart.read_bytes()
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name,content in sorted(files.items())).encode()
    with ZipFile(output, "w") as z:
        for name,content in sorted(files.items()):
            info = ZipInfo("MNQ-reservoir/"+name, (2026,11,23,0,0,0))
            info.compress_type = ZIP_DEFLATED
            z.writestr(info,content)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("chart", type=Path)
    p.add_argument("output", type=Path)
    args = p.parse_args()
    package(args.chart,args.output)
