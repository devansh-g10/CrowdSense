"""Historical evidence and explicit ranking policy, never occupancy estimates."""
from datetime import datetime
from typing import Literal

from pydantic import Field

from .schemas import Level, Record, Support

Preference = Literal['fastest', 'comfortable', 'balanced']


class SegmentCrowding(Record):
    route_id: str
    pattern_id: int
    stop_sequence: int
    from_stop_id: str
    to_stop_id: str
    scheduled_departure_at: datetime
    is_weekend: bool
    time_slot: int
    profile_found: bool
    prediction_available: bool = Field(description='A finite nonnegative numeric estimate exists in the export; this alone does not establish reliability.')
    reliable_classification: bool
    crowding_level: Level
    exported_predicted_load: float | None
    predicted_load: float | None = Field(description='Null when the historical classification is not reliable; not actual occupancy.')
    baseline_prediction: float | None
    prediction_source: str | None
    data_support: Support | None
    sample_journeys: int | None
    observed_days: int | None
    reference_samples: int | None
    lower_threshold: float | None
    upper_threshold: float | None
    peak_load_p90: float | None
    relative_crowding_score: float | None
    unavailable_reason: str | None


class JourneyCrowding(Record):
    total_segments: int
    predicted_segments: int
    reliably_classified_segments: int
    classification_counts: dict[Level, int]
    prediction_coverage: float = Field(description='Fraction of segments with numeric exported predictions, including low-support estimates; not occupancy.')
    reliable_classification_coverage: float = Field(description='Fraction of segments with supported Low/Moderate/High classifications.')
    in_vehicle_duration_seconds: int
    predicted_duration_seconds: int
    reliably_classified_duration_seconds: int
    duration_prediction_coverage: float | None
    duration_reliable_classification_coverage: float | None
    unknown_duration_fraction: float | None
    data_support: dict[Literal['High', 'Medium', 'Low', 'Missing'], int]
    data_support_duration_seconds: dict[Literal['High', 'Medium', 'Low', 'Missing'], int]
    duration_weighted_relative_crowding: float | None = Field(description='Ordinal mean over reliable duration only: Low=0, Moderate=0.5, High=1; not an occupancy fraction.')
    duration_weighted_penalized_crowding: float | None = Field(description='Mean over all in-vehicle duration, assigning 1.25 to unknown/unreliable segments.')
    comfort_eligible: bool
    comfort_ineligibility_reasons: list[str]


class RankingScore(Record):
    duration_component_minutes: float
    crowding_penalty_component_minutes: float
    transfer_penalty_component_minutes: float
    balanced_score_minutes: float
    unknown_penalized_relative_crowding: float
    comfort_eligible: bool


class RankingPolicy(Record):
    level_scores: dict[str, float] = {'Low': 0.0, 'Moderate': 0.5, 'High': 1.0}
    unknown_crowding_penalty: float = 1.25
    minimum_reliable_segment_coverage: float = 0.8
    minimum_reliable_duration_coverage: float = 0.8
    crowding_penalty_minutes_per_score: float = 30.0
    transfer_penalty_minutes: float = 5.0
    candidate_pool_limit: int = 80
    balanced_formula: str = 'total_duration_seconds / 60 + 30 * unknown_penalized_relative_crowding + 5 * transfers'
    scope: str = 'Recommendations compare only the bounded examined journey pool; scores are explicit policy choices, not trained accuracy or occupancy metrics.'
