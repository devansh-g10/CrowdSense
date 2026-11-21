"""Aggregations over exported profiles and saved notebook evaluation reports."""
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from .dependencies import PaginationDep, ResourcesDep, page
from ..schemas import (ExportResponse, HeatmapCell, Identifier, Overview, Page,
                       PeakHour, Performance, RouteAnalytics, Weekly, HighSegment, SlotCounts)

router = APIRouter(prefix='/analytics', tags=['Analytics'])


@router.get('/overview', response_model=Overview)
def overview(resources: ResourcesDep):
    """Counts cover the whole export, including Insufficient Data profiles."""
    return resources.db.overview()


@router.get('/routes', response_model=Page[RouteAnalytics])
def route_analytics(resources: ResourcesDep, pagination: PaginationDep,
                    search: Annotated[str, Query(max_length=256)] = '',
                    route_id: Identifier | None = None, is_weekend: bool | None = None,
                    time_slot: Annotated[int | None, Query(ge=0, le=47)] = None):
    """Per-route profile/classification counts summed over selected day types and slots."""
    return page(resources.db.analytics_rows(route_id=route_id, is_weekend=is_weekend,
        time_slot=time_slot, search=search, aggregate_routes=True, limit=pagination.limit, offset=pagination.offset), pagination)


@router.get('/heatmap', response_model=Page[HeatmapCell | SlotCounts])
def heatmap(resources: ResourcesDep, pagination: PaginationDep,
            aggregate_slots: bool = False,
            route_id: Identifier | None = None, is_weekend: bool | None = None,
            time_slot: Annotated[int | None, Query(ge=0, le=47)] = None):
    """Existing route/day-type/30-minute cells, retaining insufficient-data counts."""
    return page(resources.db.analytics_rows(route_id=route_id, is_weekend=is_weekend,
        time_slot=time_slot, aggregate_slots=aggregate_slots, limit=pagination.limit, offset=pagination.offset), pagination)


@router.get('/high-segments', response_model=Page[HighSegment])
def high_segments(resources: ResourcesDep, pagination: PaginationDep,
                  route_id: Identifier | None = None, is_weekend: bool | None = None,
                  time_slot: Annotated[int | None, Query(ge=0, le=47)] = None):
    """Exported High segment profiles, ordered by supporting journey count."""
    return page(resources.db.high_segments(route_id=route_id, is_weekend=is_weekend, time_slot=time_slot,
        limit=pagination.limit, offset=pagination.offset), pagination)


@router.get('/weekly', response_model=ExportResponse[Weekly])
def weekly(resources: ResourcesDep):
    return {'source': 'weekly_analysis.csv', 'items': resources.exports.weekly()}


@router.get('/peak-hours', response_model=ExportResponse[PeakHour])
def peak_hours(resources: ResourcesDep,
               day_type: Literal['Weekday', 'Weekend'] | None = None):
    rows = resources.exports.peak_hours()
    return {'source': 'peak_analysis.csv',
            'items': [row for row in rows if day_type is None or row.day_type == day_type]}


@router.get('/model-performance', response_model=Performance)
def model_performance(resources: ResourcesDep):
    return resources.exports.performance()
