"""Bounded real GTFS timetable search with at most one same-stop transfer.

No routes, stop events, arrival observations or crowding predictions are invented.
The export has departures only, so alighting departures are arrival proxies.
"""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .database import Database, _rows

IST = ZoneInfo('Asia/Kolkata')
DAY = 86400
WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')


class InvalidJourneyRequest(ValueError):
    pass


class UnknownStopError(LookupError):
    pass


@dataclass(frozen=True)
class SearchBounds:
    initial_boardings: int = 256
    destination_events: int = 2048
    transfer_events: int = 8192
    candidates_per_kind: int = 200
    stops_per_leg: int = 512

    def __post_init__(self):
        for value in vars(self).values():
            if type(value) is not int or value < 1:
                raise ValueError('Search bounds must be positive integers')


def _gtfs_date(value):
    value = str(value)
    if len(value) != 8 or not value.isdigit():
        raise ValueError('Invalid GTFS calendar date')
    return datetime.strptime(value, '%Y%m%d').date()


def _exceptions(con, data_dir):
    paths = [data_dir / name for name in ('calendar_dates.parquet', 'calendar_dates.txt', 'calendar_dates.csv')
             if (data_dir / name).is_file()]
    if len(paths) > 1:
        raise ValueError('Ambiguous calendar exception sources')
    if not paths:
        con.execute('''CREATE TEMP VIEW calendar_exceptions AS
            SELECT NULL::VARCHAR AS service_id, NULL::VARCHAR AS date,
                   NULL::VARCHAR AS exception_type WHERE false''')
        return None
    path = paths[0]
    relation = con.read_parquet(str(path)) if path.suffix == '.parquet' else con.read_csv(str(path), all_varchar=True)
    if set(relation.columns) != {'service_id', 'date', 'exception_type'}:
        raise ValueError('Unexpected calendar exception schema')
    relation.create_view('exception_input')
    con.execute('''CREATE TEMP VIEW calendar_exceptions AS SELECT service_id::VARCHAR AS service_id,
        date::VARCHAR AS date, exception_type::VARCHAR AS exception_type FROM exception_input''')
    invalid = con.execute('''SELECT count(*) FROM calendar_exceptions
        WHERE service_id IS NULL OR trim(service_id) = '' OR date IS NULL
        OR NOT regexp_full_match(date, '[0-9]{8}') OR try_strptime(date, '%Y%m%d') IS NULL
        OR exception_type IS NULL OR exception_type NOT IN ('1', '2')''').fetchall()[0][0]
    duplicates = con.execute('''SELECT count(*) FROM (SELECT service_id, date
        FROM calendar_exceptions GROUP BY service_id, date HAVING count(*) > 1)''').fetchall()[0][0]
    if invalid or duplicates:
        raise ValueError('Invalid or conflicting calendar exceptions')
    return path.name


def _calendar(con, data_dir, travel_date, horizon, max_gtfs_seconds, requested, boarding_deadline):
    """Build a tiny service-day table, including yesterday's 24+ hour trips."""
    rows = _rows(con, 'SELECT * FROM calendar LIMIT 10001')
    if not rows or len(rows) > 10000:
        raise ValueError('Calendar is empty or exceeds the supported service count')
    for row in rows:
        row['start'] = _gtfs_date(row['start_date'])
        row['end'] = _gtfs_date(row['end_date'])
        if row['start'] > row['end'] or any(row[day] not in ('0', '1') for day in WEEKDAYS):
            raise ValueError('Invalid calendar bounds or weekday flags')
    exceptions_source = _exceptions(con, data_dir)
    added_bounds = _rows(con, '''SELECT min(date) AS first_date, max(date) AS last_date
        FROM calendar_exceptions WHERE exception_type = '1' ''')[0]
    first = min(row['start'] for row in rows)
    last = max(row['end'] for row in rows)
    if added_bounds['first_date']:
        first = min(first, _gtfs_date(added_bounds['first_date']))
        last = max(last, _gtfs_date(added_bounds['last_date']))
    spill_days = max_gtfs_seconds // DAY
    if spill_days > 7:
        raise ValueError('Schedule exceeds the supported seven-day GTFS spill range')
    current = travel_date - timedelta(days=spill_days)
    service_days = []
    while current <= horizon.date():
        active = {row['service_id'] for row in rows
                  if row['start'] <= current <= row['end'] and row[WEEKDAYS[current.weekday()]] == '1'}
        overrides = _rows(con, 'SELECT service_id, exception_type FROM calendar_exceptions WHERE date = ?',
                          [current.strftime('%Y%m%d')])
        for override in overrides:
            if override['exception_type'] == '1':
                active.add(override['service_id'])
            else:
                active.discard(override['service_id'])
        for service_id in sorted(active):
            service_days.append((service_id, current, (current - travel_date).days * DAY))
        current += timedelta(days=1)
    con.execute('CREATE TEMP TABLE journey_days (service_id VARCHAR, service_date DATE, day_offset BIGINT)')
    if service_days:
        con.executemany('INSERT INTO journey_days VALUES (?, ?, ?)', service_days)
    first_possible_departure = datetime.combine(first, time(), IST)
    last_possible_departure = datetime.combine(last, time(), IST) + timedelta(seconds=max_gtfs_seconds)
    calendar_overlap = requested <= last_possible_departure and boarding_deadline >= first_possible_departure
    return {'date_supported': calendar_overlap, 'first_service_date': first,
            'last_service_date': last, 'last_possible_arrival_date': last + timedelta(days=spill_days),
            'active_service_dates': sorted({row[1] for row in service_days}),
            'exceptions_available': exceptions_source is not None, 'exceptions_source': exceptions_source}


