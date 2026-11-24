"""HTTP integration tests against actual exports; fault tests mock errors only."""
import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import duckdb
from fastapi.testclient import TestClient

from backend.config import PROJECT_ROOT, Settings
from backend.database import Database, CROWDING_NOTICE, _rows
from backend.main import create_app
from scripts.inspect_database import sha256

API_PATHS = {
    '/api/health', '/api/model-info', '/api/stops', '/api/routes',
    '/api/routes/{route_id}', '/api/routes/{route_id}/segments', '/api/crowding',
    '/api/analytics/overview', '/api/analytics/routes', '/api/analytics/heatmap',
    '/api/analytics/weekly', '/api/analytics/peak-hours', '/api/analytics/model-performance',
    '/api/journeys', '/api/analytics/high-segments',
}


class ApiIntegrationTests(unittest.TestCase):
    def test_operator_filters_and_slot_denominators(self):
        cells = self.get('/api/analytics/heatmap', {'aggregate_slots': True})['items']
        overview = self.get('/api/analytics/overview')
        self.assertEqual(sum(c['segment_profiles'] for c in cells), overview['profiles'])
        self.assertEqual(sum(c['high_crowding_segments'] for c in cells), overview['classifications']['High'])
        row = self.get('/api/analytics/high-segments', {'limit': 1})['items'][0]
        params = {key: row[key] for key in ('route_id', 'is_weekend', 'time_slot')}
        detail = self.get('/api/crowding', {**params, 'pattern_id': row['pattern_id'],
            'stop_sequence': row['stop_sequence']})['items'][0]
        self.assertEqual(detail['crowding_level'], 'High')
        self.assertEqual(detail['sample_journeys'], row['sample_journeys'])
        route = self.get('/api/analytics/routes', {**params, 'search': row['route_id']})['items'][0]
        cell = self.get('/api/analytics/heatmap', {**params, 'aggregate_slots': True})['items'][0]
        self.assertEqual(route['profiles'], cell['segment_profiles'])
        self.assertEqual(route['high_profiles'], cell['high_crowding_segments'])
        self.assertEqual(self.get('/api/analytics/high-segments', {**params, 'limit': 1})['items'][0], row)
        self.assertEqual(self.get('/api/analytics/routes', {'search': 'nonexistent route name'})['items'], [])

    @classmethod
    def setUpClass(cls):
        runtime = TemporaryDirectory()
        cls.addClassCleanup(runtime.cleanup)
        settings = Settings(runtime_dir=Path(runtime.name))
        cls.app = create_app(settings)
        cls.client = TestClient(cls.app, raise_server_exceptions=False)
        cls.db = cls.app.state.resources.db
        cls.phase1 = json.loads((PROJECT_ROOT / 'docs/phase1-verification.json').read_text())
        with cls.db.connection() as con:
            cls.stop = _rows(con, 'SELECT * FROM stops ORDER BY stop_id LIMIT 1')[0]
            cls.pattern = _rows(con, 'SELECT * FROM route_stop_sequence ORDER BY pattern_id, stop_sequence LIMIT 1')[0]
            cls.samples = {}
            for label in ('Low', 'Moderate', 'High', 'Insufficient Data'):
                cls.samples[label] = _rows(con, '''SELECT * FROM crowding_model WHERE crowding_level = ?
                    ORDER BY route_id, pattern_id, stop_sequence, is_weekend, time_slot LIMIT 1''', [label])[0]
            cls.missing_baseline = _rows(con, '''SELECT * FROM crowding_model WHERE baseline_prediction IS NULL
                ORDER BY route_id, pattern_id, stop_sequence, is_weekend, time_slot LIMIT 1''')[0]
            cls.segment = _rows(con, '''WITH ordered AS (
                SELECT *, lead(stop_id) OVER w AS next_stop_id, lead(stop_name) OVER w AS next_name,
                    lead(latitude) OVER w AS next_latitude, lead(longitude) OVER w AS next_longitude
                FROM route_stop_sequence WHERE route_id = ? AND pattern_id = ?
                WINDOW w AS (ORDER BY stop_sequence))
                SELECT * FROM ordered WHERE next_stop_id IS NOT NULL ORDER BY stop_sequence LIMIT 1''',
                [cls.pattern['route_id'], cls.pattern['pattern_id']])[0]
            cls.extra_counts = _rows(con, '''SELECT
                (SELECT count(DISTINCT pattern_id) FROM route_stop_sequence) AS patterns,
                (SELECT count(DISTINCT trip_id) FROM trip_schedule) AS trips,
                (SELECT count(DISTINCT route_id) FROM crowding_model) AS routes_with_profiles''')[0]

    def get(self, path, params=None, status=200):
        response = self.client.get(path, params=params)
        self.assertEqual(response.status_code, status, response.text)
        return response.json()

    def prediction(self, sample):
        return self.get('/api/crowding', {k: sample[k] for k in (
            'route_id', 'pattern_id', 'is_weekend', 'time_slot', 'stop_sequence', 'from_stop_id', 'to_stop_id')})

    def test_health_checks_actual_exports(self):
        self.assertEqual(self.get('/api/health'), {'status': 'ok', 'database': 'ready', 'model_files': 'ready'})

    def test_model_info_matches_original_metadata(self):
        metadata = json.loads((self.db.settings.data_dir / 'model_metadata.json').read_text())
        self.assertEqual(self.get('/api/model-info'), {**metadata, 'notice': CROWDING_NOTICE})
        self.assertFalse(metadata['actual_occupancy_validated'])
        self.assertFalse(metadata['capacity_calibration_available'])

    def test_stops_search_and_pagination(self):
        first = self.get('/api/stops', {'limit': 3})
        second = self.get('/api/stops', {'limit': 3, 'offset': 3})
        full = self.get('/api/stops', {'limit': 6})
        self.assertEqual(first['items'] + second['items'], full['items'])
        self.assertEqual((first['limit'], first['offset'], first['returned']), (3, 0, 3))
        result = self.get('/api/stops', {'search': self.stop['stop_name'].swapcase(), 'stop_id': self.stop['stop_id']})
        self.assertEqual(result['items'], [{k: self.stop[k] for k in ('stop_id', 'stop_name', 'latitude', 'longitude')}])

    def test_route_list_filters(self):
        p = self.pattern
        result = self.get('/api/routes', {'route_id': p['route_id'], 'stop_id': p['stop_id']})
        self.assertEqual(result['items'], self.db.routes(route_id=p['route_id'], stop_id=p['stop_id']))
        by_name = self.get('/api/routes', {'search': result['items'][0]['route_short_name'], 'route_id': p['route_id']})
        self.assertEqual(by_name['items'], result['items'])

    def test_route_detail_patterns(self):
        route_id = self.pattern['route_id']
        result = self.get(f'/api/routes/{route_id}', {'limit': 1})
        self.assertEqual(result['route'], self.db.routes(route_id=route_id)[0])
        self.assertEqual(result['patterns']['items'], self.db.route_patterns(route_id, limit=1))
        self.assertEqual(result['patterns']['limit'], 1)

    def test_route_segments_are_actual_consecutive_stops(self):
        row = self.segment
        result = self.get(f'/api/routes/{row["route_id"]}/segments', {'pattern_id': row['pattern_id'], 'limit': 1})
        self.assertEqual(result['items'], [{
            'route_id': row['route_id'], 'pattern_id': row['pattern_id'], 'stop_sequence': row['stop_sequence'],
            'from_stop_id': row['stop_id'], 'from_stop_name': row['stop_name'],
            'from_latitude': row['latitude'], 'from_longitude': row['longitude'],
            'to_stop_id': row['next_stop_id'], 'to_stop_name': row['next_name'],
            'to_latitude': row['next_latitude'], 'to_longitude': row['next_longitude'],
        }])

    def test_missing_routes_and_patterns_are_404(self):
        self.assertEqual(self.get('/api/routes/__missing__', status=404)['error']['code'], 'not_found')
        self.get('/api/routes/__missing__/segments', status=404)
        self.get(f'/api/routes/{self.pattern["route_id"]}/segments', {'pattern_id': 2**63 - 1}, status=404)

    def test_all_supported_prediction_labels_keep_actual_values(self):
        for label in ('Low', 'Moderate', 'High'):
            with self.subTest(label=label):
                sample = self.samples[label]
                result = self.prediction(sample)
                self.assertEqual(result['status'], 'available')
                item = result['items'][0]
                self.assertTrue(item['available'])
                self.assertIsNone(item['unavailable_reason'])
                self.assertEqual(item['exported_predicted_load'], sample['predicted_load'])
                self.assertEqual({k: item[k] for k in sample}, sample)

    def test_insufficient_prediction_is_null_not_zero(self):
        sample = self.samples['Insufficient Data']
        result = self.prediction(sample)
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['unavailable_reason'], 'insufficient_data')
        item = result['items'][0]
        self.assertIsNone(item['predicted_load'])
        self.assertFalse(item['available'])
        self.assertEqual(item['crowding_level'], 'Insufficient Data')
        self.assertEqual(item['exported_predicted_load'], sample['predicted_load'])
        self.assertEqual({k: item[k] for k in sample if k != 'predicted_load'},
                         {k: v for k, v in sample.items() if k != 'predicted_load'})

    def test_null_baseline_preserved(self):
        item = self.prediction(self.missing_baseline)['items'][0]
        self.assertIsNone(item['baseline_prediction'])
        self.assertEqual(item['exported_predicted_load'], self.missing_baseline['predicted_load'])

    def test_mixed_support_reports_partial_availability(self):
        with self.db.connection() as con:
            sample = _rows(con, '''SELECT route_id, pattern_id, is_weekend, time_slot
                FROM crowding_model GROUP BY route_id, pattern_id, is_weekend, time_slot
                HAVING count(*) <= 1000 AND
                    count(*) FILTER (WHERE crowding_level = 'Insufficient Data') BETWEEN 1 AND count(*) - 1
                ORDER BY route_id, pattern_id, is_weekend, time_slot LIMIT 1''')[0]
        result = self.get('/api/crowding', {**sample, 'limit': 1000})
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(any(item['available'] for item in result['items']))
        self.assertTrue(any(not item['available'] for item in result['items']))
        self.assertTrue(all(item['predicted_load'] is None for item in result['items'] if not item['available']))

    def test_missing_prediction_has_explicit_unavailable_response(self):
        result = self.get('/api/crowding', {'route_id': '__missing__', 'pattern_id': 0,
                                         'is_weekend': False, 'time_slot': 0})
        self.assertEqual(result['items'], [])
        self.assertEqual(result['status'], 'unavailable')
        self.assertEqual(result['unavailable_reason'], 'no_matching_exported_profile')
        self.assertEqual(result['notice'], CROWDING_NOTICE)

    def test_empty_prediction_page_does_not_claim_missing_model(self):
        sample = self.samples['Moderate']
        result = self.get('/api/crowding', {'route_id': sample['route_id'], 'pattern_id': sample['pattern_id'],
            'is_weekend': sample['is_weekend'], 'time_slot': sample['time_slot'], 'offset': 1000000})
        self.assertEqual(result['items'], [])
        self.assertEqual(result['unavailable_reason'], 'no_profiles_on_page')

    def test_overview_counts_match_exports(self):
        result = self.get('/api/analytics/overview')
        for column, expected in self.extra_counts.items():
            self.assertEqual(result[column], expected)
        self.assertEqual(result['stops'], 6862)
        self.assertEqual(result['routes'], 2574)
        self.assertEqual(result['scheduled_stop_events'], 2737136)
        self.assertEqual(result['profiles'], 1063956)
        self.assertEqual(result['classifications'], self.phase1['classifications'])
        self.assertEqual(sum(result['classifications'].values()), result['profiles'])

    def test_route_analytics_classification_sums(self):
        sample = self.samples['Moderate']
        result = self.get('/api/analytics/routes', {'route_id': sample['route_id']})
        with self.db.connection() as con:
            expected = _rows(con, '''SELECT count(*) AS profiles,
                count(*) FILTER (WHERE crowding_level = 'Low') AS low_profiles,
                count(*) FILTER (WHERE crowding_level = 'Moderate') AS moderate_profiles,
                count(*) FILTER (WHERE crowding_level = 'High') AS high_profiles,
                count(*) FILTER (WHERE crowding_level = 'Insufficient Data') AS insufficient_data_profiles
                FROM crowding_model WHERE route_id = ?''', [sample['route_id']])[0]
        self.assertEqual(len(result['items']), 1)
        self.assertEqual({k: result['items'][0][k] for k in expected}, expected)

    def test_heatmap_matches_saved_analytics_and_paginates(self):
        sample = self.samples['Moderate']
        params = {k: sample[k] for k in ('route_id', 'is_weekend', 'time_slot')}
        result = self.get('/api/analytics/heatmap', params)
        self.assertEqual(result['items'], self.db.analytics(**params))
        first = self.get('/api/analytics/heatmap', {'limit': 2})
        second = self.get('/api/analytics/heatmap', {'limit': 2, 'offset': 2})
        self.assertEqual(first['items'] + second['items'], self.get('/api/analytics/heatmap', {'limit': 4})['items'])

    def csv(self, name):
        with (self.db.settings.data_dir / name).open(newline='', encoding='utf-8') as stream:
            return list(csv.DictReader(stream))

    def test_weekly_saved_values(self):
        result = self.get('/api/analytics/weekly')
        expected = self.csv('weekly_analysis.csv')
        self.assertEqual(len(result['items']), 5)
        for item, row in zip(result['items'], expected):
            for key, value in row.items():
                self.assertEqual(item[key], float(value))
        self.assertEqual(result['source'], 'weekly_analysis.csv')

    def test_peak_hours_saved_values_and_day_filter(self):
        result = self.get('/api/analytics/peak-hours')
        self.assertEqual(len(result['items']), 6)
        for item, row in zip(result['items'], self.csv('peak_analysis.csv')):
            for key, value in row.items():
                self.assertEqual(item[key], value if key in ('day_type', 'period') else float(value))
        weekend = self.get('/api/analytics/peak-hours', {'day_type': 'Weekend'})
        self.assertEqual(weekend['items'], [row for row in result['items'] if row['day_type'] == 'Weekend'])

    def test_model_performance_is_saved_evaluation(self):
        result = self.get('/api/analytics/model-performance')
        self.assertEqual(result['test_metrics'], {k: float(v) for k, v in self.csv('test_metrics.csv')[0].items()})
        self.assertEqual(result['model_comparison'], [
            {k: v if k == 'model' else float(v) for k, v in row.items()}
            for row in self.csv('model_comparison.csv')])
        self.assertIn('different denominators', result['evaluation_note'])

    def test_request_validation(self):
        crowd = {'route_id': self.pattern['route_id'], 'pattern_id': self.pattern['pattern_id'],
                 'is_weekend': False, 'time_slot': 0}
        requests = [('/api/stops', {'limit': 0}), ('/api/stops', {'limit': 1001}),
            ('/api/routes', {'offset': -1}), ('/api/routes', {'offset': 2**70}),
            ('/api/crowding', {}), ('/api/crowding', {**crowd, 'time_slot': 48}),
            ('/api/crowding', {**crowd, 'is_weekend': 'someday'}),
            ('/api/crowding', {**crowd, 'pattern_id': -1}),
            ('/api/crowding', {**crowd, 'pattern_id': 2**70}),
            ('/api/crowding', {**crowd, 'route_id': ' '}),
            ('/api/analytics/heatmap', {'time_slot': -1}),
            ('/api/analytics/peak-hours', {'day_type': 'Holiday'})]
        for path, params in requests:
            with self.subTest(path=path, params=params):
                self.assertEqual(self.get(path, params, status=422)['error']['code'], 'invalid_input')

    def test_parameterized_queries_treat_injection_as_literal(self):
        injected = "' OR 1=1 --"
        self.assertEqual(self.get('/api/stops', {'search': injected})['items'], [])
        self.assertEqual(self.get('/api/stops', {'search': '%'})['items'], [])
        self.assertEqual(self.get('/api/routes', {'route_id': injected})['items'], [])
        self.assertEqual(self.get('/api/analytics/heatmap', {'route_id': injected})['items'], [])

    def test_local_cors(self):
        allowed = self.client.options('/api/stops', headers={'Origin': 'http://localhost:5173',
            'Access-Control-Request-Method': 'GET'})
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers['access-control-allow-origin'], 'http://localhost:5173')
        denied = self.client.options('/api/stops', headers={'Origin': 'https://example.com',
            'Access-Control-Request-Method': 'GET'})
        self.assertEqual(denied.status_code, 400)
        self.assertNotIn('access-control-allow-origin', denied.headers)
        method = self.client.options('/api/stops', headers={'Origin': 'http://localhost:5173',
            'Access-Control-Request-Method': 'POST'})
        self.assertEqual(method.status_code, 400)
        for kwargs in ({'runtime_dir': 'CrowdRoute_Delhi_Model/temp'},
                       {'runtime_dir': 'data/processed/spill', 'data_dir': 'alternate'},
                       {'cors_origins': ('*',)}, {'cors_origins': ('https://example.com',)},
                       {'max_concurrent_queries': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Settings(**kwargs)

    def test_capacity_limit_and_release(self):
        slots = self.app.state.query_slots
        count = self.app.state.resources.db.settings.max_concurrent_queries
        for _ in range(count):
            self.assertTrue(slots.acquire(blocking=False))
        try:
            response = self.client.get('/api/health')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.headers['retry-after'], '1')
        finally:
            for _ in range(count):
                slots.release()
        self.get('/api/health')

    def test_missing_exports_are_safe_503(self):
        with TemporaryDirectory() as directory:
            with TestClient(create_app(Settings(data_dir=Path(directory))), raise_server_exceptions=False) as client:
                with self.assertLogs('backend.main', level='ERROR'):
                    response = client.get('/api/health')
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()['error']['code'], 'dataset_unavailable')
                self.assertNotIn(directory, response.text)

    def test_database_error_and_unexpected_error_hide_details(self):
        for exception, code in ((duckdb.Error('private SQL and path'), 503), (RuntimeError('private secret'), 500)):
            with self.subTest(exception=exception), patch.object(self.db, 'stops', side_effect=exception):
                with self.assertLogs('backend.main', level='ERROR'):
                    response = self.client.get('/api/stops')
                self.assertEqual(response.status_code, code)
                self.assertNotIn('private', response.text)
        # Errors did not leak request capacity or database state.
        self.get('/api/health')

    def test_configured_result_limit(self):
        with TestClient(create_app(Settings(max_query_rows=2))) as client:
            self.assertEqual(client.get('/api/stops', params={'limit': 3}).status_code, 422)
            self.assertEqual(client.get('/api/stops', params={'limit': 2}).status_code, 200)

    def test_malformed_export_is_safe_503(self):
        with patch.object(self.app.state.resources.exports, 'weekly', side_effect=ValueError('private export path')):
            with self.assertLogs('backend.main', level='ERROR'):
                response = self.client.get('/api/analytics/weekly')
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()['error']['code'], 'dataset_unavailable')
            self.assertNotIn('private', response.text)
        self.get('/api/health')

    def test_swagger_and_openapi_document_all_endpoints(self):
        schema = self.get('/openapi.json')
        self.assertEqual(set(schema['paths']), API_PATHS)
        for path in API_PATHS:
            self.assertIn('get', schema['paths'][path])
            self.assertIn('schema', schema['paths'][path]['get']['responses']['200']['content']['application/json'])
        docs = self.client.get('/docs')
        self.assertEqual(docs.status_code, 200)
        self.assertIn('SwaggerUIBundle', docs.text)
        self.assertIn('/openapi.json', docs.text)
        self.assertEqual(self.client.get('/redoc').status_code, 200)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        for item in cls.phase1['files']:
            for directory in (PROJECT_ROOT / 'CrowdRoute_Delhi_Model', cls.db.settings.data_dir):
                if sha256(directory / item['name']) != item['sha256']:
                    raise AssertionError(f'Asset changed: {directory / item["name"]}')
        if list(cls.db.settings.runtime_dir.iterdir()):
            raise AssertionError('Database spill directories were not cleaned')


if __name__ == '__main__':
    unittest.main()
