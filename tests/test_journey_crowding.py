"""Real-data end-to-end tests; no synthetic routes, journeys or model estimates."""
from collections import Counter
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.config import PROJECT_ROOT, Settings
from backend.crowding_schemas import RankingPolicy
from backend.database import _rows
from backend.journey_planner import IST, JourneyPlanner
from backend.journey_ranking import rank_journeys
from backend.journey_schemas import Journey
from backend.main import create_app
from scripts.inspect_database import sha256


def clock(seconds):
    return (datetime.combine(date(2026,11,20), time()) + timedelta(seconds=seconds % 86400)).time().isoformat()


class JourneyCrowdingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime = TemporaryDirectory()
        cls.addClassCleanup(runtime.cleanup)
        settings = Settings(runtime_dir=Path(runtime.name))
        discovery = json.loads((PROJECT_ROOT/'docs/phase5-crowding-cases.json').read_text())
        cls.cases = discovery['cases']
        cls.old_cases = json.loads((PROJECT_ROOT/'docs/phase4-journey-cases.json').read_text())
        cls.app = create_app(settings)
        cls.db = cls.app.state.resources.db
        cls.client = TestClient(cls.app, raise_server_exceptions=False)
        cls.cache = {}
        for name, expected in discovery['inputs_sha256'].items():
            if sha256(cls.db.settings.data_dir/name) != expected:
                raise AssertionError('Inputs changed; rediscover actual crowding test witnesses')

    def request(self, params):
        key = tuple(sorted(params.items()))
        if key not in self.cache:
            response = self.client.get('/api/journeys',params=params)
            self.assertEqual(response.status_code,200,response.text)
            self.cache[key] = response.json()
        return self.cache[key]

    def point(self, label, preference='balanced'):
        case = self.cases[label]
        return self.request({'source_stop_id':case['from_stop_id'],'destination_stop_id':case['to_stop_id'],
            'travel_date':case['travel_date'],'departure_time':clock(case['departure_seconds']),
            'max_wait_minutes':0,'max_transfers':0,'limit':20,'preference':preference})

    def comparison(self, preference='balanced', limit=20):
        case = self.cases['Low']
        return self.request({'source_stop_id':case['from_stop_id'],'destination_stop_id':case['to_stop_id'],
            'travel_date':case['travel_date'],'departure_time':clock(case['departure_seconds']-15*60),
            'max_wait_minutes':30,'max_transfers':0,'limit':limit,'preference':preference})

    def all_journeys(self, response):
        return list({j['journey_id']:j for j in
            response['journeys']+[r['journey'] for r in response['recommendations']]}.values())

    def target(self, response, case):
        return next(j for j in self.all_journeys(response) if len(j['legs'])==1
            and j['legs'][0]['trip_id']==case['trip_id'])

    def long_case(self):
        case = self.cases['slot_crossing']
        return self.request({'source_stop_id':case['from_stop_id'],'destination_stop_id':case['to_stop_id'],
            'travel_date':case['travel_date'],'departure_time':clock(case['boarding_departure_seconds']),
            'max_wait_minutes':0,'max_transfers':0,'limit':20})

    def assert_exact_profiles(self, response):
        with self.db.connection() as con:
            for journey in self.all_journeys(response):
                for leg in journey['legs']:
                    for segment in leg['segments']:
                        evidence = segment['crowding']
                        local = datetime.fromisoformat(segment['departure_at']).astimezone(IST)
                        expected_key = (leg['route_id'],leg['pattern_id'],segment['from_stop_sequence'],
                            segment['from_stop_id'],segment['to_stop_id'],local.weekday()>=5,
                            local.hour*2+local.minute//30)
                        rows = _rows(con, '''SELECT * FROM crowding_model WHERE route_id=? AND pattern_id=?
                            AND stop_sequence=? AND from_stop_id=? AND to_stop_id=? AND is_weekend=? AND time_slot=?''',list(expected_key))
                        self.assertEqual(tuple(evidence[k] for k in ('route_id','pattern_id','stop_sequence',
                            'from_stop_id','to_stop_id','is_weekend','time_slot')),expected_key)
                        self.assertEqual(evidence['profile_found'], bool(rows))
                        self.assertEqual(datetime.fromisoformat(evidence['scheduled_departure_at']),local)
                        if rows:
                            row=rows[0]
                            self.assertEqual(evidence['crowding_level'],row['crowding_level'])
                            self.assertEqual(evidence['exported_predicted_load'],row['predicted_load'])
                            for field in ('baseline_prediction','data_support','prediction_source','sample_journeys',
                                          'observed_days','reference_samples','lower_threshold','upper_threshold','peak_load_p90'):
                                self.assertEqual(evidence[field],row[field])
                            reliable=(row['crowding_level'] in ('Low','Moderate','High')
                                and row['data_support'] in ('Medium','High') and row['sample_journeys']>=5
                                and row['observed_days']>=3 and row['reference_samples']>=20)
                            self.assertEqual(evidence['reliable_classification'],reliable)
                            self.assertEqual(evidence['predicted_load'],row['predicted_load'] if reliable else None)
                        else:
                            self.assertEqual(evidence['crowding_level'],'Insufficient Data')
                            self.assertEqual(evidence['unavailable_reason'],'no_matching_exported_profile')
                            self.assertIsNone(evidence['predicted_load'])

    def test_all_four_actual_classifications_join_exact_keys(self):
        for label in ('Low','Moderate','High','Insufficient Data'):
            with self.subTest(label=label):
                result=self.point(label)
                journey=self.target(result,self.cases[label])
                self.assertEqual(journey['legs'][0]['segments'][0]['crowding']['crowding_level'],label)
                self.assert_exact_profiles(result)

    def test_each_segment_uses_its_actual_time_slot(self):
        result=self.long_case()
        journey=self.target(result,self.cases['slot_crossing'])
        slots=[s['crowding']['time_slot'] for s in journey['legs'][0]['segments']]
        self.assertIn(17,slots)
        self.assertIn(18,slots)
        last=journey['legs'][0]['segments'][-1]
        self.assertEqual(last['crowding']['crowding_level'],'Low')
        self.assert_exact_profiles(result)

    def test_midnight_uses_civil_weekend_not_service_weekday(self):
        start=self.old_cases['midnight']
        end=self.old_cases['previous_service_day']
        result=self.request({'source_stop_id':start['source_stop_id'],
            'destination_stop_id':end['destination_stop_id'],'travel_date':'2026-11-20',
            'departure_time':clock(start['departure_seconds']),'max_wait_minutes':0,'max_transfers':0,'limit':20})
        journey=next(j for j in self.all_journeys(result) if j['legs'][0]['trip_id']==start['trip_id'])
        segments=journey['legs'][0]['segments']
        self.assertEqual(journey['legs'][0]['service_date'],'2026-11-20')
        self.assertEqual([(s['crowding']['is_weekend'],s['crowding']['time_slot']) for s in segments],[(False,47),(True,0)])
        self.assert_exact_profiles(result)

    def test_numeric_prediction_coverage_does_not_imply_reliability(self):
        journey=self.target(self.point('Insufficient Data'),self.cases['Insufficient Data'])
        summary=journey['crowding']
        self.assertEqual(summary['prediction_coverage'],1)
        self.assertEqual(summary['duration_prediction_coverage'],1)
        self.assertEqual(summary['reliable_classification_coverage'],0)
        self.assertEqual(summary['duration_reliable_classification_coverage'],0)
        self.assertIsNone(summary['duration_weighted_relative_crowding'])
        self.assertFalse(summary['comfort_eligible'])

    def test_medium_support_insufficient_label_is_not_upgraded(self):
        label='Medium support Insufficient Data'
        journey=self.target(self.point(label),self.cases[label])
        evidence=journey['legs'][0]['segments'][0]['crowding']
        self.assertEqual(evidence['data_support'],'Medium')
        self.assertEqual(evidence['crowding_level'],'Insufficient Data')
        self.assertFalse(evidence['reliable_classification'])
        self.assertIsNone(evidence['predicted_load'])

    def test_weighted_relative_crowding_and_support_arithmetic(self):
        for journey in self.all_journeys(self.long_case()):
            segments=[s for l in journey['legs'] for s in l['segments']]
            total=sum(s['approximate_duration_seconds'] for s in segments)
            reliable=[s for s in segments if s['crowding']['reliable_classification']]
            known=sum(s['approximate_duration_seconds'] for s in reliable)
            weighted=sum(s['approximate_duration_seconds']*{'Low':0,'Moderate':0.5,'High':1}[s['crowding']['crowding_level']] for s in reliable)
            penalized=weighted+1.25*(total-known)
            summary=journey['crowding']
            self.assertAlmostEqual(summary['duration_weighted_penalized_crowding'],penalized/total)
            if known:
                self.assertAlmostEqual(summary['duration_weighted_relative_crowding'],weighted/known)
            else:
                self.assertIsNone(summary['duration_weighted_relative_crowding'])
            self.assertAlmostEqual(summary['duration_reliable_classification_coverage'],known/total)
            self.assertEqual(summary['in_vehicle_duration_seconds'],journey['in_vehicle_duration_seconds'])
            support=Counter(s['crowding']['data_support'] or 'Missing' for s in segments)
            for key,count in summary['data_support'].items():
                self.assertEqual(count,support[key])
            self.assertEqual(sum(summary['classification_counts'].values()),len(segments))

    def test_unknown_crowding_has_higher_cost_than_known_high(self):
        high=self.target(self.point('High'),self.cases['High'])
        unknown=self.target(self.point('Insufficient Data'),self.cases['Insufficient Data'])
        self.assertEqual(high['crowding']['duration_weighted_penalized_crowding'],1)
        self.assertEqual(unknown['crowding']['duration_weighted_penalized_crowding'],1.25)
        self.assertGreater(unknown['ranking']['unknown_penalized_relative_crowding'],high['ranking']['unknown_penalized_relative_crowding'])

    def test_unavailable_comfort_is_explicit_with_no_silent_fallback(self):
        case=self.old_cases['direct']
        result=self.request({'source_stop_id':case['source_stop_id'],'destination_stop_id':case['destination_stop_id'],
            'travel_date':'2026-11-20','departure_time':'06:09','max_transfers':0,'preference':'comfortable'})
        self.assertTrue(result['journeys'])
        self.assertFalse(result['preference_available'])
        self.assertIsNone(result['applied_preference'])
        self.assertIn('Unknown/Insufficient Data',result['preference_unavailable_reason'])
        self.assertEqual(result['unavailable_recommendations'][0]['preference'],'comfortable')
        for journey in result['journeys']:
            self.assertFalse(journey['crowding']['comfort_eligible'])
            self.assertIsNone(journey['crowding']['duration_weighted_relative_crowding'])
            self.assertEqual(journey['crowding']['duration_weighted_penalized_crowding'],1.25)
            self.assertGreater(journey['crowding']['data_support']['Missing'],0)

    def test_reliable_comfort_recommendation_has_sufficient_coverage(self):
        result=self.comparison('comfortable')
        self.assertTrue(result['preference_available'])
        winner=next(r['journey'] for r in result['recommendations'] if 'comfortable' in r['preferences'])
        self.assertTrue(winner['crowding']['comfort_eligible'])
        self.assertGreaterEqual(winner['crowding']['reliable_classification_coverage'],0.8)
        self.assertGreaterEqual(winner['crowding']['duration_reliable_classification_coverage'],0.8)
        self.assertEqual(result['journeys'][0]['journey_id'],winner['journey_id'])

    def test_fastest_is_minimum_total_time_in_full_bounded_pool(self):
        result=self.comparison('fastest',limit=1)
        case=self.cases['Low']
        pool=JourneyPlanner(self.db).plan(case['from_stop_id'],case['to_stop_id'],date.fromisoformat(case['travel_date']),
            time.fromisoformat(clock(case['departure_seconds']-900)),max_transfers=0,max_wait_minutes=30,
            candidate_pool_limit=80)['journeys']
        self.assertEqual(result['journeys'][0]['total_duration_seconds'],min(j['total_duration_seconds'] for j in pool))
        self.assertEqual(len(result['journeys']),1)
        self.assertGreater(result['search']['ranking_candidates_evaluated'],1)

    def test_balanced_formula_and_transparency(self):
        result=self.comparison('balanced')
        policy=result['ranking_policy']
        self.assertEqual(policy['level_scores'],{'Low':0,'Moderate':0.5,'High':1})
        self.assertEqual(policy['unknown_crowding_penalty'],1.25)
        for journey in self.all_journeys(result):
            score=journey['ranking']
            self.assertAlmostEqual(score['duration_component_minutes'],journey['total_duration_seconds']/60)
            self.assertAlmostEqual(score['crowding_penalty_component_minutes'],30*score['unknown_penalized_relative_crowding'])
            self.assertAlmostEqual(score['transfer_penalty_component_minutes'],5*journey['transfers'])
            self.assertAlmostEqual(score['balanced_score_minutes'],sum(score[k] for k in
                ('duration_component_minutes','crowding_penalty_component_minutes','transfer_penalty_component_minutes')))

    def test_actual_preferences_can_select_different_real_journeys(self):
        result=self.comparison()
        winners={name:r['journey'] for r in result['recommendations'] for name in r['preferences']}
        self.assertNotEqual(winners['fastest']['journey_id'],winners['comfortable']['journey_id'])
        self.assertGreater(winners['comfortable']['total_duration_seconds'],winners['fastest']['total_duration_seconds'])
        self.assertLess(winners['comfortable']['crowding']['duration_weighted_penalized_crowding'],
                        winners['fastest']['crowding']['duration_weighted_penalized_crowding'])

    def test_duplicate_recommendations_merge_preference_labels(self):
        original=self.target(self.point('Low'),self.cases['Low'])
        actual=Journey.model_validate(original).model_dump()
        ranked,count=rank_journeys([deepcopy(actual),deepcopy(actual)],'balanced',10)
        self.assertEqual(count,1)
        self.assertEqual(len(ranked['journeys']),1)
        self.assertEqual(len(ranked['recommendations']),1)
        self.assertEqual(set(ranked['recommendations'][0]['preferences']),{'fastest','comfortable','balanced'})
        result=self.comparison()
        ids=[r['journey']['journey_id'] for r in result['recommendations']]
        self.assertEqual(len(ids),len(set(ids)))
        labels=[name for r in result['recommendations'] for name in r['preferences']]
        self.assertEqual(len(labels),len(set(labels)))

    def test_recommendations_remain_inspectable_outside_response_limit(self):
        result=self.comparison('fastest',limit=1)
        self.assertEqual(len(result['journeys']),1)
        comfortable=next(r['journey'] for r in result['recommendations'] if 'comfortable' in r['preferences'])
        self.assertNotEqual(comfortable['journey_id'],result['journeys'][0]['journey_id'])
        self.assertTrue(comfortable['legs'][0]['segments'][0]['crowding'])

    def test_unsupported_dates_and_no_journeys_do_not_create_recommendations(self):
        case=self.cases['Low']
        result=self.request({'source_stop_id':case['from_stop_id'],'destination_stop_id':case['to_stop_id'],
            'travel_date':'2024-11-20','departure_time':'08:45','preference':'comfortable'})
        self.assertEqual(result['status'],'unsupported_date')
        self.assertEqual(result['journeys'],[])
        self.assertEqual(result['recommendations'],[])
        self.assertEqual(len(result['unavailable_recommendations']),3)

    def test_repeated_zero_duration_segment_is_not_given_fake_weight(self):
        case=self.old_cases['repeated_stops']
        result=self.request({'source_stop_id':case['source_stop_id'],'destination_stop_id':case['destination_stop_id'],
            'travel_date':'2026-11-20','departure_time':clock(case['departure_seconds']),
            'max_wait_minutes':0,'max_transfers':0,'limit':20})
        journey=next(j for j in self.all_journeys(result) if j['legs'][0]['trip_id']==case['trip_id'])
        segments=journey['legs'][0]['segments']
        self.assertEqual(len(segments),3)
        self.assertEqual(segments[1]['approximate_duration_seconds'],0)
        self.assertEqual(segments[1]['crowding']['stop_sequence'],23)
        self.assertEqual(journey['crowding']['in_vehicle_duration_seconds'],sum(s['approximate_duration_seconds'] for s in segments))
        self.assert_exact_profiles(result)

    def test_preference_validation_and_openapi(self):
        case=self.cases['Low']
        params={'source_stop_id':case['from_stop_id'],'destination_stop_id':case['to_stop_id'],
                'travel_date':case['travel_date'],'departure_time':'08:45','preference':'empty-bus'}
        self.assertEqual(self.client.get('/api/journeys',params=params).status_code,422)
        schema=self.client.get('/openapi.json').json()
        self.assertEqual(schema['info']['version'],'0.5.0')
        self.assertIn('/api/journeys', schema['paths'])
        self.assertIn('preference',[p['name'] for p in schema['paths']['/api/journeys']['get']['parameters']])

    def test_ranking_pool_truncation_is_disclosed(self):
        case=self.cases['Low']
        with patch('backend.journey_ranking.RankingPolicy',return_value=RankingPolicy(candidate_pool_limit=2)):
            response=self.client.get('/api/journeys',params={'source_stop_id':case['from_stop_id'],
                'destination_stop_id':case['to_stop_id'],'travel_date':case['travel_date'],
                'departure_time':clock(case['departure_seconds']-900),'max_transfers':0})
        self.assertEqual(response.status_code,200,response.text)
        result=response.json()
        self.assertTrue(result['search']['ranking_pool_truncated'])
        self.assertLessEqual(result['search']['ranking_candidates_evaluated'],2)
        self.assertTrue(any('ranking pool limit' in w for w in result['warnings']))

    def test_transfer_ranking_keeps_waits_out_of_crowding_duration(self):
        case=self.old_cases['transfer_only']
        result=self.request({'source_stop_id':case['source_stop_id'],'destination_stop_id':case['destination_stop_id'],
            'travel_date':'2026-11-20','departure_time':'06:09','limit':3})
        self.assertTrue(all(j['transfers']==1 for j in result['journeys']))
        for journey in self.all_journeys(result):
            self.assertEqual(journey['ranking']['transfer_penalty_component_minutes'],5)
            self.assertEqual(journey['crowding']['in_vehicle_duration_seconds'],
                journey['total_duration_seconds']-journey['initial_wait_seconds']-journey['transfer_wait_seconds'])
        self.assert_exact_profiles(result)

    def test_json_scores_are_finite_and_do_not_claim_occupancy(self):
        result=self.comparison()
        def walk(value):
            if isinstance(value,dict):
                self.assertFalse({'occupancy_percentage','seat_availability','occupancy_percent'} & value.keys())
                for item in value.values(): walk(item)
            elif isinstance(value,list):
                for item in value: walk(item)
            elif isinstance(value,float): self.assertTrue(math.isfinite(value))
        walk(result)
        self.assertIn('not actual bus occupancy',result['notice'])

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        report=json.loads((PROJECT_ROOT/'docs/phase1-verification.json').read_text())
        for item in report['files']:
            for directory in (PROJECT_ROOT/'CrowdRoute_Delhi_Model',cls.db.settings.data_dir):
                if sha256(directory/item['name'])!=item['sha256']:
                    raise AssertionError(f'Original export changed: {item["name"]}')
        if list(cls.db.settings.runtime_dir.iterdir()):
            raise AssertionError('Database spill directories leaked')


if __name__=='__main__':
    unittest.main()
