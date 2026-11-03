#!/usr/bin/env python3
"""Restore and verify the latest complete MNQ research snapshot in /workspace."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
WORKSPACE = Path('/workspace')
ALLOWED_ROOTS = {'mnq-oracle-code', 'mnq-private-data', 'mnq-private-results', 'outputs'}
FORBIDDEN_NAMES = {'Dataset_NQ_1min_2022_2025.csv'}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def restore() -> dict:
    index = json.loads((HERE / 'latest_snapshot_index.json').read_text())
    if index['version'] != 1 or index['sealed_2025_raw_included'] is not False:
        raise ValueError('Unsupported or unsafe snapshot index')
    spec = index['archive']
    assembled = HERE / 'reassembled' / spec['name']
    assembled.parent.mkdir(exist_ok=True)
    with assembled.open('wb') as output:
        for part in spec['parts']:
            path = HERE.parent / part['path']
            data = path.read_bytes()
            blob = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if len(data) != part['bytes'] or blob != part['git_blob_sha1']:
                raise ValueError(f'Corrupt Git part: {path}')
            output.write(data)
    if assembled.stat().st_size != spec['bytes'] or sha256(assembled.read_bytes()) != spec['sha256']:
        raise ValueError('Snapshot archive checksum mismatch')
    with zipfile.ZipFile(assembled) as stream:
        manifest_bytes = stream.read('_snapshot_manifest.json')
        if sha256(manifest_bytes) != index['manifest_sha256']:
            raise ValueError('Snapshot manifest checksum mismatch')
        manifest = json.loads(manifest_bytes)
        if (manifest['version'] != 1 or manifest['sealed_2025_raw_included'] is not False or
                set(manifest['roots']) != ALLOWED_ROOTS or len(manifest['files']) != index['file_count']):
            raise ValueError('Unsafe snapshot manifest')
        names = stream.namelist()
        if len(names) != len(set(names)) or set(names) != set(manifest['files']) | {'_snapshot_manifest.json'}:
            raise ValueError('Unexpected or duplicate archive members')
        # Validate every member before writing any workspace file.
        for name, metadata in manifest['files'].items():
            member = Path(name)
            if (member.is_absolute() or '..' in member.parts or not member.parts or
                    member.parts[0] not in ALLOWED_ROOTS or member.name in FORBIDDEN_NAMES or
                    '2025' in member.name.lower()):
                raise ValueError(f'Unsafe snapshot member: {name}')
            info = stream.getinfo(name)
            if info.is_dir() or (info.external_attr >> 16) & 0o170000 not in (0, 0o100000):
                raise ValueError(f'Unexpected file type: {name}')
            data = stream.read(name)
            if len(data) != metadata['bytes'] or sha256(data) != metadata['sha256']:
                raise ValueError(f'Corrupt snapshot member: {name}')
        for name in manifest['files']:
            destination = WORKSPACE / name
            if not destination.resolve().is_relative_to(WORKSPACE.resolve()):
                raise ValueError(f'Unsafe workspace destination: {name}')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(stream.read(name))
    print(f"Verified and restored {index['file_count']} MNQ files to {WORKSPACE}")
    return index


if __name__ == '__main__':
    restore()
