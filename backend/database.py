"""Bounded, parameterized queries over immutable Parquet-backed DuckDB views.

Every session owns its in-memory database and spill directory. No connections or
lazy results are shared between threads. Exports are only opened for reading;
there is no persistent database or table materialization.
"""
from contextlib import contextmanager
from tempfile import TemporaryDirectory

import duckdb

from .config import Settings

# Observed directly with DuckDB DESCRIBE on all eight actual Parquet exports.
SCHEMAS = {
    'calendar': 'service_id:VARCHAR monday:VARCHAR tuesday:VARCHAR wednesday:VARCHAR thursday:VARCHAR friday:VARCHAR saturday:VARCHAR sunday:VARCHAR start_date:VARCHAR end_date:VARCHAR',
    'stops': 'stop_id:VARCHAR stop_name:VARCHAR stop_key:VARCHAR latitude:DOUBLE longitude:DOUBLE',
    'routes': 'agency_id:VARCHAR route_id:VARCHAR route_long_name:VARCHAR route_short_name:VARCHAR route_desc:VARCHAR route_type:VARCHAR',
    'route_lookup': 'ticket_route:VARCHAR route_id:VARCHAR',
    'route_stop_sequence': 'pattern_id:BIGINT route_id:VARCHAR stop_id:VARCHAR stop_name:VARCHAR stop_key:VARCHAR stop_sequence:BIGINT latitude:DOUBLE longitude:DOUBLE',
    'trip_schedule': 'pattern_id:BIGINT route_id:VARCHAR trip_id:VARCHAR service_id:VARCHAR stop_id:VARCHAR stop_sequence:BIGINT departure_seconds:INTEGER',
    'crowding_model': 'route_id:VARCHAR pattern_id:BIGINT stop_sequence:BIGINT from_stop_id:VARCHAR to_stop_id:VARCHAR is_weekend:BOOLEAN time_slot:INTEGER baseline_prediction:DOUBLE predicted_load:DOUBLE prediction_source:VARCHAR sample_journeys:BIGINT observed_days:BIGINT peak_load_p90:DOUBLE lower_threshold:DOUBLE upper_threshold:DOUBLE reference_samples:BIGINT data_support:VARCHAR crowding_level:VARCHAR',
    'route_analytics': 'route_id:VARCHAR route_name:VARCHAR is_weekend:BOOLEAN time_slot:INTEGER segment_profiles:BIGINT average_recorded_load:DOUBLE maximum_recorded_load:DOUBLE low_crowding_segments:DOUBLE moderate_crowding_segments:DOUBLE high_crowding_segments:DOUBLE insufficient_data_segments:DOUBLE',
}
CROWDING_NOTICE = ('Relative historical crowding is not actual bus occupancy '
                   'or guaranteed seat availability.')


def _rows(connection, sql, parameters=()):
    result = connection.execute(sql, parameters)
    names = [column[0] for column in result.description]
    # Fully consume the result before issuing another statement (DuckDB 2.x).
    return [dict(zip(names, row)) for row in result.fetchall()]


