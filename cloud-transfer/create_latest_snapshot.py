#!/usr/bin/env python3
"""Create a verified, complete MNQ workspace snapshot for the private Git branch."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
WORKSPACE = Path('/workspace')
ROOTS = ('mnq-oracle-code', 'mnq-private-data', 'mnq-private-results', 'outputs')
PART_BYTES = 500_000
EXCLUDED_DIRS = {'__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache', '.git'}
FORBIDDEN_NAMES = {'Dataset_NQ_1min_2022_2025.csv'}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def create() -> dict:
    archive = HERE / 'latest-mnq-snapshot.zip'
    part_dir = HERE / 'parts/latest-mnq-snapshot.zip'
    if archive.exists() or part_dir.exists() or (HERE / 'latest_snapshot_index.json').exists():
        raise ValueError('Latest snapshot already exists; choose a new version instead of overwriting')
    files = []
    for root in ROOTS:
        directory = WORKSPACE / root
        if not directory.is_dir():
            raise ValueError(f'Missing workspace root: {root}')
        for path in directory.rglob('*'):
            if path.is_symlink():
                raise ValueError(f'Symlink not allowed in snapshot: {path}')
            if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.relative_to(WORKSPACE).parts):
                continue
            if path.name in FORBIDDEN_NAMES or '2025' in path.name.lower():
                raise ValueError(f'Sealed 2025 file encountered: {path}')
            files.append(path)
    files.sort(key=lambda p: p.relative_to(WORKSPACE).as_posix())
    if not files:
        raise ValueError('No snapshot files')
    manifest = {'version': 1, 'roots': list(ROOTS), 'sealed_2025_raw_included': False,
                'files': {}}
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as stream:
        for path in files:
            relative = path.relative_to(WORKSPACE).as_posix()
            payload = path.read_bytes()
            manifest['files'][relative] = {'bytes': len(payload), 'sha256': digest(payload)}
            info = zipfile.ZipInfo(relative, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            stream.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        info = zipfile.ZipInfo('_snapshot_manifest.json', (1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        stream.writestr(info, json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    part_dir.mkdir(parents=True)
    parts = []
    with archive.open('rb') as source:
        for index, data in enumerate(iter(lambda: source.read(PART_BYTES), b'')):
            relative = f'cloud-transfer/parts/latest-mnq-snapshot.zip/{index:04d}.part'
            path = HERE.parent / relative
            path.write_bytes(data)
            parts.append({'path': relative, 'bytes': len(data), 'git_blob_sha1': git_blob_sha1(data)})
    index = {'version': 1, 'private_research_only': True, 'sealed_2025_raw_included': False,
             'archive': {'name': archive.name, 'bytes': archive.stat().st_size,
                         'sha256': digest(archive.read_bytes()), 'parts': parts},
             'file_count': len(files), 'manifest_sha256': digest(json.dumps(manifest, indent=2, sort_keys=True).encode() + b'\n')}
    (HERE / 'latest_snapshot_index.json').write_text(json.dumps(index, indent=2) + '\n')
    archive.unlink()
    return index


if __name__ == '__main__':
    result = create()
    print(f"Packed {result['file_count']} files into {result['archive']['bytes']} verified bytes across {len(result['archive']['parts'])} Git parts")
