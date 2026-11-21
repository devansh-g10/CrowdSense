"""Verify the running local server with actual dataset keys.

Start Uvicorn separately, then run: python -m scripts.verify_api
This performs GET/OPTIONS requests only and writes a local verification report.
"""
import json
from time import perf_counter
from urllib.request import Request, urlopen

from backend.config import PROJECT_ROOT
from backend.database import Database, _rows


def main():
    base = 'http://127.0.0.1:8000'
    db = Database()
    with db.connection() as con:
        sample = _rows(con, '''SELECT route_id, pattern_id, time_slot FROM crowding_model
            WHERE crowding_level = 'Insufficient Data' AND is_weekend = false
            ORDER BY route_id, pattern_id, time_slot LIMIT 1''')[0]
    route = sample['route_id']
    pattern = sample['pattern_id']
    paths = ['/api/health', '/api/model-info', '/api/stops?search=Rohini&limit=3',
        '/api/routes?limit=3', f'/api/routes/{route}',
        f'/api/routes/{route}/segments?pattern_id={pattern}&limit=3',
        f'/api/crowding?route_id={route}&pattern_id={pattern}&is_weekend=false&time_slot={sample["time_slot"]}&limit=3',
        '/api/analytics/overview', '/api/analytics/routes?limit=3',
        '/api/analytics/heatmap?limit=3', '/api/analytics/weekly',
        '/api/analytics/peak-hours', '/api/analytics/model-performance',
        '/docs', '/openapi.json']
    checks = []
    for path in paths:
        start = perf_counter()
        with urlopen(base + path, timeout=30) as response:
            raw = response.read()
            content_type = response.headers['content-type']
            assert response.status == 200
        item = {'path': path, 'status': 200, 'content_type': content_type,
                'elapsed_ms': round((perf_counter() - start) * 1000, 2)}
        if path == '/docs':
            assert b'SwaggerUIBundle' in raw and b'/openapi.json' in raw
        else:
            data = json.loads(raw)
            if path == '/openapi.json':
                assert len(data['paths']) >= 13  # Phase 4 adds /api/journeys.
                assert all('get' in methods for methods in data['paths'].values())
                item['documented_api_paths'] = len(data['paths'])
            if path.startswith('/api/crowding'):
                assert data['items']
                for row in data['items']:
                    if row['crowding_level'] == 'Insufficient Data':
                        assert row['predicted_load'] is None and not row['available']
                item['prediction_status'] = data['status']
        checks.append(item)
    preflight = Request(base + '/api/stops', method='OPTIONS',
        headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'GET'})
    with urlopen(preflight, timeout=30) as response:
        assert response.status == 200
        assert response.headers['access-control-allow-origin'] == 'http://localhost:5173'
    report = {'base_url': base, 'checks': checks, 'local_cors_preflight': 'passed',
              'summary': 'All 13 API endpoints, Swagger HTML and OpenAPI JSON passed over live HTTP.'}
    (PROJECT_ROOT / 'docs/phase3-api-verification.json').write_text(
        json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['summary'])
    print('Local CORS preflight passed.')


if __name__ == '__main__':
    main()
