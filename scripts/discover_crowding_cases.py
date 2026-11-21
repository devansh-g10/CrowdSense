"""Find real, schedule-aligned historical classifications; never create model data."""
import json

from backend.config import PROJECT_ROOT
from backend.database import Database, _rows
from scripts.inspect_database import sha256


def discover_cases(db=None):
    db = db or Database()
    with db.connection() as con:
        con.execute('SET enable_progress_bar = false')
        con.execute('''CREATE TEMP VIEW scheduled_segments AS SELECT *,
            lead(stop_id) OVER w AS to_stop_id, lead(departure_seconds) OVER w AS next_seconds
            FROM trip_schedule WINDOW w AS (PARTITION BY trip_id ORDER BY stop_sequence)''')
        sql = '''SELECT s.route_id,s.pattern_id,s.trip_id,s.stop_id AS from_stop_id,s.to_stop_id,
            s.stop_sequence,s.departure_seconds,s.next_seconds,m.is_weekend,m.crowding_level,
            m.data_support,m.predicted_load FROM scheduled_segments s JOIN crowding_model m
            ON m.route_id=s.route_id AND m.pattern_id=s.pattern_id AND m.stop_sequence=s.stop_sequence
                AND m.from_stop_id=s.stop_id AND m.to_stop_id=s.to_stop_id
                AND m.time_slot=floor(s.departure_seconds/1800)::INTEGER
            WHERE s.departure_seconds<86400 AND s.next_seconds>s.departure_seconds
                AND m.crowding_level=? {support_filter}
            ORDER BY s.trip_id,s.stop_sequence,m.is_weekend LIMIT 1'''
        cases = {}
        for label in ('Low', 'Moderate', 'High', 'Insufficient Data'):
            rows = _rows(con, sql.format(support_filter=''), [label])
            if not rows:
                raise ValueError(f'No real schedule-aligned example for {label}')
            cases[label] = rows[0]
            cases[label]['travel_date'] = '2026-11-21' if rows[0]['is_weekend'] else '2026-11-20'
        rows = _rows(con, sql.format(support_filter="AND m.data_support='Medium'"), ['Insufficient Data'])
        if rows:
            cases['Medium support Insufficient Data'] = rows[0]
            cases['Medium support Insufficient Data']['travel_date'] = '2026-11-21' if rows[0]['is_weekend'] else '2026-11-20'
        low = cases['Low']
        long_start = _rows(con, '''SELECT stop_id,stop_sequence,departure_seconds FROM trip_schedule
            WHERE trip_id=? AND stop_sequence<? ORDER BY stop_sequence LIMIT 1''',
            [low['trip_id'], low['stop_sequence']])[0]
        cases['slot_crossing'] = {**low, 'from_stop_id': long_start['stop_id'],
            'boarding_sequence': long_start['stop_sequence'], 'boarding_departure_seconds': long_start['departure_seconds']}
        zero = _rows(con, '''SELECT route_id,pattern_id,trip_id,stop_id AS from_stop_id,to_stop_id,
            stop_sequence,departure_seconds,next_seconds FROM scheduled_segments
            WHERE stop_id<>to_stop_id AND departure_seconds=next_seconds
            ORDER BY trip_id,stop_sequence LIMIT 1''')
        if zero:
            cases['zero_duration'] = {**zero[0], 'travel_date': '2026-11-20'}
    return {'cases': cases, 'inputs_sha256': {name: sha256(db.settings.data_dir / name)
        for name in ('crowding_model.parquet', 'trip_schedule.parquet')}}


if __name__ == '__main__':
    result = discover_cases()
    (PROJECT_ROOT / 'docs/phase5-crowding-cases.json').write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
