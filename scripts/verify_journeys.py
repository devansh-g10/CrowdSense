"""Live HTTP checks using the actual pairs in the Phase 4 discovery report."""
from datetime import date, datetime, time, timedelta
import json
from time import perf_counter
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.config import PROJECT_ROOT


def main():
    cases_path = PROJECT_ROOT / 'docs/phase4-journey-cases.json'
    if not cases_path.is_file():
        raise FileNotFoundError('Run python -m scripts.discover_journey_cases first')
    cases = json.loads(cases_path.read_text())
    checks = []
    for kind in ('direct', 'transfer_only', 'midnight', 'previous_service_day',
                 'cross_service_day_transfer', 'repeated_stops', 'no_direct', 'unsupported_date'):
        case = cases['direct' if kind == 'unsupported_date' else kind]
        day = date.fromisoformat(cases['reference_travel_date'])
        exact = kind in ('midnight', 'previous_service_day', 'repeated_stops')
        seconds = case['departure_seconds'] - (0 if exact else 60)
        if kind == 'previous_service_day':
            day += timedelta(days=1)
        if kind == 'unsupported_date':
            day = date(2024, 11, 20)
        clock = (datetime.combine(day, time()) + timedelta(seconds=seconds % 86400)).time()
        params = {'source_stop_id': case['source_stop_id'], 'destination_stop_id': case['destination_stop_id'],
                  'travel_date': day.isoformat(), 'departure_time': clock.isoformat(), 'limit': 3}
        if kind not in ('transfer_only', 'cross_service_day_transfer'):
            params['max_transfers'] = 0
        if exact:
            params['max_wait_minutes'] = 0
        start = perf_counter()
        with urlopen('http://127.0.0.1:8000/api/journeys?' + urlencode(params), timeout=30) as response:
            assert response.status == 200
            data = json.load(response)
        expected = 'no_journeys' if kind == 'no_direct' else 'unsupported_date' if kind == 'unsupported_date' else 'ok'
        assert data['status'] == expected, data
        if expected == 'ok':
            assert data['journeys']
            assert all(j['duration_is_approximate'] for j in data['journeys'])
            assert all(j['departure_at'].endswith('+05:30') for j in data['journeys'])
        entry = {'case': kind, 'parameters': params, 'http_status': 200,
                 'planner_status': data['status'], 'journeys_returned': len(data['journeys']),
                 'search_truncated': data['search']['search_truncated'],
                 'elapsed_ms': round((perf_counter() - start) * 1000, 2)}
        if data['journeys']:
            journey = data['journeys'][0]
            entry['first_journey'] = {key: journey[key] for key in (
                'transfers', 'departure_at', 'estimated_arrival_at', 'initial_wait_seconds',
                'transfer_wait_seconds', 'travel_duration_seconds', 'duration_is_approximate')}
            entry['first_journey']['trip_ids'] = [leg['trip_id'] for leg in journey['legs']]
            entry['first_journey']['service_dates'] = [leg['service_date'] for leg in journey['legs']]
        checks.append(entry)
    for stop, departure, expected in (('__missing__', '06:09', 404), (cases['direct']['source_stop_id'], '25:00', 422)):
        params = {'source_stop_id': stop, 'destination_stop_id': cases['direct']['destination_stop_id'],
                  'travel_date': cases['reference_travel_date'], 'departure_time': departure}
        try:
            urlopen('http://127.0.0.1:8000/api/journeys?' + urlencode(params), timeout=30)
            raise AssertionError('Expected request error')
        except HTTPError as error:
            assert error.code == expected
            checks.append({'case': 'unknown_stop' if expected == 404 else 'invalid_time', 'http_status': error.code})
    for day, clock, supported in (('2024-12-31', '18:00', False),
                                  ('2024-12-31', '23:50', True), ('2040-01-02', '12:00', False)):
        params = {'source_stop_id': cases['direct']['source_stop_id'],
                  'destination_stop_id': cases['direct']['destination_stop_id'],
                  'travel_date': day, 'departure_time': clock, 'max_transfers': 0}
        with urlopen('http://127.0.0.1:8000/api/journeys?' + urlencode(params), timeout=30) as response:
            data = json.load(response)
        assert data['calendar']['date_supported'] == supported
        if not supported:
            assert data['status'] == 'unsupported_date'
        checks.append({'case': 'calendar_window_boundary', 'parameters': params,
                       'http_status': 200, 'date_supported': supported, 'planner_status': data['status']})
    with urlopen('http://127.0.0.1:8000/openapi.json', timeout=30) as response:
        schema = json.load(response)
    assert tuple(map(int, schema['info']['version'].split('.'))) >= (0, 4, 0)
    assert '/api/journeys' in schema['paths']
    with urlopen('http://127.0.0.1:8000/docs', timeout=30) as response:
        assert response.status == 200 and b'SwaggerUIBundle' in response.read()
    report = {'base_url': 'http://127.0.0.1:8000', 'api_version': schema['info']['version'],
              'documented_api_paths': len(schema['paths']), 'swagger': 'passed', 'checks': checks,
              'summary': 'Eight real-data journey scenarios, two invalid requests and three calendar-window boundaries passed over live HTTP.'}
    (PROJECT_ROOT / 'docs/phase4-journey-verification.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['summary'])
    print('Swagger and the journey OpenAPI contract passed.')


if __name__ == '__main__':
    main()
