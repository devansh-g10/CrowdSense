"""Stage immutable existing exports and verify them; never execute training code."""
from pathlib import Path, PurePosixPath
import argparse
import csv
import hashlib
import json
import shutil
import stat
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {
    'calendar.parquet': 1, 'crowding_model.parquet': 1063956,
    'route_analytics.parquet': 50318, 'route_lookup.parquet': 1980,
    'route_stop_sequence.parquet': 109660, 'routes.parquet': 2574,
    'stops.parquet': 6862, 'trip_schedule.parquet': 2737136,
}
EXPECTED = set(COUNTS) | {'model_metadata.json', 'model_comparison.csv',
                         'test_metrics.csv', 'peak_analysis.csv', 'weekly_analysis.csv'}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage(destination, archive):
    """Validate every member before writing; reject traversal, links and collisions."""
    if destination.is_symlink():
        raise ValueError('Destination must not be a symlink')
    if archive:
        with zipfile.ZipFile(archive) as package:
            members = {}
            for entry in package.infolist():
                path = PurePosixPath(entry.filename)
                mode = entry.external_attr >> 16
                if ('\\' in entry.filename or path.is_absolute() or
                        '..' in path.parts or ':' in entry.filename or
                        stat.S_ISLNK(mode)):
                    raise ValueError(f'Unsafe archive member: {entry.filename}')
                if entry.is_dir():
                    continue
                if (len(path.parts) not in (1, 2) or
                        (len(path.parts) == 2 and path.parts[0] != 'CrowdRoute_Delhi_Model') or
                        path.name not in EXPECTED or path.name in members or
                        entry.file_size > 256 * 1024**2):
                    raise ValueError(f'Unexpected archive member: {entry.filename}')
                members[path.name] = entry
            if set(members) != EXPECTED:
                raise ValueError('Archive must contain exactly the 13 expected exports')
            # Refuse existing mismatches before any extraction. Reading each entry checks CRC.
            for name, entry in members.items():
                target = destination / name
                with package.open(entry) as stream:
                    expected_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
                if target.is_symlink() or (target.exists() and digest(target) != expected_hash):
                    raise ValueError(f'Refusing to overwrite: {target}')
            for name, entry in members.items():
                target = destination / name
                if not target.exists():
                    with package.open(entry) as src, target.open('xb') as dst:
                        shutil.copyfileobj(src, dst, 1024 * 1024)
        return {'mode': 'zip', 'archive': str(archive), 'archive_sha256': digest(archive)}
    source = ROOT / 'CrowdRoute_Delhi_Model'
    if {p.name for p in source.iterdir() if p.is_file()} != EXPECTED:
        raise ValueError('Original export folder must contain exactly 13 expected files')
    for name in EXPECTED:
        src, dst = source / name, destination / name
        if src.is_symlink() or dst.is_symlink():
            raise ValueError('Symlink model assets are not supported')
        if dst.exists() and digest(src) != digest(dst):
            raise ValueError(f'Refusing to overwrite: {dst}')
    for name in sorted(EXPECTED):
        src, dst = source / name, destination / name
        if not dst.exists():
            with src.open('rb') as reader, dst.open('xb') as writer:
                shutil.copyfileobj(reader, writer, 1024 * 1024)
        if digest(src) != digest(dst):
            raise ValueError(f'Copy mismatch: {name}')
    return {'mode': 'existing_export_copy', 'source': str(source),
            'archive_status': 'User confirmed this folder was already extracted from the model ZIP before this session; archive bytes unavailable for CRC verification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, help='Original model ZIP; never create a replacement archive')
    args = parser.parse_args()
    import duckdb
    destination = ROOT / 'data' / 'processed'
    destination.mkdir(parents=True, exist_ok=True)
    provenance = stage(destination, args.archive.resolve() if args.archive else None)
    if {p.name for p in destination.iterdir() if p.name != '.gitkeep'} != EXPECTED:
        raise ValueError('Unexpected processed directory contents')
    con = duckdb.connect(config={'memory_limit': '256MB', 'threads': '2',
                                 'temp_directory': str(ROOT / 'data' / '.duckdb_tmp')})
    report = {'provenance': provenance, 'duckdb_version': duckdb.__version__,
              'expected_count_source': 'Notebook cell 65 saved output, not recomputed training', 'files': []}
    for path in sorted(destination.iterdir()):
        if path.name not in EXPECTED:
            continue
        item = {'name': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)}
        if not item['bytes']:
            raise ValueError(f'Empty file: {path.name}')
        if path.suffix == '.parquet':
            relation = con.read_parquet(str(path))
            item['schema'] = [{'name': n, 'type': str(t)} for n, t in zip(relation.columns, relation.types)]
            item['rows'] = relation.aggregate('count(*)').fetchall()[0][0]
            if item['rows'] != COUNTS[path.name]:
                raise ValueError(f'Notebook row count mismatch: {path.name}')
            # Hash every column to force a full decode scan instead of trusting footer counts.
            relation.aggregate('bit_xor(hash(COLUMNS(*)))').fetchall()
            item['full_column_scan'] = 'passed'
        elif path.suffix == '.csv':
            with path.open(newline='', encoding='utf-8') as stream:
                reader = csv.DictReader(stream)
                rows = list(reader)
                if not reader.fieldnames or not rows or any(None in row for row in rows):
                    raise ValueError(f'Malformed CSV: {path.name}')
                item.update(columns=reader.fieldnames, rows=len(rows), values=rows)
        else:
            item['metadata'] = json.loads(path.read_text(encoding='utf-8'))
        report['files'].append(item)
    model = con.read_parquet(str(destination / 'crowding_model.parquet'))
    model.create_view('model')
    report['classifications'] = dict(con.execute('SELECT crowding_level, count(*) FROM model GROUP BY 1').fetchall())
    if set(report['classifications']) - {'Low', 'Moderate', 'High', 'Insufficient Data'}:
        raise ValueError('Unknown crowding classification')
    invalid = con.execute('''SELECT count(*) FROM model WHERE predicted_load < 0
        OR crowding_level IS NULL OR time_slot IS NULL OR time_slot NOT BETWEEN 0 AND 47''').fetchall()[0][0]
    if invalid:
        raise ValueError(f'Invalid model rows: {invalid}')
    report['model_checks'] = {'invalid_rows': invalid, 'profile_count_matches_metadata':
        model.aggregate('count(*)').fetchall()[0][0] == json.loads((destination / 'model_metadata.json').read_text())['final_profiles']}
    if not report['model_checks']['profile_count_matches_metadata']:
        raise ValueError('Profile count metadata mismatch')
    report['verification'] = '13 files verified; existing originals unchanged'
    (ROOT / 'docs' / 'phase1-verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    con.close()
    print(report['verification'])
    print('Staging mode:', provenance['mode'])
    print('Classifications:', report['classifications'])


if __name__ == '__main__':
    main()