def _bounded(con, name, sql, parameters, order, cap):
    # Identifiers/order expressions are constants supplied inside this module.
    con.execute(f'CREATE TEMP TABLE {name}_probe AS {sql} ORDER BY {order} LIMIT ?', parameters + [cap + 1])
    count = con.execute(f'SELECT count(*) FROM {name}_probe').fetchall()[0][0]
    con.execute(f'CREATE TEMP VIEW {name} AS SELECT * FROM {name}_probe ORDER BY {order} LIMIT {cap}')
    return min(count, cap), count > cap


class JourneyPlanner:
    def __init__(self, database: Database, bounds: SearchBounds | None = None):
        self.db = database
        self.bounds = bounds or SearchBounds()

    def plan(self, source_stop_id: str, destination_stop_id: str, travel_date: date,
             departure_time: time, *, max_wait_minutes=30, min_transfer_minutes=2,
             max_journey_minutes=360, max_transfers=1, limit=10, candidate_pool_limit=None):
        self.db._id(source_stop_id, 'source_stop_id')
        self.db._id(destination_stop_id, 'destination_stop_id')
        if source_stop_id == destination_stop_id:
            raise InvalidJourneyRequest('Source and destination must be different stops')
        if not isinstance(travel_date, date) or isinstance(travel_date, datetime) or not date(1900, 1, 1) <= travel_date <= date(2100, 12, 31):
            raise InvalidJourneyRequest('travel_date must be a date between 1900 and 2100')
        if not isinstance(departure_time, time) or departure_time.tzinfo is not None or departure_time.microsecond:
            raise InvalidJourneyRequest('departure_time must be a local IST time without an offset or fractions')
        for value, name, low, high in (
            (max_wait_minutes, 'max_wait_minutes', 0, 120),
            (min_transfer_minutes, 'min_transfer_minutes', 1, 30),
            (max_journey_minutes, 'max_journey_minutes', 1, 720),
            (max_transfers, 'max_transfers', 0, 1), (limit, 'limit', 1, 20)):
            if type(value) is not int or not low <= value <= high:
                raise InvalidJourneyRequest(f'{name} must be between {low} and {high}')
        # Internal ranking callers may inspect a larger bounded pool before applying
        # the public response limit; ordinary Phase 4 callers retain their behavior.
        output_limit = limit
        if candidate_pool_limit is not None:
            if type(candidate_pool_limit) is not int or not 1 <= candidate_pool_limit <= 80:
                raise InvalidJourneyRequest('candidate_pool_limit must be between 1 and 80')
            output_limit = candidate_pool_limit
        midnight = datetime.combine(travel_date, time(), IST)
        requested = datetime.combine(travel_date, departure_time, IST)
        start = int((requested - midnight).total_seconds())
        end = start + max_journey_minutes * 60
        horizon = midnight + timedelta(seconds=end)
        search = {'max_wait_minutes': max_wait_minutes, 'min_transfer_minutes': min_transfer_minutes,
                  'max_journey_minutes': max_journey_minutes, 'max_transfers': max_transfers,
                  'initial_boardings_examined': 0, 'destination_events_examined': 0,
                  'transfer_events_examined': 0, 'candidates_considered': 0,
                  'bounds': vars(self.bounds).copy(), 'search_truncated': False,
                  'result_limit': output_limit, 'result_limit_reached': False}
        warnings = ['Arrival times and durations are approximate: only stop departure times are exported.',
                    'Static schedules do not establish real-time operation or vehicle availability.',
                    'Transfers use the identical stop ID with a configurable minimum time buffer; no walking transfers or transfer rules are exported.']
        with self.db.connection() as con:
            known = {r['stop_id'] for r in _rows(con, 'SELECT stop_id FROM stops WHERE stop_id IN (?, ?)',
                                                [source_stop_id, destination_stop_id])}
            if len(known) != 2:
                raise UnknownStopError('Source or destination stop is not in the exported dataset')
            max_gtfs_seconds = con.execute('SELECT max(departure_seconds) FROM trip_schedule').fetchall()[0][0]
            if max_gtfs_seconds is None or max_gtfs_seconds < 0:
                raise ValueError('Schedule has no valid departure times')
            boarding_deadline = midnight + timedelta(seconds=min(end, start + max_wait_minutes * 60))
            coverage = _calendar(con, self.db.settings.data_dir, travel_date, horizon, max_gtfs_seconds,
                                 requested, boarding_deadline)
            if not coverage['exceptions_available']:
                warnings.append('No calendar exception file is exported; holiday additions/removals and cancellations cannot be checked.')
            response = {'status': 'no_journeys', 'reason': None, 'source_stop_id': source_stop_id,
                        'destination_stop_id': destination_stop_id, 'requested_departure_at': requested,
                        'calendar': coverage, 'search': search, 'journeys': [], 'warnings': warnings}
            if not coverage['date_supported']:
                response.update(status='unsupported_date', reason='Search window is outside the exported service calendar coverage.')
                return response
            if not coverage['active_service_dates']:
                response['reason'] = 'No active services in the requested search window.'
                return response
            sql = '''SELECT t.*, d.service_date, d.day_offset,
                        t.departure_seconds + d.day_offset AS absolute_seconds
                     FROM trip_schedule t JOIN journey_days d USING (service_id)
                     JOIN routes r USING (route_id) WHERE r.route_type = '3' AND t.stop_id = ?
                     AND t.departure_seconds + d.day_offset BETWEEN ? AND ?'''
            order = 'absolute_seconds, trip_id, service_date, stop_sequence'
            search['initial_boardings_examined'], truncated = _bounded(con, 'initial_boardings', sql,
                [source_stop_id, start, min(end, start + max_wait_minutes * 60)], order, self.bounds.initial_boardings)
            search['search_truncated'] |= truncated
            search['destination_events_examined'], truncated = _bounded(con, 'destination_events', sql,
                [destination_stop_id, start, end], order, self.bounds.destination_events)
            search['search_truncated'] |= truncated
            direct = _rows(con, '''SELECT b.trip_id, b.route_id, b.pattern_id, b.service_date,
                    b.stop_sequence AS board_sequence, a.stop_sequence AS alight_sequence,
                    b.absolute_seconds AS departure_seconds, a.absolute_seconds AS arrival_seconds
                FROM initial_boardings b JOIN destination_events a
                    ON b.trip_id = a.trip_id AND b.service_date = a.service_date
                WHERE b.stop_sequence < a.stop_sequence AND b.absolute_seconds <= a.absolute_seconds
                ORDER BY arrival_seconds, departure_seconds, b.trip_id, b.service_date, board_sequence, alight_sequence
                LIMIT ?''', [self.bounds.candidates_per_kind + 1])
            search['search_truncated'] |= len(direct) > self.bounds.candidates_per_kind
            candidates = [[row] for row in direct[:self.bounds.candidates_per_kind]]
            if max_transfers and max_wait_minutes >= min_transfer_minutes:
                n, truncated = _bounded(con, 'transfer_events', '''SELECT b.trip_id, b.route_id, b.pattern_id,
                    b.service_date, b.stop_sequence AS board_sequence,
                    b.absolute_seconds AS board_absolute_seconds,
                    t.stop_sequence AS alight_sequence, t.stop_id AS transfer_stop_id,
                    t.departure_seconds + b.day_offset AS absolute_seconds
                    FROM initial_boardings b JOIN trip_schedule t ON b.trip_id = t.trip_id
                    WHERE t.stop_sequence > b.stop_sequence
                    AND t.departure_seconds + b.day_offset BETWEEN b.absolute_seconds AND ?
                    AND t.stop_id NOT IN (?, ?)''', [end, source_stop_id, destination_stop_id],
                    'absolute_seconds, trip_id, service_date, board_sequence, alight_sequence', self.bounds.transfer_events)
                search['transfer_events_examined'] = n
                search['search_truncated'] |= truncated
                transfers = _rows(con, '''SELECT f.trip_id, f.route_id, f.pattern_id, f.service_date,
                    f.board_sequence, f.alight_sequence, f.board_absolute_seconds AS departure_seconds,
                    f.absolute_seconds AS arrival_seconds,
                    a.trip_id AS second_trip_id, a.route_id AS second_route_id,
                    a.pattern_id AS second_pattern_id, a.service_date AS second_service_date,
                    b.stop_sequence AS second_board_sequence, a.stop_sequence AS second_alight_sequence,
                    b.departure_seconds + a.day_offset AS second_departure_seconds,
                    a.absolute_seconds AS second_arrival_seconds
                    FROM transfer_events f JOIN trip_schedule b ON b.stop_id = f.transfer_stop_id
                    JOIN destination_events a ON a.trip_id = b.trip_id
                    WHERE b.stop_sequence < a.stop_sequence
                    AND b.departure_seconds + a.day_offset BETWEEN f.absolute_seconds + ? AND f.absolute_seconds + ?
                    AND a.absolute_seconds >= b.departure_seconds + a.day_offset
                    AND (a.trip_id <> f.trip_id OR a.service_date <> f.service_date)
                    ORDER BY second_arrival_seconds, departure_seconds, f.trip_id, f.service_date,
                        f.board_sequence, f.alight_sequence, second_trip_id, second_service_date,
                        second_board_sequence, second_alight_sequence LIMIT ?''',
                    [min_transfer_minutes * 60, max_wait_minutes * 60, self.bounds.candidates_per_kind + 1])
                search['search_truncated'] |= len(transfers) > self.bounds.candidates_per_kind
                for row in transfers[:self.bounds.candidates_per_kind]:
                    first = {key: value for key, value in row.items() if not key.startswith('second_')}
                    second = {key.removeprefix('second_'): value for key, value in row.items() if key.startswith('second_')}
                    candidates.append([first, second])
            candidates.sort(key=lambda legs: (legs[-1]['arrival_seconds'], len(legs), legs[0]['departure_seconds'],
                tuple((leg['trip_id'], leg['service_date'], leg['board_sequence'], leg['alight_sequence']) for leg in legs)))
            search['candidates_considered'] = len(candidates)
            cache, journeys = {}, []
            for index, candidate in enumerate(candidates):
                legs = []
                for leg in candidate:
                    key = (leg['trip_id'], leg['service_date'], leg['board_sequence'], leg['alight_sequence'])
                    if key not in cache:
                        batch_size = min(8, output_limit - len(journeys))
                        self._load_legs(con, candidates[index:index + batch_size], cache)
                    if cache[key] is None:
                        search['search_truncated'] = True
                        break
                    legs.append(cache[key])
                if len(legs) != len(candidate):
                    continue
                transfer_wait = int((legs[1]['departure_at'] - legs[0]['estimated_arrival_at']).total_seconds()) if len(legs) == 2 else 0
                initial_wait = int((legs[0]['departure_at'] - requested).total_seconds())
                in_vehicle = sum(leg['approximate_duration_seconds'] for leg in legs)
                journeys.append({'transfers': len(legs) - 1,
                    'departure_at': legs[0]['departure_at'], 'estimated_arrival_at': legs[-1]['estimated_arrival_at'],
                    'initial_wait_seconds': initial_wait, 'transfer_wait_seconds': transfer_wait,
                    'in_vehicle_duration_seconds': in_vehicle,
                    'travel_duration_seconds': in_vehicle + transfer_wait,
                    'total_duration_seconds': initial_wait + in_vehicle + transfer_wait,
                    'duration_is_approximate': True, 'arrival_time_basis': 'alighting_stop_departure_proxy',
                    'legs': legs})
                if len(journeys) >= output_limit:
                    search['result_limit_reached'] = len(candidates) > len(journeys)
                    break
            response['journeys'] = journeys
            if journeys:
                response['status'] = 'ok'
            elif search['search_truncated']:
                response.update(status='search_incomplete', reason='No journey found within candidate bounds; a complete search was not performed.')
            else:
                response['reason'] = 'No feasible journey within the requested transfer, wait and duration bounds.'
            if search['search_truncated']:
                warnings.append('Candidate search limits were reached or an invalid/oversized leg was excluded; results may omit other feasible journeys.')
            return response

    def _load_legs(self, con, candidates, cache):
        pending = {}
        for candidate in candidates:
            for leg in candidate:
                key = (leg['trip_id'], leg['service_date'], leg['board_sequence'], leg['alight_sequence'])
                if key not in cache:
                    pending[key] = leg
        # Each request represents one dated boarding/alighting occurrence. Keep
        # one extra row per leg so the original oversized-leg check still applies.
        values = ','.join('(?,?,?,?)' for _ in pending)
        params = [value for i, (trip, _, start, end) in enumerate(pending)
                  for value in (i, trip, start, end)]
        rows = _rows(con, f'''WITH requested(idx, trip, first_seq, last_seq) AS (VALUES {values})
            SELECT q.idx, t.route_id, t.pattern_id, t.trip_id, t.service_id, t.stop_sequence,
                   t.stop_id, t.departure_seconds, p.stop_name, p.latitude, p.longitude, r.route_short_name
            FROM requested q JOIN trip_schedule t
              ON t.trip_id=q.trip AND t.stop_sequence BETWEEN q.first_seq AND q.last_seq
            JOIN route_stop_sequence p
                USING (route_id, pattern_id, stop_sequence, stop_id)
            JOIN routes r USING (route_id)
            QUALIFY row_number() OVER (PARTITION BY q.idx ORDER BY t.stop_sequence) <= ?
            ORDER BY q.idx, t.stop_sequence''', params + [self.bounds.stops_per_leg + 1])
        grouped = [[] for _ in pending]
        for row in rows:
            grouped[row['idx']].append(row)
        for (key, leg), events in zip(pending.items(), grouped):
            cache[key] = self._leg(events, leg)

    def _leg(self, rows, candidate):
        if (len(rows) < 2 or len(rows) > self.bounds.stops_per_leg
                or rows[0]['stop_sequence'] != candidate['board_sequence']
                or rows[-1]['stop_sequence'] != candidate['alight_sequence']
                or any(b['departure_seconds'] < a['departure_seconds'] for a, b in zip(rows, rows[1:]))):
            return None
        service_midnight = datetime.combine(candidate['service_date'], time(), IST)
        stops = [{'stop_id': row['stop_id'], 'stop_name': row['stop_name'], 'stop_sequence': row['stop_sequence'],
                  'latitude': row['latitude'], 'longitude': row['longitude'],
                  'gtfs_departure_seconds': row['departure_seconds'],
                  'scheduled_departure_at': service_midnight + timedelta(seconds=row['departure_seconds'])} for row in rows]
        segments = [{'from_stop_id': a['stop_id'], 'to_stop_id': b['stop_id'],
                     'from_stop_sequence': a['stop_sequence'], 'to_stop_sequence': b['stop_sequence'],
                     'departure_at': a['scheduled_departure_at'], 'estimated_arrival_at': b['scheduled_departure_at'],
                     'approximate_duration_seconds': int((b['scheduled_departure_at'] - a['scheduled_departure_at']).total_seconds())}
                    for a, b in zip(stops, stops[1:])]
        return {'route_id': rows[0]['route_id'], 'route_name': rows[0]['route_short_name'],
                'pattern_id': rows[0]['pattern_id'], 'trip_id': rows[0]['trip_id'],
                'service_id': rows[0]['service_id'], 'service_date': candidate['service_date'],
                'boarding_stop_sequence': rows[0]['stop_sequence'], 'alighting_stop_sequence': rows[-1]['stop_sequence'],
                'departure_at': stops[0]['scheduled_departure_at'], 'estimated_arrival_at': stops[-1]['scheduled_departure_at'],
                'approximate_duration_seconds': rows[-1]['departure_seconds'] - rows[0]['departure_seconds'],
                'stops': stops, 'intermediate_stops': stops[1:-1], 'segments': segments}
