"""Explicit recommendation policy over actual enriched, bounded journeys."""
import hashlib
import json

from .crowding_schemas import RankingPolicy
from .journey_crowding import JourneyCrowding, UNKNOWN_PENALTY
from .journey_planner import InvalidJourneyRequest, JourneyPlanner


def identity(journey):
    return tuple((leg['route_id'], leg['pattern_id'], leg['trip_id'], leg['service_date'].isoformat(),
                  leg['boarding_stop_sequence'], leg['alighting_stop_sequence']) for leg in journey['legs'])


def score(journey, policy):
    crowding = journey['crowding']['duration_weighted_penalized_crowding']
    # Zero-duration paths have no meaningful weighted crowding; never turn that
    # absence into a zero/Low crowding score.
    if crowding is None:
        crowding = UNKNOWN_PENALTY
    duration = journey['total_duration_seconds'] / 60
    crowding_penalty = policy.crowding_penalty_minutes_per_score * crowding
    transfer_penalty = policy.transfer_penalty_minutes * journey['transfers']
    return {'duration_component_minutes': duration,
            'crowding_penalty_component_minutes': crowding_penalty,
            'transfer_penalty_component_minutes': transfer_penalty,
            'balanced_score_minutes': duration + crowding_penalty + transfer_penalty,
            'unknown_penalized_relative_crowding': crowding,
            'comfort_eligible': journey['crowding']['comfort_eligible']}


def rank_journeys(journeys, preference, limit, policy=None):
    """No fake alternative winners: a shared winner gets multiple preference labels."""
    if preference not in ('fastest', 'comfortable', 'balanced'):
        raise InvalidJourneyRequest('preference must be fastest, comfortable or balanced')
    policy = policy or RankingPolicy()
    unique = {}
    for journey in journeys:
        key = identity(journey)
        if key in unique:
            continue
        journey['journey_id'] = 'journey_' + hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24]
        journey['ranking'] = score(journey, policy)
        unique[key] = journey
    items = list(unique.values())

    def fastest(journey):
        return (journey['total_duration_seconds'], journey['transfers'],
                journey['ranking']['unknown_penalized_relative_crowding'], journey['journey_id'])

    def comfortable(journey):
        return (not journey['crowding']['comfort_eligible'],
                journey['ranking']['unknown_penalized_relative_crowding'], *fastest(journey))

    def balanced(journey):
        return (journey['ranking']['balanced_score_minutes'], *fastest(journey))

    eligible = [journey for journey in items if journey['crowding']['comfort_eligible']]
    winners = {}
    if items:
        winners['fastest'] = min(items, key=fastest)
        winners['balanced'] = min(items, key=balanced)
    if eligible:
        winners['comfortable'] = min(eligible, key=comfortable)
    unavailable = []
    if items and not eligible:
        unavailable.append({'preference': 'comfortable', 'code': 'insufficient_reliable_coverage',
            'explanation': ('No examined journey has positive in-vehicle duration and at least 0.8 reliable '
                'classification coverage by both segment count and duration. Unknown/Insufficient Data is not Low crowding.')})
    elif not items:
        unavailable = [{'preference': name, 'code': 'no_feasible_journey',
                        'explanation': 'No feasible journey was available in the bounded timetable search.'}
                       for name in ('fastest', 'comfortable', 'balanced')]
    recommendations = {}
    for name in ('fastest', 'comfortable', 'balanced'):
        if name not in winners:
            continue
        journey = winners[name]
        if name == 'fastest':
            explanation = f"Minimum total duration among {len(items)} examined unique journeys: {journey['total_duration_seconds']} seconds."
        elif name == 'comfortable':
            evidence = journey['crowding']
            explanation = (f"Lowest unknown-penalized relative score among {len(eligible)} coverage-eligible journeys; "
                f"reliable duration coverage {evidence['duration_reliable_classification_coverage']:.6f}, "
                f"reliable segment coverage {evidence['reliable_classification_coverage']:.6f}. These are evidence fractions, not occupancy.")
        else:
            components = journey['ranking']
            explanation = (f"Minimum policy cost: {components['duration_component_minutes']:.6f} duration minutes + "
                f"{components['crowding_penalty_component_minutes']:.6f} crowding penalty minutes + "
                f"{components['transfer_penalty_component_minutes']:.6f} transfer penalty minutes. "
                'Unknown crowding is penalized; this is not an occupancy measurement.')
        record = recommendations.setdefault(journey['journey_id'],
            {'preferences': [], 'journey': journey, 'explanations': {}})
        record['preferences'].append(name)
        record['explanations'][name] = explanation
    available = preference in winners
    order = {'fastest': fastest, 'comfortable': comfortable, 'balanced': balanced}[preference] if available else fastest
    selected = sorted(items, key=order)[:limit]
    return {'journeys': selected, 'recommendations': list(recommendations.values()),
            'unavailable_recommendations': unavailable, 'preference': preference,
            'applied_preference': preference if available else None,
            'preference_available': available,
            'preference_unavailable_reason': next((r['explanation'] for r in unavailable if r['preference'] == preference), None),
            'ranking_policy': policy.model_dump()}, len(items)


class RankedJourneyService:
    def __init__(self, database):
        self.db = database
        self.planner = JourneyPlanner(database)
        self.crowding = JourneyCrowding(database)

    def plan(self, source_stop_id, destination_stop_id, travel_date, departure_time, *,
             preference='balanced', limit=10, **options):
        if preference not in ('fastest', 'comfortable', 'balanced'):
            raise InvalidJourneyRequest('preference must be fastest, comfortable or balanced')
        policy = RankingPolicy()
        result = self.planner.plan(source_stop_id, destination_stop_id, travel_date, departure_time,
            limit=limit, candidate_pool_limit=policy.candidate_pool_limit, **options)
        pool_truncated = result['search']['result_limit_reached']
        pool = result['journeys']
        self.crowding.attach(pool)
        ranked, evaluated = rank_journeys(pool, preference, limit, policy)
        result.update(ranked)
        result['search'].update(ranking_candidates_evaluated=evaluated,
            ranking_pool_limit=policy.candidate_pool_limit, ranking_pool_truncated=pool_truncated,
            result_limit=limit, result_limit_reached=evaluated > limit)
        result['warnings'].append('Crowding scores compare segment-specific historical labels, not verified absolute occupancy or seat availability.')
        if pool_truncated:
            result['warnings'].append('The ranking pool limit was reached; recommendations compare only examined journeys.')
        if not result['preference_available']:
            result['warnings'].append(result['preference_unavailable_reason'])
        return result
