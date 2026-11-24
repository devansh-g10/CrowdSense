"""Schedule-engine integration tests using discovered actual trip witnesses."""
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from backend.config import PROJECT_ROOT, Settings
from backend.database import Database, _rows
from backend.journey_planner import (IST, InvalidJourneyRequest, JourneyPlanner,
                                     SearchBounds, UnknownStopError)
from backend.main import create_app
from scripts.discover_journey_cases import discover_cases
from scripts.inspect_database import sha256

TRAVEL_DATE = date(2026, 11, 20)


def clock(seconds):
    return (datetime.combine(TRAVEL_DATE, time()) + timedelta(seconds=seconds % 86400)).time()


class JourneyIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime = TemporaryDirectory()
        cls.addClassCleanup(runtime.cleanup)
        settings = Settings(runtime_dir=Path(runtime.name))
        cls.db = Database(settings)
        cls.planner = JourneyPlanner(cls.db)
        cls.cases = discover_cases(cls.db)
        cls.client = TestClient(create_app(settings), raise_server_exceptions=False)
        cls.results = {}

    def plan(self, case_name='direct', *, travel_date=TRAVEL_DATE, seconds=None, **kwargs):
        case = self.cases[case_name]
        seconds = case['departure_seconds'] - 60 if seconds is None else seconds
        key = (case_name, travel_date, seconds, tuple(sorted(kwargs.items())))
        if key not in self.results:
            self.results[key] = self.planner.plan(case['source_stop_id'], case['destination_stop_id'],
                travel_date, clock(seconds), **kwargs)
        return self.results[key]

    def assert_real_journeys(self, response):
        search = response['search']
        with self.db.connection() as con:
            for journey in response['journeys']:
                self.assertTrue(journey['departure_at'].utcoffset() == timedelta(hours=5, minutes=30))
                self.assertLessEqual(journey['total_duration_seconds'], search['max_journey_minutes'] * 60)
                self.assertLessEqual(journey['initial_wait_seconds'], search['max_wait_minutes'] * 60)
                self.assertGreaterEqual(journey['initial_wait_seconds'], 0)
                self.assertEqual(journey['total_duration_seconds'], int((journey['estimated_arrival_at'] - response['requested_departure_at']).total_seconds()))
                self.assertEqual(journey['travel_duration_seconds'], journey['in_vehicle_duration_seconds'] + journey['transfer_wait_seconds'])
                self.assertEqual(journey['legs'][0]['stops'][0]['stop_id'], response['source_stop_id'])
                self.assertEqual(journey['legs'][-1]['stops'][-1]['stop_id'], response['destination_stop_id'])
                if journey['transfers']:
                    first, second = journey['legs']
                    self.assertEqual(first['stops'][-1]['stop_id'], second['stops'][0]['stop_id'])
                    self.assertNotEqual((first['trip_id'], first['service_date']), (second['trip_id'], second['service_date']))
                    self.assertGreaterEqual(journey['transfer_wait_seconds'], search['min_transfer_minutes'] * 60)
                    self.assertLessEqual(journey['transfer_wait_seconds'], search['max_wait_minutes'] * 60)
                for leg in journey['legs']:
                    self.assertLess(leg['boarding_stop_sequence'], leg['alighting_stop_sequence'])
                    expected = _rows(con, '''SELECT stop_id,stop_sequence,departure_seconds FROM trip_schedule
                        WHERE trip_id=? AND stop_sequence BETWEEN ? AND ? ORDER BY stop_sequence''',
                        [leg['trip_id'],leg['boarding_stop_sequence'],leg['alighting_stop_sequence']])
                    self.assertEqual([(s['stop_id'],s['stop_sequence'],s['gtfs_departure_seconds']) for s in leg['stops']],
                                     [(s['stop_id'],s['stop_sequence'],s['departure_seconds']) for s in expected])
                    self.assertEqual(leg['intermediate_stops'], leg['stops'][1:-1])
                    self.assertEqual(len(leg['segments']), len(leg['stops']) - 1)
                    self.assertEqual(sum(s['approximate_duration_seconds'] for s in leg['segments']), leg['approximate_duration_seconds'])
                    calendar = _rows(con, 'SELECT * FROM calendar WHERE service_id=?', [leg['service_id']])[0]
                    self.assertLessEqual(datetime.strptime(calendar['start_date'], '%Y%m%d').date(), leg['service_date'])
                    self.assertLessEqual(leg['service_date'], datetime.strptime(calendar['end_date'], '%Y%m%d').date())
                    self.assertEqual(calendar[('monday','tuesday','wednesday','thursday','friday','saturday','sunday')[leg['service_date'].weekday()]], '1')
                    for stop in leg['stops']:
                        self.assertEqual(stop['scheduled_departure_at'], datetime.combine(leg['service_date'], time(), IST) + timedelta(seconds=stop['gtfs_departure_seconds']))

    def test_direct_uses_discovered_real_trip(self):
        result = self.plan(max_transfers=0, limit=20)
        self.assertEqual(result['status'], 'ok')
        self.assertIn(self.cases['direct']['trip_id'], [j['legs'][0]['trip_id'] for j in result['journeys']])
        self.assertTrue(all(j['transfers'] == 0 for j in result['journeys']))
        self.assert_real_journeys(result)

    def test_transfer_only_pair_has_no_direct_but_feasible_connection(self):
        direct = self.plan('transfer_only', max_transfers=0)
        self.assertEqual(direct['journeys'], [])
        self.assertEqual(direct['status'], 'no_journeys')
        result = self.plan('transfer_only', limit=20)
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(all(j['transfers'] == 1 for j in result['journeys']))
        self.assert_real_journeys(result)

    def test_initial_wait_zero_excludes_future_departure(self):
        result = self.plan(max_transfers=0, max_wait_minutes=0)
        self.assertEqual(result['status'], 'no_journeys')
        exact = self.plan(seconds=self.cases['direct']['departure_seconds'], max_wait_minutes=0, max_transfers=0)
        self.assertEqual(exact['status'], 'ok')
        self.assertTrue(all(j['initial_wait_seconds'] == 0 for j in exact['journeys']))

    def test_maximum_transfer_wait_and_minimum_buffer(self):
        result = self.plan('transfer_only', max_wait_minutes=5, limit=20)
        self.assert_real_journeys(result)
        witness = self.cases['transfer_only']
        self.assertGreater(witness['second_departure_seconds'] - witness['first_arrival_seconds'], 300)
        self.assertFalse(any([l['trip_id'] for l in j['legs']] == [witness['first_trip'], witness['second_trip']]
                             for j in result['journeys']))
        result = self.plan('transfer_only', min_transfer_minutes=10, limit=20)
        self.assert_real_journeys(result)

    def test_duration_horizon_is_enforced(self):
        result = self.plan(max_journey_minutes=1, max_transfers=0)
        self.assertEqual(result['journeys'], [])
        self.assertEqual(result['status'], 'no_journeys')

    def test_ordered_pair_without_direct_route_does_not_invent_one(self):
        result = self.plan('no_direct', max_transfers=0)
        self.assertEqual(result['status'], 'no_journeys')
        self.assertEqual(result['journeys'], [])

    def test_midnight_arrival_uses_next_civil_date(self):
        case = self.cases['midnight']
        result = self.plan('midnight', seconds=case['departure_seconds'], max_wait_minutes=0, max_transfers=0)
        journey = next(j for j in result['journeys'] if j['legs'][0]['trip_id'] == case['trip_id'])
        self.assertEqual(journey['departure_at'].date(), TRAVEL_DATE)
        self.assertEqual(journey['estimated_arrival_at'].date(), TRAVEL_DATE + timedelta(days=1))
        self.assertGreaterEqual(journey['legs'][0]['stops'][-1]['gtfs_departure_seconds'], 86400)
        self.assert_real_journeys(result)

    def test_after_midnight_boarding_looks_back_to_service_date(self):
        case = self.cases['previous_service_day']
        result = self.plan('previous_service_day', travel_date=TRAVEL_DATE + timedelta(days=1),
            seconds=case['departure_seconds'], max_wait_minutes=0, max_transfers=0)
        leg = next(j['legs'][0] for j in result['journeys'] if j['legs'][0]['trip_id'] == case['trip_id'])
        self.assertEqual(leg['service_date'], TRAVEL_DATE)
        self.assertEqual(leg['departure_at'].date(), TRAVEL_DATE + timedelta(days=1))
        self.assert_real_journeys(result)

    def test_transfer_can_cross_service_dates(self):
        result = self.plan('cross_service_day_transfer', limit=20)
        self.assertEqual(result['status'], 'ok')
        self.assertTrue(any(j['transfers'] == 1 and j['legs'][0]['service_date'] != j['legs'][1]['service_date'] for j in result['journeys']))
        self.assert_real_journeys(result)

    def test_repeated_stops_and_equal_times_remain_ordered(self):
        case = self.cases['repeated_stops']
        result = self.plan('repeated_stops', seconds=case['departure_seconds'], max_wait_minutes=0, max_transfers=0, limit=20)
        leg = next(j['legs'][0] for j in result['journeys'] if j['legs'][0]['trip_id'] == case['trip_id'])
        occurrences = [s['stop_sequence'] for s in leg['stops'] if s['stop_id'] == case['repeated_stop_id']]
        self.assertEqual(occurrences, [case['first_occurrence'], case['last_occurrence']])
        self.assertTrue(any(segment['approximate_duration_seconds'] == 0 for segment in leg['segments']))
        self.assert_real_journeys(result)

    def test_boarding_repeated_stop_uses_each_sequence_occurrence(self):
        case = self.cases['repeated_stops']
        with self.db.connection() as con:
            seconds = _rows(con, 'SELECT departure_seconds FROM trip_schedule WHERE trip_id=? AND stop_sequence=?',
                            [case['trip_id'], case['first_occurrence']])[0]['departure_seconds']
        result = self.planner.plan(case['repeated_stop_id'], case['destination_stop_id'], TRAVEL_DATE,
            clock(seconds), max_wait_minutes=0, max_transfers=0, limit=20)
        sequences = [j['legs'][0]['boarding_stop_sequence'] for j in result['journeys'] if j['legs'][0]['trip_id'] == case['trip_id']]
        self.assertEqual(sequences, [case['first_occurrence'], case['last_occurrence']])
        self.assert_real_journeys(result)

    def test_calendar_limits_and_previous_day_validity(self):
        for day in (date(2024, 11, 20), date(2040, 1, 3)):
            result = self.plan(travel_date=day, max_transfers=0)
            self.assertEqual(result['status'], 'unsupported_date')
            self.assertEqual(result['journeys'], [])
        carry = self.cases['previous_service_day']
        result = self.plan('previous_service_day', travel_date=date(2040, 1, 2), seconds=carry['departure_seconds'],
                           max_wait_minutes=0, max_transfers=0)
        self.assertTrue(any(j['legs'][0]['service_date'] == date(2040, 1, 1) for j in result['journeys']))
        result = self.plan('previous_service_day', travel_date=date(2025, 1, 1), seconds=carry['departure_seconds'],
                           max_wait_minutes=0, max_transfers=0)
        self.assertTrue(all(l['service_date'] >= date(2025, 1, 1) for j in result['journeys'] for l in j['legs']))

    def test_exceptions_absence_and_approximation_are_explicit(self):
        result = self.plan(max_transfers=0)
        self.assertFalse(result['calendar']['exceptions_available'])
        self.assertEqual(self.cases['calendar_exception_files'], [])
        self.assertTrue(any('exception' in warning for warning in result['warnings']))
        self.assertTrue(any('approximate' in warning for warning in result['warnings']))
        self.assertEqual(self.cases['schedule_order_checks']['backwards_events'], 0)

    def test_calendar_coverage_uses_initial_wait_not_entire_journey_horizon(self):
        # A six-hour horizon reaches Jan 1; a 30-minute boarding wait does not.
        result = self.plan(travel_date=date(2024,12,31), seconds=18*3600, max_transfers=0)
        self.assertEqual(result['status'], 'unsupported_date')
        # A civil date before the calendar can still wait across midnight into coverage.
        result = self.plan(travel_date=date(2024,12,31), seconds=23*3600+50*60, max_transfers=0)
        self.assertTrue(result['calendar']['date_supported'])
        # The last service day's 24+ hour spill cannot cover the following afternoon.
        result = self.plan(travel_date=date(2040,1,2), seconds=12*3600, max_transfers=0)
        self.assertEqual(result['status'], 'unsupported_date')

    def test_limits_are_bounded_and_truncation_is_disclosed(self):
        case = self.cases['direct']
        planner = JourneyPlanner(self.db, SearchBounds(initial_boardings=1, destination_events=1,
            transfer_events=1, candidates_per_kind=1, stops_per_leg=1))
        result = planner.plan(case['source_stop_id'],case['destination_stop_id'],TRAVEL_DATE,
                              clock(case['departure_seconds'] - 60))
        self.assertTrue(result['search']['search_truncated'])
        self.assertLessEqual(result['search']['initial_boardings_examined'], 1)
        self.assertLessEqual(result['search']['destination_events_examined'], 1)
        self.assertEqual(result['journeys'], [])
        self.assertEqual(result['status'], 'search_incomplete')

    def test_result_order_and_limit(self):
        result = self.plan(limit=2)
        self.assertLessEqual(len(result['journeys']), 2)
        arrivals = [j['estimated_arrival_at'] for j in result['journeys']]
        self.assertEqual(arrivals, sorted(arrivals))

    def test_api_valid_journey_and_schema(self):
        case = self.cases['transfer_only']
        response = self.client.get('/api/journeys', params={'source_stop_id': case['source_stop_id'],
            'destination_stop_id': case['destination_stop_id'], 'travel_date': TRAVEL_DATE.isoformat(),
            'departure_time': clock(case['departure_seconds'] - 60).isoformat(), 'limit': 2})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['timezone'], 'Asia/Kolkata')
        self.assertTrue(all(j['duration_is_approximate'] for j in data['journeys']))
        self.assertTrue(all(j['arrival_time_basis'] == 'alighting_stop_departure_proxy' for j in data['journeys']))
        self.assertIn('/api/journeys', self.client.get('/openapi.json').json()['paths'])

    def test_api_invalid_inputs_and_unknown_stops(self):
        case = self.cases['direct']
        params = {'source_stop_id':case['source_stop_id'],'destination_stop_id':case['destination_stop_id'],
                  'travel_date':'2026-11-20','departure_time':'06:09'}
        invalid = [{}, {**params,'destination_stop_id':params['source_stop_id']},
            {**params,'departure_time':'25:00'}, {**params,'departure_time':'06:09+00:00'},
            {**params,'travel_date':'invalid'}, {**params,'max_wait_minutes':-1},
            {**params,'max_wait_minutes':121}, {**params,'max_transfers':2},
            {**params,'min_transfer_minutes':0}, {**params,'max_journey_minutes':721},
            {**params,'limit':21}]
        for values in invalid:
            with self.subTest(values=values):
                self.assertEqual(self.client.get('/api/journeys',params=values).status_code,422)
        missing = self.client.get('/api/journeys',params={**params,'source_stop_id':"' OR 1=1 --"})
        self.assertEqual(missing.status_code,404)
        unsupported = self.client.get('/api/journeys',params={**params,'travel_date':'2024-11-20'})
        self.assertEqual(unsupported.status_code,200)
        self.assertEqual(unsupported.json()['status'],'unsupported_date')

    def test_programmatic_validation_and_unknown_stop(self):
        case = self.cases['direct']
        args = (case['source_stop_id'],case['destination_stop_id'],TRAVEL_DATE,time(6,9))
        with self.assertRaises(InvalidJourneyRequest):
            self.planner.plan(*args, max_transfers=2)
        with self.assertRaises(UnknownStopError):
            self.planner.plan('__missing__',case['destination_stop_id'],TRAVEL_DATE,time(6,9))

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        report = json.loads((PROJECT_ROOT / 'docs/phase1-verification.json').read_text())
        for item in report['files']:
            for directory in (PROJECT_ROOT/'CrowdRoute_Delhi_Model',cls.db.settings.data_dir):
                if sha256(directory/item['name']) != item['sha256']:
                    raise AssertionError(f'Model asset changed: {item["name"]}')
        if list(cls.db.settings.runtime_dir.iterdir()):
            raise AssertionError('Planning sessions leaked spill directories')


if __name__ == '__main__':
    unittest.main()
