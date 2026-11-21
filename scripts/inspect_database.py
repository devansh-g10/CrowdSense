"""Inspect actual exports through the database layer; never alter source files.

Run from the project root: python -m scripts.inspect_database
"""
import hashlib
import json

from backend.config import PROJECT_ROOT
from backend.database import Database, SCHEMAS, _rows

KEYS = {
    'stops': 'stop_id', 'routes': 'route_id', 'calendar': 'service_id',
    'route_lookup': 'ticket_route',
    'route_stop_sequence': 'pattern_id, stop_sequence',
    'trip_schedule': 'trip_id, stop_sequence',
    'crowding_model': 'route_id, pattern_id, stop_sequence, from_stop_id, to_stop_id, is_weekend, time_slot',
    'route_analytics': 'route_id, is_weekend, time_slot',
}

RELATIONSHIPS = {
    'pattern_route_missing': 'SELECT count(*) FROM route_stop_sequence p ANTI JOIN routes r USING (route_id)',
    'pattern_stop_missing': 'SELECT count(*) FROM route_stop_sequence p ANTI JOIN stops s USING (stop_id)',
    'lookup_route_missing': 'SELECT count(*) FROM route_lookup l ANTI JOIN routes r USING (route_id)',
    'schedule_route_missing': 'SELECT count(*) FROM trip_schedule t ANTI JOIN routes r USING (route_id)',
    'schedule_stop_missing': 'SELECT count(*) FROM trip_schedule t ANTI JOIN stops s USING (stop_id)',
    'schedule_service_missing': 'SELECT count(*) FROM trip_schedule t ANTI JOIN calendar c USING (service_id)',
    'schedule_pattern_stop_missing': '''SELECT count(*) FROM trip_schedule t ANTI JOIN
        route_stop_sequence p USING (route_id, pattern_id, stop_sequence, stop_id)''',
    'model_route_missing': 'SELECT count(*) FROM crowding_model m ANTI JOIN routes r USING (route_id)',
    'model_from_stop_missing': 'SELECT count(*) FROM crowding_model m ANTI JOIN stops s ON m.from_stop_id = s.stop_id',
    'model_to_stop_missing': 'SELECT count(*) FROM crowding_model m ANTI JOIN stops s ON m.to_stop_id = s.stop_id',
    'model_pattern_segment_missing': '''WITH segments AS (
        SELECT route_id, pattern_id, stop_sequence, stop_id AS from_stop_id,
        lead(stop_id) OVER (PARTITION BY route_id, pattern_id ORDER BY stop_sequence) AS to_stop_id
        FROM route_stop_sequence)
        SELECT count(*) FROM crowding_model m ANTI JOIN segments s
        USING (route_id, pattern_id, stop_sequence, from_stop_id, to_stop_id)''',
    'analytics_route_missing': 'SELECT count(*) FROM route_analytics a ANTI JOIN routes r USING (route_id)',
    'analytics_model_group_missing': '''SELECT count(*) FROM route_analytics a ANTI JOIN
        (SELECT DISTINCT route_id, is_weekend, time_slot FROM crowding_model) m
        USING (route_id, is_weekend, time_slot)''',
    'model_analytics_group_missing': '''SELECT count(*) FROM
        (SELECT DISTINCT route_id, is_weekend, time_slot FROM crowding_model) m
        ANTI JOIN route_analytics a USING (route_id, is_weekend, time_slot)''',
    'pattern_multiple_routes': '''SELECT count(*) FROM (SELECT pattern_id FROM
        route_stop_sequence GROUP BY pattern_id HAVING count(DISTINCT route_id) <> 1)''',
    'trip_multiple_patterns_or_services': '''SELECT count(*) FROM (SELECT trip_id
        FROM trip_schedule GROUP BY trip_id HAVING count(DISTINCT (route_id, pattern_id, service_id)) <> 1)''',
    'analytics_classification_count_mismatch': '''WITH counts AS (
        SELECT route_id, is_weekend, time_slot, count(*) AS n,
            count(*) FILTER (WHERE crowding_level = 'Low') AS low,
            count(*) FILTER (WHERE crowding_level = 'Moderate') AS moderate,
            count(*) FILTER (WHERE crowding_level = 'High') AS high,
            count(*) FILTER (WHERE crowding_level = 'Insufficient Data') AS insufficient
        FROM crowding_model GROUP BY route_id, is_weekend, time_slot)
        SELECT count(*) FROM route_analytics a JOIN counts c USING (route_id, is_weekend, time_slot)
        WHERE a.segment_profiles <> c.n OR a.low_crowding_segments <> c.low
        OR a.moderate_crowding_segments <> c.moderate OR a.high_crowding_segments <> c.high
        OR a.insufficient_data_segments <> c.insufficient''',
}


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inspect_database(db=None):
    db = db or Database()
    report = {'tables': {}, 'relationships': {}, 'settings': {
        'memory_limit': db.settings.memory_limit, 'threads': db.settings.threads,
        'max_temp_directory_size': db.settings.max_temp_directory_size}}
    with db.connection() as con:
        for table in SCHEMAS:
            schema = _rows(con, f'DESCRIBE {table}')
            columns = [row['column_name'] for row in schema]
            nulls = _rows(con, 'SELECT ' + ', '.join(
                f'count(*) FILTER (WHERE "{name}" IS NULL) AS "{name}"'
                for name in columns) + f' FROM {table}')[0]
            strings = [row['column_name'] for row in schema if row['column_type'] == 'VARCHAR']
            blanks = _rows(con, 'SELECT ' + ', '.join(
                f'count(*) FILTER (WHERE trim("{name}") = \'\') AS "{name}"'
                for name in strings) + f' FROM {table}')[0] if strings else {}
            counts = _rows(con, f'SELECT count(*) AS rows, count(DISTINCT ({KEYS[table]})) AS distinct_keys FROM {table}')[0]
            report['tables'][table] = {
                'schema': schema, **counts, 'duplicate_key_rows': counts['rows'] - counts['distinct_keys'],
                'nulls': nulls, 'blank_strings': blanks,
                'sha256': sha256(db.settings.data_dir / f'{table}.parquet')}
        for name, sql in RELATIONSHIPS.items():
            report['relationships'][name] = con.execute(sql).fetchall()[0][0]
        report['classifications'] = _rows(con, '''SELECT crowding_level, count(*) AS profiles
            FROM crowding_model GROUP BY crowding_level ORDER BY crowding_level''')
        report['value_checks'] = _rows(con, '''SELECT
            count(*) FILTER (WHERE time_slot NOT BETWEEN 0 AND 47) AS invalid_slots,
            count(*) FILTER (WHERE predicted_load < 0 OR NOT isfinite(predicted_load)) AS invalid_loads,
            count(*) FILTER (WHERE crowding_level NOT IN ('Low', 'Moderate', 'High', 'Insufficient Data')) AS unknown_labels,
            count(*) FILTER (WHERE crowding_level <> 'Insufficient Data' AND
                (predicted_load IS NULL OR sample_journeys < 5 OR observed_days < 3 OR
                 reference_samples IS NULL OR reference_samples < 20)) AS unsupported_classifications
            FROM crowding_model''')[0]
        report['schedule_range'] = _rows(con, '''SELECT min(departure_seconds) AS minimum_seconds,
            max(departure_seconds) AS maximum_seconds,
            count(*) FILTER (WHERE departure_seconds >= 86400) AS events_after_midnight,
            count(*) FILTER (WHERE departure_seconds < 0) AS negative_times FROM trip_schedule''')[0]
        report['coordinate_checks'] = _rows(con, '''SELECT count(*) FILTER (
            WHERE latitude NOT BETWEEN -90 AND 90 OR longitude NOT BETWEEN -180 AND 180
            OR NOT isfinite(latitude) OR NOT isfinite(longitude)) AS invalid_stops FROM stops''')[0]
    return report


if __name__ == '__main__':
    report = inspect_database()
    path = PROJECT_ROOT / 'docs' / 'phase2-database-verification.json'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('Tables:', {name: row['rows'] for name, row in report['tables'].items()})
    print('Nonzero null counts:', {name: {k: v for k, v in row['nulls'].items() if v}
          for name, row in report['tables'].items() if any(row['nulls'].values())})
    print('Nonzero blank counts:', {name: {k: v for k, v in row['blank_strings'].items() if v}
          for name, row in report['tables'].items() if any(row['blank_strings'].values())})
    print('Duplicate keys:', {name: row['duplicate_key_rows'] for name, row in report['tables'].items()})
    print('Relationships:', report['relationships'])
    print('Value checks:', report['value_checks'])
    print('Schedule range:', report['schedule_range'])
    print('Coordinate checks:', report['coordinate_checks'])