class Database:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()

    @contextmanager
    def connection(self):
        """Own one connection per request/batch; always close, even on failure.

        The yielded connection is an internal SQL interface, not an untrusted
        user SQL endpoint. Memory limits apply per active session; callers must
        bound the number of simultaneous sessions in a future server.
        """
        missing = [str(self.settings.data_dir / f'{name}.parquet')
                   for name in SCHEMAS
                   if not (self.settings.data_dir / f'{name}.parquet').is_file()]
        if missing:
            raise FileNotFoundError('Missing model exports: ' + ', '.join(missing))
        self.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='duckdb-', dir=self.settings.runtime_dir) as spill:
            con = duckdb.connect(':memory:', config={
                'memory_limit': self.settings.memory_limit,
                'threads': self.settings.threads,
                'temp_directory': spill,
                'max_temp_directory_size': self.settings.max_temp_directory_size,
                'preserve_insertion_order': 'false',
            })
            try:
                for name, definition in SCHEMAS.items():
                    relation = con.read_parquet(str(self.settings.data_dir / f'{name}.parquet'))
                    actual = list(zip(relation.columns, map(str, relation.types)))
                    expected = [tuple(item.split(':')) for item in definition.split()]
                    if actual != expected:
                        raise ValueError(f'Unexpected schema for {name}: {actual!r}')
                    relation.create_view(name)
                yield con
            finally:
                con.close()

    def _page(self, limit, offset):
        if type(limit) is not int or not 1 <= limit <= self.settings.max_query_rows:
            raise ValueError(f'limit must be between 1 and {self.settings.max_query_rows}')
        if type(offset) is not int or offset < 0:
            raise ValueError('offset must be a nonnegative integer')
        return [limit, offset]

    def _query(self, sql, parameters):
        with self.connection() as con:
            return _rows(con, sql, parameters)

    @staticmethod
    def _id(value, name):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{name} must be a nonempty string (GTFS IDs are strings)')
        return value

    @staticmethod
    def _integer(value, name):
        if type(value) is not int or value < 0:
            raise ValueError(f'{name} must be a nonnegative integer')
        return value

    @staticmethod
    def _slot(value):
        if type(value) is not int or not 0 <= value <= 47:
            raise ValueError('time_slot must be an integer between 0 and 47')
        return value

    def stops(self, *, search='', stop_id=None, limit=100, offset=0):
        """Literal substring search with deterministic stop ID pagination."""
        if not isinstance(search, str):
            raise ValueError('search must be a string')
        conditions, params = ['contains(lower(stop_name), lower(?))'], [search]
        if stop_id is not None:
            conditions.append('stop_id = ?')
            params.append(self._id(stop_id, 'stop_id'))
        return self._query('SELECT stop_id, stop_name, latitude, longitude FROM stops WHERE '
                           + ' AND '.join(conditions) + ' ORDER BY stop_id LIMIT ? OFFSET ?',
                           params + self._page(limit, offset))

    def routes(self, *, search='', route_id=None, stop_id=None, limit=100, offset=0):
        if not isinstance(search, str):
            raise ValueError('search must be a string')
        conditions = ['(contains(lower(route_short_name), lower(?)) OR contains(lower(route_long_name), lower(?)))']
        params = [search, search]
        if route_id is not None:
            conditions.append('r.route_id = ?')
            params.append(self._id(route_id, 'route_id'))
        if stop_id is not None:
            conditions.append('EXISTS (SELECT 1 FROM route_stop_sequence p WHERE p.route_id = r.route_id AND p.stop_id = ?)')
            params.append(self._id(stop_id, 'stop_id'))
        return self._query('SELECT r.* FROM routes r WHERE ' + ' AND '.join(conditions)
                           + ' ORDER BY r.route_id LIMIT ? OFFSET ?', params + self._page(limit, offset))

    def route_patterns(self, route_id, *, limit=100, offset=0):
        return self._query('''SELECT route_id, pattern_id, count(*) AS stop_count,
            min(stop_sequence) AS first_sequence, max(stop_sequence) AS last_sequence
            FROM route_stop_sequence WHERE route_id = ? GROUP BY route_id, pattern_id
            ORDER BY pattern_id LIMIT ? OFFSET ?''',
            [self._id(route_id, 'route_id')] + self._page(limit, offset))

    def pattern_stops(self, route_id, pattern_id, *, limit=100, offset=0):
        return self._query('''SELECT route_id, pattern_id, stop_sequence, stop_id,
            stop_name, latitude, longitude FROM route_stop_sequence
            WHERE route_id = ? AND pattern_id = ? ORDER BY stop_sequence LIMIT ? OFFSET ?''',
            [self._id(route_id, 'route_id'), self._integer(pattern_id, 'pattern_id')]
            + self._page(limit, offset))

    def trip_schedule(self, route_id, *, pattern_id=None, stop_id=None, trip_id=None,
                      after_seconds=0, before_seconds=None, limit=100, offset=0):
        """Scheduled stop events, not a journey plan. Seconds may exceed 86400.

        Bounds are inclusive; dates/service exceptions are not inferred here.
        """
        conditions = ['route_id = ?', 'departure_seconds >= ?']
        params = [self._id(route_id, 'route_id'), self._integer(after_seconds, 'after_seconds')]
        if before_seconds is not None:
            self._integer(before_seconds, 'before_seconds')
            if before_seconds < after_seconds:
                raise ValueError('before_seconds must be >= after_seconds')
            conditions.append('departure_seconds <= ?')
            params.append(before_seconds)
        for name, value in [('pattern_id', pattern_id), ('stop_id', stop_id), ('trip_id', trip_id)]:
            if value is not None:
                conditions.append(f'{name} = ?')
                params.append(self._integer(value, name) if name == 'pattern_id' else self._id(value, name))
        return self._query('SELECT * FROM trip_schedule WHERE ' + ' AND '.join(conditions)
                           + ' ORDER BY departure_seconds, trip_id, stop_sequence LIMIT ? OFFSET ?',
                           params + self._page(limit, offset))

    def crowding_predictions(self, route_id, pattern_id, is_weekend, time_slot, *,
                             stop_sequence=None, from_stop_id=None, to_stop_id=None,
                             limit=100, offset=0):
        """Return exported values and labels unchanged. Missing key => empty list.

        No new fallback is computed: the export already includes hourly fallback.
        Numeric values on Insufficient Data rows must not be shown as reliable
        estimates. All values represent relative historical crowding.
        """
        if type(is_weekend) is not bool:
            raise ValueError('is_weekend must be a boolean')
        conditions = ['route_id = ?', 'pattern_id = ?', 'is_weekend = ?', 'time_slot = ?']
        params = [self._id(route_id, 'route_id'), self._integer(pattern_id, 'pattern_id'),
                  is_weekend, self._slot(time_slot)]
        for name, value in [('stop_sequence', stop_sequence), ('from_stop_id', from_stop_id), ('to_stop_id', to_stop_id)]:
            if value is not None:
                conditions.append(f'{name} = ?')
                params.append(self._integer(value, name) if name == 'stop_sequence' else self._id(value, name))
        return self._query('SELECT * FROM crowding_model WHERE ' + ' AND '.join(conditions)
                           + ' ORDER BY stop_sequence, from_stop_id, to_stop_id LIMIT ? OFFSET ?',
                           params + self._page(limit, offset))

    def analytics(self, route_id, *, is_weekend=None, time_slot=None, limit=100, offset=0):
        conditions, params = ['route_id = ?'], [self._id(route_id, 'route_id')]
        if is_weekend is not None:
            if type(is_weekend) is not bool:
                raise ValueError('is_weekend must be a boolean')
            conditions.append('is_weekend = ?')
            params.append(is_weekend)
        if time_slot is not None:
            conditions.append('time_slot = ?')
            params.append(self._slot(time_slot))
        return self._query('SELECT * FROM route_analytics WHERE ' + ' AND '.join(conditions)
                           + ' ORDER BY is_weekend, time_slot LIMIT ? OFFSET ?',
                           params + self._page(limit, offset))

    def route_segments(self, route_id, *, pattern_id=None, limit=100, offset=0):
        """Consecutive pattern stops only; no inferred routes or geometries."""
        condition, params = 'route_id = ?', [self._id(route_id, 'route_id')]
        if pattern_id is not None:
            condition += ' AND pattern_id = ?'
            params.append(self._integer(pattern_id, 'pattern_id'))
        return self._query('''WITH ordered AS (
            SELECT route_id, pattern_id, stop_sequence,
                stop_id AS from_stop_id, stop_name AS from_stop_name,
                latitude AS from_latitude, longitude AS from_longitude,
                lead(stop_id) OVER w AS to_stop_id, lead(stop_name) OVER w AS to_stop_name,
                lead(latitude) OVER w AS to_latitude, lead(longitude) OVER w AS to_longitude
            FROM route_stop_sequence WHERE ''' + condition + '''
            WINDOW w AS (PARTITION BY route_id, pattern_id ORDER BY stop_sequence))
            SELECT * FROM ordered WHERE to_stop_id IS NOT NULL
            ORDER BY pattern_id, stop_sequence LIMIT ? OFFSET ?''', params + self._page(limit, offset))

    def overview(self):
        with self.connection() as con:
            counts = _rows(con, '''SELECT
                (SELECT count(*) FROM stops) AS stops,
                (SELECT count(*) FROM routes) AS routes,
                (SELECT count(DISTINCT pattern_id) FROM route_stop_sequence) AS patterns,
                (SELECT count(DISTINCT trip_id) FROM trip_schedule) AS trips,
                (SELECT count(*) FROM trip_schedule) AS scheduled_stop_events,
                (SELECT count(*) FROM crowding_model) AS profiles,
                (SELECT count(DISTINCT route_id) FROM crowding_model) AS routes_with_profiles''')[0]
            counts['classifications'] = dict(con.execute('''SELECT crowding_level, count(*)
                FROM crowding_model GROUP BY crowding_level''').fetchall())
            return counts

    def _analytics_filters(self, route_id, is_weekend, time_slot, search=''):
        conditions, params = [], []
        for name, value in [('route_id', route_id), ('is_weekend', is_weekend), ('time_slot', time_slot)]:
            if value is not None:
                if name == 'route_id':
                    value = self._id(value, name)
                elif name == 'time_slot':
                    value = self._slot(value)
                elif type(value) is not bool:
                    raise ValueError('is_weekend must be a boolean')
                conditions.append(f'{name} = ?')
                params.append(value)
        if search:
            conditions.append('(contains(lower(route_name), lower(?)) OR contains(lower(route_id), lower(?)))')
            params.extend([search, search])
        return (' WHERE ' + ' AND '.join(conditions) if conditions else ''), params

    def analytics_rows(self, *, route_id=None, is_weekend=None, time_slot=None, search='',
                       aggregate_routes=False, aggregate_slots=False, limit=100, offset=0):
        where, params = self._analytics_filters(route_id, is_weekend, time_slot, search)
        if aggregate_routes:
            sql = '''SELECT route_id, route_name, sum(segment_profiles)::BIGINT AS profiles,
                sum(low_crowding_segments)::BIGINT AS low_profiles,
                sum(moderate_crowding_segments)::BIGINT AS moderate_profiles,
                sum(high_crowding_segments)::BIGINT AS high_profiles,
                sum(insufficient_data_segments)::BIGINT AS insufficient_data_profiles
                FROM route_analytics''' + where + ' GROUP BY route_id, route_name ORDER BY route_id'
        elif aggregate_slots:
            sql = '''SELECT is_weekend, time_slot, sum(segment_profiles)::BIGINT AS segment_profiles,
                sum(high_crowding_segments)::BIGINT AS high_crowding_segments,
                sum(insufficient_data_segments)::BIGINT AS insufficient_data_segments
                FROM route_analytics''' + where + ' GROUP BY is_weekend, time_slot ORDER BY is_weekend, time_slot'
        else:
            sql = 'SELECT * FROM route_analytics' + where + ' ORDER BY route_id, is_weekend, time_slot'
        return self._query(sql + ' LIMIT ? OFFSET ?', params + self._page(limit, offset))

    def high_segments(self, *, route_id=None, is_weekend=None, time_slot=None, limit=100, offset=0):
        where, params = self._analytics_filters(route_id, is_weekend, time_slot)
        predicate = where + (' AND ' if where else ' WHERE ') + "crowding_level = 'High'"
        sql = '''WITH selected AS (
            SELECT route_id, pattern_id, stop_sequence, from_stop_id, to_stop_id, time_slot,
                   is_weekend, sample_journeys, observed_days FROM crowding_model''' + predicate + '''
            ORDER BY sample_journeys DESC, route_id, pattern_id, stop_sequence, is_weekend, time_slot
            LIMIT ? OFFSET ?)
            SELECT s.* EXCLUDE (from_stop_id, to_stop_id), a.stop_name AS from_name, b.stop_name AS to_name
            FROM selected s JOIN stops a ON a.stop_id=s.from_stop_id JOIN stops b ON b.stop_id=s.to_stop_id
            ORDER BY sample_journeys DESC, route_id, pattern_id, stop_sequence, is_weekend, time_slot'''
        return self._query(sql, params + self._page(limit, offset))
