"""API contracts grounded in the exported Parquet, JSON and CSV schemas."""
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from .database import CROWDING_NOTICE

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=256)]
Level = Literal['Low', 'Moderate', 'High', 'Insufficient Data']
Support = Literal['Low', 'Medium', 'High']
T = TypeVar('T')


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class Page(Record, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    returned: int
    notice: str = CROWDING_NOTICE


class ErrorDetail(Record):
    code: str
    message: str


class ErrorResponse(Record):
    error: ErrorDetail


class Health(Record):
    status: Literal['ok']
    database: Literal['ready']
    model_files: Literal['ready']


class ModelMetadata(Record):
    project: str
    model_type: str
    version: str
    timezone: str
    training_period: str
    validation_period: str
    testing_period: str
    time_slot_minutes: int
    total_ticket_records: int
    final_profiles: int
    crowding_type: str
    minimum_profile_samples: int
    minimum_profile_days: int
    minimum_reference_samples: int
    minimum_reference_days: int
    actual_occupancy_validated: bool
    capacity_calibration_available: bool
    limitations: list[str]


class ModelInfo(ModelMetadata):
    notice: str = CROWDING_NOTICE


class Stop(Record):
    stop_id: str
    stop_name: str
    latitude: float
    longitude: float


class Route(Record):
    agency_id: str
    route_id: str
    route_long_name: str
    route_short_name: str
    route_desc: str
    route_type: str


class Pattern(Record):
    route_id: str
    pattern_id: int
    stop_count: int
    first_sequence: int
    last_sequence: int


class RouteDetail(Record):
    route: Route
    patterns: Page[Pattern]


class Segment(Record):
    route_id: str
    pattern_id: int
    stop_sequence: int
    from_stop_id: str
    from_stop_name: str
    from_latitude: float
    from_longitude: float
    to_stop_id: str
    to_stop_name: str
    to_latitude: float
    to_longitude: float


class CrowdingProfile(Record):
    route_id: str
    pattern_id: int
    stop_sequence: int
    from_stop_id: str
    to_stop_id: str
    is_weekend: bool
    time_slot: int
    baseline_prediction: float | None
    predicted_load: float | None = Field(description='Usable prediction; null when unavailable or Insufficient Data.')
    exported_predicted_load: float | None = Field(description='Original historical model value, including low-support values; not actual occupancy.')
    prediction_source: str
    sample_journeys: int
    observed_days: int
    peak_load_p90: float | None
    lower_threshold: float | None
    upper_threshold: float | None
    reference_samples: int | None
    data_support: Support
    crowding_level: Level
    available: bool
    unavailable_reason: str | None


class CrowdingResponse(Page[CrowdingProfile]):
    status: Literal['available', 'partial', 'unavailable']
    unavailable_reason: str | None


class Overview(Record):
    stops: int
    routes: int
    patterns: int
    trips: int
    scheduled_stop_events: int
    profiles: int
    routes_with_profiles: int
    classifications: dict[Level, int]
    notice: str = CROWDING_NOTICE


class RouteAnalytics(Record):
    route_id: str
    route_name: str
    profiles: int
    low_profiles: int
    moderate_profiles: int
    high_profiles: int
    insufficient_data_profiles: int


class HeatmapCell(Record):
    route_id: str
    route_name: str
    is_weekend: bool
    time_slot: int
    segment_profiles: int
    average_recorded_load: float | None
    maximum_recorded_load: float | None
    low_crowding_segments: float
    moderate_crowding_segments: float
    high_crowding_segments: float
    insufficient_data_segments: float


class SlotCounts(Record):
    is_weekend: bool
    time_slot: int
    segment_profiles: int
    high_crowding_segments: int
    insufficient_data_segments: int


class HighSegment(Record):
    route_id: str
    pattern_id: int
    stop_sequence: int
    from_name: str
    to_name: str
    time_slot: int
    is_weekend: bool
    sample_journeys: int
    observed_days: int


class Weekly(Record):
    week_number: int
    segment_observations: int
    observed_days: int
    observed_journeys: int
    average_recorded_load: float
    median_recorded_load: float
    p90_recorded_load: float


class PeakHour(Record):
    day_type: Literal['Weekday', 'Weekend']
    period: Literal['Morning Peak', 'Evening Peak', 'Other Hours']
    segment_observations: int
    average_load: float
    peak_load_p90: float


class TestMetrics(Record):
    total_observations: int
    evaluated_observations: int
    MAE: float
    RMSE: float
    prediction_bias: float
    within_one_passenger_percentage: float
    coverage_percentage: float


class Comparison(Record):
    model: str
    observations: int
    MAE: float
    RMSE: float


class ExportResponse(Record, Generic[T]):
    source: str
    items: list[T]
    notice: str = CROWDING_NOTICE


class Performance(Record):
    test_metrics: TestMetrics
    model_comparison: list[Comparison]
    sources: list[str]
    evaluation_note: str = ('Saved evaluation against reconstructed recorded loads, not actual occupancy. '
                            'Test metrics and common-observation comparison use different denominators.')
    notice: str = CROWDING_NOTICE
