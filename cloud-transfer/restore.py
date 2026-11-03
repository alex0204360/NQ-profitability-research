#!/usr/bin/env python3
"""Reassemble and verify the private MNQ research transfer in /workspace."""
import hashlib
import json
import zipfile
from pathlib import Path

here = Path(__file__).resolve().parent
workspace = Path("/workspace")
if (here / 'latest_snapshot_index.json').exists():
    from restore_latest import restore
    restore()
    raise SystemExit(0)
index = json.loads((here / "transfer_index.json").read_text(encoding="utf-8"))
assert index["version"] == 1 and not index["sealed_2025_raw_included"]
targets = {"mnq-oracle-code.zip": workspace,
           "mnq-2026-training.zip": workspace,
           "mnq-outputs-core.zip": workspace}
for record in index["files"]:
    name = record["name"]
    target = targets.get(name, workspace / "mnq-private-results")
    target.mkdir(parents=True, exist_ok=True)
    archive = here / "reassembled" / name
    archive.parent.mkdir(exist_ok=True)
    with archive.open("wb") as stream:
        for part in record["parts"]:
            path = here.parent / part["path"]
            data = path.read_bytes()
            assert hashlib.sha1(b"blob " + str(len(data)).encode() + bytes([0]) + data).hexdigest() == part["sha"], path
            stream.write(data)
    assert archive.stat().st_size == record["bytes"], name
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == record["sha256"], name
    with zipfile.ZipFile(archive) as z:
        for member in z.infolist():
            resolved = (target / member.filename).resolve()
            if not resolved.is_relative_to(target.resolve()):
                raise ValueError("Unsafe ZIP member: " + member.filename)
            if "Dataset_NQ_1min_2022_2025.csv" in member.filename:
                raise ValueError("Sealed raw dataset forbidden")
        z.extractall(target)
    print(f"Verified and extracted {name} to {target}")
print("MNQ transfer complete. Read /workspace/outputs/MNQ_CLOUD_TRANSFER_README.md")
