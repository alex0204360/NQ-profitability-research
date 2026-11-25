"""Export only the runtime dependencies, frozen heads, scorecards and offline charts."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CORE=ROOT/"experiments/path_order"
LAB=HERE.parent


def build():
    files={HERE/n for n in ("forward.py","capacitor.py","load_weights.json","overlap.py","overlap_protocol.md",
           "risk_head.py","risk_weights.json","risk_protocol.md","forward_protocol.md","protocol.md",
           "learning_protocol.md","bridge_weights.json","bridge.py","replay_lab.py","risk_study.py","test_physics.py",
           "feedback_study.py")}
    files.update(CORE/n for n in ("brain.py","data.py","execution.py","prospective.json","area.json","reservoir.json",
                                "evaluate.py","workbench/session.py","workbench/history.py","november/capture-receipt.json",
                                "november-extension/capture-1.json","november-extension/capture-2.json"))
    files.update(LAB/n for n in ("minute_observatory/observer.py","minute_observatory/risk.py","minute_observatory/evaluate_entry.py",
           "minute_observatory/evidence.py","minute_observatory/weights.json","tick_exit/experiment.py","tick_exit/neuron.py",
           "tick_exit/weights.json","return_to_anchor/model.py","return_to_anchor/weights.json","adverse_impact/simulator.py",
           "trade_memory/capture_receipt.json"))
    with ZipFile(HERE/"capacitor-review.zip","w",ZIP_DEFLATED) as z:
        for path in sorted(files):
            z.write(path,path.relative_to(ROOT))
        for path in sorted((HERE/"results").glob("*/*.json")):
            z.write(path,path.relative_to(HERE))
        z.write(HERE/"README.md","README.md")
        z.write(HERE/"risk-replay.html","risk-replay.html")
        for path in sorted((LAB/"paper_sessions/2026-11-24").iterdir()):
            z.write(path,"November-24/"+path.name)
        z.writestr("record.py","from pathlib import Path\nimport runpy, sys\np=Path(__file__).parent/'experiments/reservoir_lab/capacitor_bridge'\nsys.path.insert(0,str(p))\nrunpy.run_path(str(p/'forward.py'),run_name='__main__')\n")


if __name__=="__main__":build()
