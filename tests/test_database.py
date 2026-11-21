"""Integration tests using actual private exports. No fabricated transit data.

Run: ./.venv/Scripts/python.exe -m unittest discover -s tests -v
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import duckdb

from backend.config import PROJECT_ROOT, Settings
from backend.database import Database, SCHEMAS, _rows
from scripts.inspect_database import inspect_database, sha256


class DatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = Database(Settings())
        cls.phase1 = json.loads((PROJECT_ROOT / 'docs/phase1-verification.json').read_text())
        cls.audit = inspect_database(cls.db)
        with cls.db.connection() as con:
            cls.stop = _rows(con, 'SELECT * FROM stops ORDER BY stop_id LIMIT 1')[0]
            cls.pattern = _rows(con, '''SELECT * FROM route_stop_sequence
                ORDER BY pattern_id, stop_sequence LIMIT 1''')[0]
            cls.trip = _rows(con, '''SELECT * FROM trip_schedule
                WHERE departure_seconds >= 86400 ORDER BY departure_seconds, trip_id, stop_sequence LIMIT 1''')[0]
            cls.prediction = _rows(con, '''SELECT * FROM crowding_model
                WHERE crowding_level = 'Insufficient Data' AND baseline_prediction IS NULL
                ORDER BY route_id, pattern_id, stop_sequence, is_weekend, time_slot LIMIT 1''')[0]
            cls.supported = _rows(con, '''SELECT * FROM crowding_model
                WHERE crowding_level <> 'Insufficient Data'
                ORDER BY route_id, pattern_id, stop_sequence, is_weekend, time_slot LIMIT 1''')[0]
            cls.analytics = _rows(con, '''SELECT * FROM route_analytics
                ORDER BY route_id, is_weekend, time_slot LIMIT 1''')[0]

    def test_actual_schemas_and_row_counts(self):
        expected = {f['name'].removesuffix('.parquet'): f for f in self.phase1['files']
                    if f['name'].endswith('.parquet')}
        self.assertEqual(set(self.audit['tables']), set(SCHEMAS))
        for name, table in self.audit['tables'].items():
            with self.subTest(table=name):
                self.assertEqual(table['rows'], expected[name]['rows'])
                self.assertEqual([(c['column_name'], c['column_type']) for c in table['schema']],
                                 [(c['name'], c['type']) for c in expected[name]['schema']])

    def test_keys_and_relationships(self):
        self.assertTrue(all(t['duplicate_key_rows'] == 0 for t in self.audit['tables'].values()))
        self.assertTrue(all(n == 0 for n in self.audit['relationships'].values()), self.audit['relationships'])

    def test_nulls_are_preserved_and_explicit(self):
        for table, item in self.audit['tables'].items():
            for column, count in item['nulls'].items():
                self.assertEqual(count, 381153 if (table, column) == ('crowding_model', 'baseline_prediction') else 0)
            self.assertTrue(all(count == 0 for count in item['blank_strings'].values()))

    def test_classifications_and_values(self):
        self.assertEqual({r['crowding_level']: r['profiles'] for r in self.audit['classifications']},
                         self.phase1['classifications'])
        self.assertTrue(all(n == 0 for n in self.audit['value_checks'].values()))
        self.assertEqual(self.audit['coordinate_checks']['invalid_stops'], 0)
        self.assertEqual(self.audit['schedule_range']['negative_times'], 0)

    def test_stops_search_and_lookup(self):
        result = self.db.stops(stop_id=self.stop['stop_id'])
        self.assertEqual(result, [{k: self.stop[k] for k in ('stop_id', 'stop_name', 'latitude', 'longitude')}])
        self.assertEqual(self.db.stops(search=self.stop['stop_name'].swapcase(), stop_id=self.stop['stop_id']), result)

    def test_routes_and_stop_relationship(self):
        p = self.pattern
        result = self.db.routes(route_id=p['route_id'], stop_id=p['stop_id'])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['route_id'], p['route_id'])
        self.assertEqual(self.db.routes(search=result[0]['route_short_name'], route_id=p['route_id']), result)

    def test_patterns_and_ordered_stops(self):
        p = self.pattern
        patterns = self.db.route_patterns(p['route_id'], limit=1000)
        self.assertIn(p['pattern_id'], [r['pattern_id'] for r in patterns])
        stops = self.db.pattern_stops(p['route_id'], p['pattern_id'], limit=1000)
        summary = next(r for r in patterns if r['pattern_id'] == p['pattern_id'])
        self.assertEqual(len(stops), summary['stop_count'])
        self.assertEqual([r['stop_sequence'] for r in stops], sorted(r['stop_sequence'] for r in stops))
        self.assertEqual(stops[0]['stop_id'], p['stop_id'])

    def test_schedule_exact_filters_and_after_midnight(self):
        t = self.trip
        result = self.db.trip_schedule(t['route_id'], pattern_id=t['pattern_id'],
            stop_id=t['stop_id'], trip_id=t['trip_id'],
            after_seconds=t['departure_seconds'], before_seconds=t['departure_seconds'])
        self.assertIn(t, result)
        self.assertGreaterEqual(result[0]['departure_seconds'], 86400)
        self.assertEqual(self.audit['schedule_range']['events_after_midnight'], 18457)
        self.assertEqual(self.audit['schedule_range']['maximum_seconds'], 104113)

    def _prediction_query(self, sample):
        return self.db.crowding_predictions(sample['route_id'], sample['pattern_id'],
            sample['is_weekend'], sample['time_slot'], stop_sequence=sample['stop_sequence'],
            from_stop_id=sample['from_stop_id'], to_stop_id=sample['to_stop_id'])

    def test_insufficient_data_and_missing_baseline_unchanged(self):
        self.assertEqual(self._prediction_query(self.prediction), [self.prediction])
        self.assertIsNone(self.prediction['baseline_prediction'])
        self.assertEqual(self.prediction['crowding_level'], 'Insufficient Data')

    def test_supported_prediction_unchanged(self):
        self.assertEqual(self._prediction_query(self.supported), [self.supported])

    def test_exported_analytics_unchanged(self):
        a = self.analytics
        self.assertEqual(self.db.analytics(a['route_id'], is_weekend=a['is_weekend'],
                                          time_slot=a['time_slot']), [a])

    def test_empty_results_never_fabricate_fallbacks(self):
        missing = "' OR 1=1 --"
        self.assertEqual(self.db.stops(stop_id=missing), [])
        self.assertEqual(self.db.routes(route_id=missing), [])
        self.assertEqual(self.db.route_patterns(missing), [])
        self.assertEqual(self.db.pattern_stops(missing, 0), [])
        self.assertEqual(self.db.trip_schedule(missing), [])
        self.assertEqual(self.db.crowding_predictions(missing, 0, False, 0), [])
        self.assertEqual(self.db.analytics(missing), [])
        self.assertEqual(self.db.stops(search='%'), [])

    def test_bounded_deterministic_pagination(self):
        first = self.db.stops(limit=3)
        second = self.db.stops(limit=3, offset=3)
        self.assertEqual(first + second, self.db.stops(limit=6))
        self.assertEqual(self.db.routes(limit=1) + self.db.routes(limit=1, offset=1), self.db.routes(limit=2))
        self.assertEqual(len(first), 3)

    def test_invalid_query_inputs(self):
        for limit in (0, -1, 1001, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.db.stops(limit=limit)
        for offset in (-1, True, '0'):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.db.routes(offset=offset)
        for slot in (-1, 48, True, '1'):
            with self.subTest(slot=slot), self.assertRaises(ValueError):
                self.db.crowding_predictions('1', 1, False, slot)
        with self.assertRaises(ValueError):
            self.db.crowding_predictions('1', 1, 'false', 0)
        with self.assertRaises(ValueError):
            self.db.trip_schedule('1', after_seconds=10, before_seconds=9)
        with self.assertRaises(ValueError):
            self.db.pattern_stops('1', True)
        with self.assertRaises(ValueError):
            self.db.routes(route_id=1)

    def test_portable_settings_from_different_working_directory(self):
        previous = Path.cwd()
        with TemporaryDirectory() as directory:
            try:
                os.chdir(directory)
                with patch.dict(os.environ, {'CROWDROUTE_DATA_DIR': 'data/processed',
                                             'CROWDROUTE_RUNTIME_DIR': 'data/runtime'}):
                    settings = Settings.from_env()
                self.assertEqual(settings.data_dir, PROJECT_ROOT / 'data/processed')
                self.assertTrue(Database(settings).stops(limit=1))
            finally:
                os.chdir(previous)

    def test_bad_configuration_and_missing_exports(self):
        for kwargs in ({'threads': 0}, {'memory_limit': 'unlimited'}, {'max_query_rows': 0},
                       {'runtime_dir': self.db.settings.data_dir / 'spill'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Settings(**kwargs)
        with TemporaryDirectory() as directory:
            db = Database(Settings(data_dir=Path(directory)))
            with self.assertRaisesRegex(FileNotFoundError, 'Missing model exports'):
                db.stops(limit=1)

    def test_connection_limits_cleanup_and_exception_recovery(self):
        with TemporaryDirectory() as directory:
            db = Database(Settings(runtime_dir=Path(directory)))
            with self.assertRaisesRegex(RuntimeError, 'test cleanup'):
                with db.connection() as con:
                    settings = _rows(con, "SELECT current_setting('threads') AS threads, current_setting('memory_limit') AS memory_limit")
                    self.assertEqual(settings[0]['threads'], 2)
                    self.assertEqual(settings[0]['memory_limit'], '244.1 MiB')
                    raise RuntimeError('test cleanup')
            self.assertEqual(list(Path(directory).iterdir()), [])
            with self.assertRaises(duckdb.Error):
                con.execute('SELECT 1')
            self.assertEqual(len(db.stops(limit=1)), 1)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_concurrent_queries_use_independent_sessions(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.db.stops(limit=2), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(results[0]), 2)

    def test_all_original_and_processed_assets_unchanged(self):
        for item in self.phase1['files']:
            for directory in (PROJECT_ROOT / 'CrowdRoute_Delhi_Model', self.db.settings.data_dir):
                with self.subTest(path=str(directory / item['name'])):
                    self.assertEqual(sha256(directory / item['name']), item['sha256'])

    @classmethod
    def tearDownClass(cls):
        # Run again after every test/query to detect accidental asset mutation.
        for item in cls.phase1['files']:
            for directory in (PROJECT_ROOT / 'CrowdRoute_Delhi_Model', cls.db.settings.data_dir):
                if sha256(directory / item['name']) != item['sha256']:
                    raise AssertionError(f'Model asset changed: {directory / item["name"]}')


if __name__ == '__main__':
    unittest.main()
