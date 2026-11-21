"""Live end-to-end checks using the discovered actual Phase 4/5 data."""
from datetime import date, datetime, time, timedelta
import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.config import PROJECT_ROOT


def clock(seconds):
    return (datetime.combine(date(2026,11,20),time())+timedelta(seconds=seconds%86400)).time().isoformat()


def main():
    cases=json.loads((PROJECT_ROOT/'docs/phase5-crowding-cases.json').read_text())['cases']
    old=json.loads((PROJECT_ROOT/'docs/phase4-journey-cases.json').read_text())
    checks=[]
    def request(name,params):
        with urlopen('http://127.0.0.1:8000/api/journeys?'+urlencode(params),timeout=60) as response:
            assert response.status==200
            result=json.load(response)
        checks.append({'case':name,'parameters':params,'http_status':200,'planner_status':result['status'],
            'preference_available':result['preference_available'],
            'ranking_candidates_evaluated':result['search']['ranking_candidates_evaluated'],
            'recommendations':[{'preferences':r['preferences'],'journey_id':r['journey']['journey_id'],
                'trip_ids':[leg['trip_id'] for leg in r['journey']['legs']],
                'total_duration_seconds':r['journey']['total_duration_seconds'],
                'crowding':r['journey']['crowding'],'ranking':r['journey']['ranking']} for r in result['recommendations']],
            'unavailable_recommendations':result['unavailable_recommendations']})
        return result
    for label in ('Low','Moderate','High','Insufficient Data','Medium support Insufficient Data'):
        case=cases[label]
        data=request(label,{'source_stop_id':case['from_stop_id'],'destination_stop_id':case['to_stop_id'],
            'travel_date':case['travel_date'],'departure_time':clock(case['departure_seconds']),
            'max_wait_minutes':0,'max_transfers':0,'limit':20})
        target=next(j for j in data['journeys'] if j['legs'][0]['trip_id']==case['trip_id'])
        evidence=target['legs'][0]['segments'][0]['crowding']
        assert evidence['crowding_level']==case['crowding_level']
        assert evidence['exported_predicted_load']==case['predicted_load']
        if case['crowding_level']=='Insufficient Data':
            assert evidence['predicted_load'] is None and not evidence['reliable_classification']
    low=cases['Low']
    choices={}
    for preference in ('fastest','comfortable','balanced'):
        choices[preference]=request('preference_'+preference,{'source_stop_id':low['from_stop_id'],
            'destination_stop_id':low['to_stop_id'],'travel_date':low['travel_date'],
            'departure_time':clock(low['departure_seconds']-900),'max_wait_minutes':30,
            'max_transfers':0,'limit':1,'preference':preference})
        assert choices[preference]['preference_available']
        assert len(choices[preference]['journeys'])==1
    winners={name:r['journey_id'] for r in checks[-1]['recommendations'] for name in r['preferences']}
    assert winners['fastest']!=winners['comfortable']
    assert len(winners.values())>len(set(winners.values()))  # Shared winners merge preference labels.
    direct=old['direct']
    unavailable=request('unavailable_comfort',{'source_stop_id':direct['source_stop_id'],
        'destination_stop_id':direct['destination_stop_id'],'travel_date':'2026-11-20',
        'departure_time':'06:09','max_transfers':0,'preference':'comfortable'})
    assert unavailable['journeys'] and not unavailable['preference_available']
    assert unavailable['applied_preference'] is None and unavailable['preference_unavailable_reason']
    midnight=old['midnight']
    carry=old['previous_service_day']
    data=request('civil_weekend_after_midnight',{'source_stop_id':midnight['source_stop_id'],
        'destination_stop_id':carry['destination_stop_id'],'travel_date':'2026-11-20',
        'departure_time':clock(midnight['departure_seconds']),'max_wait_minutes':0,'max_transfers':0,'limit':20})
    target=next(j for j in data['journeys'] if j['legs'][0]['trip_id']==midnight['trip_id'])
    assert [(s['crowding']['is_weekend'],s['crowding']['time_slot']) for s in target['legs'][0]['segments']]==[(False,47),(True,0)]
    long=cases['slot_crossing']
    data=request('per_segment_slot_change',{'source_stop_id':long['from_stop_id'],
        'destination_stop_id':long['to_stop_id'],'travel_date':long['travel_date'],
        'departure_time':clock(long['boarding_departure_seconds']),'max_wait_minutes':0,'max_transfers':0,'limit':20})
    target=next(j for j in data['journeys'] if j['legs'][0]['trip_id']==long['trip_id'])
    assert {s['crowding']['time_slot'] for s in target['legs'][0]['segments']}=={17,18}
    transfer=old['transfer_only']
    data=request('real_transfer_with_segment_evidence',{'source_stop_id':transfer['source_stop_id'],
        'destination_stop_id':transfer['destination_stop_id'],'travel_date':'2026-11-20','departure_time':'06:09','limit':3})
    assert data['journeys'] and all(j['transfers']==1 for j in data['journeys'])
    data=request('unsupported_date',{'source_stop_id':low['from_stop_id'],'destination_stop_id':low['to_stop_id'],
        'travel_date':'2024-11-20','departure_time':'08:45'})
    assert data['status']=='unsupported_date' and not data['recommendations']
    try:
        urlopen('http://127.0.0.1:8000/api/journeys?'+urlencode({'source_stop_id':low['from_stop_id'],
            'destination_stop_id':low['to_stop_id'],'travel_date':low['travel_date'],
            'departure_time':'08:45','preference':'guaranteed-seats'}),timeout=30)
        raise AssertionError('Expected invalid preference error')
    except HTTPError as error:
        assert error.code==422
        checks.append({'case':'invalid_preference','http_status':422})
    with urlopen('http://127.0.0.1:8000/openapi.json',timeout=30) as response:
        schema=json.load(response)
    assert schema['info']['version']=='0.5.0' and '/api/journeys' in schema['paths']
    with urlopen('http://127.0.0.1:8000/docs',timeout=30) as response:
        assert response.status==200 and b'SwaggerUIBundle' in response.read()
    report={'api_version':'0.5.0','base_url':'http://127.0.0.1:8000','checks':checks,
        'documented_api_paths':len(schema['paths']),'swagger':'passed',
        'summary':f'{len(checks)} live journey/ranking checks passed using actual exports; no occupancy/seat guarantees.'}
    (PROJECT_ROOT/'docs/phase5-ranking-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(report['summary'])


if __name__=='__main__':
    main()
