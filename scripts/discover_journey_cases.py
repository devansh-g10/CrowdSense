"""Discover real test pairs and witnesses from the exported timetable."""
import json

from backend.config import PROJECT_ROOT
from backend.database import Database, _rows


def discover_cases(db=None):
    db = db or Database()
    with db.connection() as con:
        # Temporary view over actual rows; lead preserves ordered occurrences.
        con.execute('''CREATE TEMP VIEW adjacent_events AS SELECT *,
            lead(stop_id) OVER w AS next_stop_id,
            lead(stop_sequence) OVER w AS next_sequence,
            lead(departure_seconds) OVER w AS next_departure_seconds
            FROM trip_schedule WINDOW w AS (PARTITION BY trip_id ORDER BY stop_sequence)''')
        columns = '''trip_id, route_id, pattern_id, stop_id AS source_stop_id,
            next_stop_id AS destination_stop_id, stop_sequence AS board_sequence,
            next_sequence AS alight_sequence, departure_seconds, next_departure_seconds'''
        direct = _rows(con, 'SELECT ' + columns + ''' FROM adjacent_events
            WHERE next_stop_id <> stop_id AND next_departure_seconds > departure_seconds
            ORDER BY trip_id, stop_sequence LIMIT 1''')[0]
        midnight = _rows(con, 'SELECT ' + columns + ''' FROM adjacent_events
            WHERE next_stop_id <> stop_id AND departure_seconds < 86400 AND next_departure_seconds >= 86400
            ORDER BY trip_id, stop_sequence LIMIT 1''')[0]
        carry = _rows(con, 'SELECT ' + columns + ''' FROM adjacent_events
            WHERE next_stop_id <> stop_id AND departure_seconds >= 86400 AND next_departure_seconds > departure_seconds
            ORDER BY trip_id, stop_sequence LIMIT 1''')[0]
        repeated = _rows(con, '''SELECT trip_id, stop_id AS repeated_stop_id,
            min(stop_sequence) AS first_occurrence, max(stop_sequence) AS last_occurrence
            FROM trip_schedule GROUP BY trip_id, stop_id HAVING count(*) > 1
            ORDER BY trip_id, stop_id LIMIT 1''')[0]
        endpoints = _rows(con, '''SELECT a.stop_id AS source_stop_id, b.stop_id AS destination_stop_id,
            a.stop_sequence AS board_sequence,b.stop_sequence AS alight_sequence,a.departure_seconds
            FROM trip_schedule a JOIN trip_schedule b ON a.trip_id=b.trip_id
            WHERE a.trip_id=? AND a.stop_sequence=? AND b.stop_sequence=?''',
            [repeated['trip_id'], repeated['first_occurrence'] - 1, repeated['last_occurrence'] + 1])[0]
        repeated.update(endpoints)
        transfer = _rows(con, '''SELECT a.trip_id AS first_trip, a.stop_id AS transfer_stop_id,
            a.stop_sequence AS first_alight_sequence,a.departure_seconds AS first_arrival_seconds,
            b.trip_id AS second_trip,b.stop_sequence AS second_board_sequence,
            b.departure_seconds AS second_departure_seconds,
            d.stop_id AS destination_stop_id,d.departure_seconds AS destination_arrival_seconds
            FROM trip_schedule a JOIN trip_schedule b ON a.stop_id=b.stop_id
                AND b.departure_seconds BETWEEN a.departure_seconds+120 AND a.departure_seconds+1800
            JOIN trip_schedule d ON d.trip_id=b.trip_id AND d.stop_sequence=b.stop_sequence+1
            WHERE a.trip_id=? AND a.stop_sequence>? AND a.trip_id<>b.trip_id
                AND d.departure_seconds>b.departure_seconds AND d.stop_id<>?
                AND NOT EXISTS (SELECT 1 FROM route_stop_sequence p JOIN route_stop_sequence q
                    ON p.pattern_id=q.pattern_id AND p.stop_sequence<q.stop_sequence
                    WHERE p.stop_id=? AND q.stop_id=d.stop_id)
            ORDER BY destination_arrival_seconds,first_arrival_seconds,second_trip LIMIT 1''',
            [direct['trip_id'], direct['board_sequence'], direct['source_stop_id'], direct['source_stop_id']])[0]
        transfer.update(source_stop_id=direct['source_stop_id'], departure_seconds=direct['departure_seconds'])
        cross_day = _rows(con, '''SELECT a.trip_id AS first_trip, a.stop_id AS transfer_stop_id,
            a.stop_sequence AS first_alight_sequence,a.departure_seconds AS first_arrival_seconds,
            b.trip_id AS second_trip,b.departure_seconds+86400 AS second_departure_seconds,
            d.stop_id AS destination_stop_id,d.departure_seconds+86400 AS destination_arrival_seconds
            FROM trip_schedule a JOIN trip_schedule b ON b.stop_id=a.stop_id
                AND b.departure_seconds+86400 BETWEEN a.departure_seconds+120 AND a.departure_seconds+1800
            JOIN trip_schedule d ON d.trip_id=b.trip_id AND d.stop_sequence=b.stop_sequence+1
            WHERE a.trip_id=? AND a.stop_sequence>? AND a.stop_id<>? AND d.stop_id<>?
                AND d.departure_seconds>b.departure_seconds
            ORDER BY destination_arrival_seconds,second_trip LIMIT 1''',
            [midnight['trip_id'], midnight['board_sequence'], midnight['source_stop_id'], midnight['source_stop_id']])[0]
        cross_day.update(source_stop_id=midnight['source_stop_id'], departure_seconds=midnight['departure_seconds'])
        no_direct = _rows(con, '''SELECT stop_id AS destination_stop_id FROM stops s
            WHERE stop_id <> ? AND NOT EXISTS (
                SELECT 1 FROM route_stop_sequence x JOIN route_stop_sequence y
                    ON x.pattern_id=y.pattern_id AND x.stop_sequence<y.stop_sequence
                WHERE x.stop_id=? AND y.stop_id=s.stop_id) ORDER BY stop_id LIMIT 1''',
            [direct['source_stop_id'], direct['source_stop_id']])[0]
        no_direct.update(source_stop_id=direct['source_stop_id'], departure_seconds=direct['departure_seconds'])
        schedule = _rows(con, '''WITH t AS (SELECT *, lag(departure_seconds) OVER (
                PARTITION BY trip_id ORDER BY stop_sequence) AS prev FROM trip_schedule)
            SELECT count(*) FILTER (WHERE departure_seconds < prev) AS backwards_events,
                count(*) FILTER (WHERE departure_seconds = prev) AS equal_time_events FROM t''')[0]
        return {'reference_travel_date': '2026-11-20', 'direct': direct, 'transfer_only': transfer,
                'midnight': midnight, 'previous_service_day': carry, 'cross_service_day_transfer': cross_day,
                'repeated_stops': repeated, 'no_direct': no_direct, 'schedule_order_checks': schedule,
                'calendar_exception_files': [p.name for p in db.settings.data_dir.glob('calendar_dates.*')]}


if __name__ == '__main__':
    result = discover_cases()
    (PROJECT_ROOT / 'docs/phase4-journey-cases.json').write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
