"""Join bounded real journey segment keys to the existing immutable model."""
from collections import Counter
from math import isfinite

from .database import Database, _rows
from .journey_planner import IST

LEVEL_SCORES = {'Low': 0.0, 'Moderate': 0.5, 'High': 1.0}
UNKNOWN_PENALTY = 1.25
MIN_COVERAGE = 0.8


def segment_key(leg, segment):
    local = segment['departure_at'].astimezone(IST)
    return (leg['route_id'], leg['pattern_id'], segment['from_stop_sequence'],
            segment['from_stop_id'], segment['to_stop_id'], local.weekday() >= 5,
            local.hour * 2 + local.minute // 30)


def summarize(journey):
    segments = [segment for leg in journey['legs'] for segment in leg['segments']]
    n = len(segments)
    duration = sum(segment['approximate_duration_seconds'] for segment in segments)
    predicted = reliable = predicted_duration = reliable_duration = 0
    weighted = penalized = 0.0
    counts = Counter({level: 0 for level in (*LEVEL_SCORES, 'Insufficient Data')})
    support = Counter({level: 0 for level in ('High', 'Medium', 'Low', 'Missing')})
    support_duration = support.copy()
    for segment in segments:
        evidence = segment['crowding']
        seconds = segment['approximate_duration_seconds']
        counts[evidence['crowding_level']] += 1
        support[evidence['data_support'] or 'Missing'] += 1
        support_duration[evidence['data_support'] or 'Missing'] += seconds
        if evidence['prediction_available']:
            predicted += 1
            predicted_duration += seconds
        if evidence['reliable_classification']:
            reliable += 1
            reliable_duration += seconds
            weighted += seconds * evidence['relative_crowding_score']
            penalized += seconds * evidence['relative_crowding_score']
        else:
            penalized += seconds * UNKNOWN_PENALTY
    prediction_coverage = predicted / n if n else 0.0
    reliable_coverage = reliable / n if n else 0.0
    time_coverage = reliable_duration / duration if duration else None
    reasons = []
    if not duration:
        reasons.append('no_positive_in_vehicle_duration')
    if reliable_coverage < MIN_COVERAGE:
        reasons.append('insufficient_reliable_segment_coverage')
    if time_coverage is None or time_coverage < MIN_COVERAGE:
        reasons.append('insufficient_reliable_duration_coverage')
    return {'total_segments': n, 'predicted_segments': predicted,
            'reliably_classified_segments': reliable, 'classification_counts': dict(counts),
            'prediction_coverage': prediction_coverage,
            'reliable_classification_coverage': reliable_coverage,
            'in_vehicle_duration_seconds': duration, 'predicted_duration_seconds': predicted_duration,
            'reliably_classified_duration_seconds': reliable_duration,
            'duration_prediction_coverage': predicted_duration / duration if duration else None,
            'duration_reliable_classification_coverage': time_coverage,
            'unknown_duration_fraction': 1 - time_coverage if time_coverage is not None else None,
            'data_support': dict(support), 'data_support_duration_seconds': dict(support_duration),
            'duration_weighted_relative_crowding': weighted / reliable_duration if reliable_duration else None,
            'duration_weighted_penalized_crowding': penalized / duration if duration else None,
            'comfort_eligible': not reasons, 'comfort_ineligibility_reasons': reasons}


class JourneyCrowding:
    def __init__(self, database: Database):
        self.db = database

    def attach(self, journeys):
        keys = sorted({segment_key(leg, segment) for journey in journeys
                       for leg in journey['legs'] for segment in leg['segments']})
        if not keys:
            return
        with self.db.connection() as con:
            con.execute('''CREATE TEMP TABLE requested_crowding_keys (
                route_id VARCHAR, pattern_id BIGINT, stop_sequence BIGINT,
                from_stop_id VARCHAR, to_stop_id VARCHAR, is_weekend BOOLEAN, time_slot INTEGER)''')
            # Bounded batches; only placeholder counts enter SQL text.
            for offset in range(0, len(keys), 500):
                batch = keys[offset:offset + 500]
                con.execute('INSERT INTO requested_crowding_keys VALUES ' +
                            ','.join('(?,?,?,?,?,?,?)' for _ in batch),
                            [value for key in batch for value in key])
            rows = _rows(con, '''SELECT k.*, m.route_id IS NOT NULL AS profile_found,
                m.predicted_load AS exported_predicted_load, m.baseline_prediction,
                m.crowding_level, m.prediction_source, m.data_support,
                m.sample_journeys, m.observed_days, m.reference_samples,
                m.lower_threshold, m.upper_threshold, m.peak_load_p90
                FROM requested_crowding_keys k LEFT JOIN crowding_model m
                USING (route_id, pattern_id, stop_sequence, from_stop_id, to_stop_id, is_weekend, time_slot)''')
        lookup = {(row['route_id'], row['pattern_id'], row['stop_sequence'], row['from_stop_id'],
                   row['to_stop_id'], row['is_weekend'], row['time_slot']): row for row in rows}
        if len(rows) != len(keys) or len(lookup) != len(keys):
            raise ValueError('Ambiguous crowding profile keys')
        for journey in journeys:
            for leg in journey['legs']:
                for segment in leg['segments']:
                    row = lookup[segment_key(leg, segment)].copy()
                    numeric = row['exported_predicted_load']
                    prediction_available = numeric is not None and isfinite(numeric) and numeric >= 0
                    # Keep the exported classification. Medium support alone is not enough.
                    if row['profile_found'] and row['crowding_level'] not in (*LEVEL_SCORES, 'Insufficient Data'):
                        raise ValueError('Unknown exported crowding classification')
                    reliable = (prediction_available and row['crowding_level'] in LEVEL_SCORES
                        and row['data_support'] in ('Medium', 'High')
                        and (row['sample_journeys'] or 0) >= 5 and (row['observed_days'] or 0) >= 3
                        and (row['reference_samples'] or 0) >= 20)
                    row.update(scheduled_departure_at=segment['departure_at'].astimezone(IST),
                        crowding_level=row['crowding_level'] if row['profile_found'] else 'Insufficient Data',
                        prediction_available=prediction_available, reliable_classification=reliable,
                        predicted_load=numeric if reliable else None,
                        relative_crowding_score=LEVEL_SCORES[row['crowding_level']] if reliable else None,
                        unavailable_reason=None if reliable else
                            'insufficient_data' if row['profile_found'] else 'no_matching_exported_profile')
                    segment['crowding'] = row
            journey['crowding'] = summarize(journey)
