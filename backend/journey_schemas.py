"""Schedule-based journey contracts; estimates are never real-time arrivals."""
from datetime import date, datetime
from typing import Literal

from .database import CROWDING_NOTICE
from .crowding_schemas import JourneyCrowding, Preference, RankingPolicy, RankingScore, SegmentCrowding
from .schemas import Record


class JourneyStop(Record):
    stop_id: str
    stop_name: str
    stop_sequence: int
    latitude: float
    longitude: float
    gtfs_departure_seconds: int
    scheduled_departure_at: datetime


class JourneySegment(Record):
    from_stop_id: str
    to_stop_id: str
    from_stop_sequence: int
    to_stop_sequence: int
    departure_at: datetime
    estimated_arrival_at: datetime
    approximate_duration_seconds: int
    crowding: SegmentCrowding


class JourneyLeg(Record):
    route_id: str
    route_name: str
    pattern_id: int
    trip_id: str
    service_id: str
    service_date: date
    boarding_stop_sequence: int
    alighting_stop_sequence: int
    departure_at: datetime
    estimated_arrival_at: datetime
    approximate_duration_seconds: int
    stops: list[JourneyStop]
    intermediate_stops: list[JourneyStop]
    segments: list[JourneySegment]


class Journey(Record):
    journey_id: str
    transfers: int
    departure_at: datetime
    estimated_arrival_at: datetime
    initial_wait_seconds: int
    transfer_wait_seconds: int
    in_vehicle_duration_seconds: int
    travel_duration_seconds: int
    total_duration_seconds: int
    duration_is_approximate: bool = True
    arrival_time_basis: Literal['alighting_stop_departure_proxy'] = 'alighting_stop_departure_proxy'
    legs: list[JourneyLeg]
    crowding: JourneyCrowding
    ranking: RankingScore


class Recommendation(Record):
    preferences: list[Preference]
    journey: Journey
    explanations: dict[str, str]


class UnavailableRecommendation(Record):
    preference: Preference
    code: str
    explanation: str


class CalendarCoverage(Record):
    date_supported: bool
    first_service_date: date
    last_service_date: date
    last_possible_arrival_date: date
    active_service_dates: list[date]
    exceptions_available: bool
    exceptions_source: str | None


class SearchDetails(Record):
    max_wait_minutes: int
    min_transfer_minutes: int
    max_journey_minutes: int
    max_transfers: int
    initial_boardings_examined: int = 0
    destination_events_examined: int = 0
    transfer_events_examined: int = 0
    candidates_considered: int = 0
    bounds: dict[str, int]
    search_truncated: bool = False
    result_limit: int
    result_limit_reached: bool = False
    ranking_candidates_evaluated: int = 0
    ranking_pool_limit: int | None = None
    ranking_pool_truncated: bool = False


class JourneyResponse(Record):
    status: Literal['ok', 'no_journeys', 'unsupported_date', 'search_incomplete']
    reason: str | None
    source_stop_id: str
    destination_stop_id: str
    requested_departure_at: datetime
    timezone: Literal['Asia/Kolkata'] = 'Asia/Kolkata'
    calendar: CalendarCoverage
    search: SearchDetails
    journeys: list[Journey]
    preference: Preference
    applied_preference: Preference | None
    preference_available: bool
    preference_unavailable_reason: str | None
    ranking_policy: RankingPolicy
    recommendations: list[Recommendation]
    unavailable_recommendations: list[UnavailableRecommendation]
    warnings: list[str]
    notice: str = CROWDING_NOTICE
