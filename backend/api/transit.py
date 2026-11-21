"""Read-only stop, route and existing crowding profile endpoints."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from .dependencies import PaginationDep, ResourcesDep, page, require_route
from ..schemas import (CrowdingResponse, Identifier, Page, Route, RouteDetail,
                       Segment, Stop)

router = APIRouter(tags=['Transit'])


@router.get('/stops', response_model=Page[Stop])
def stops(resources: ResourcesDep, pagination: PaginationDep,
          search: Annotated[str, Query(max_length=256)] = '', stop_id: Identifier | None = None):
    """Literal case-insensitive stop-name search; stable limit/offset pagination."""
    return page(resources.db.stops(search=search, stop_id=stop_id,
                                  limit=pagination.limit, offset=pagination.offset), pagination)


@router.get('/routes', response_model=Page[Route])
def routes(resources: ResourcesDep, pagination: PaginationDep,
           search: Annotated[str, Query(max_length=256)] = '',
           route_id: Identifier | None = None, stop_id: Identifier | None = None):
    return page(resources.db.routes(search=search, route_id=route_id, stop_id=stop_id,
                                   limit=pagination.limit, offset=pagination.offset), pagination)


@router.get('/routes/{route_id}', response_model=RouteDetail)
def route_detail(route_id: Identifier, resources: ResourcesDep, pagination: PaginationDep):
    """Route definition with a separately paginated list of actual patterns."""
    route = require_route(resources, route_id)
    patterns = resources.db.route_patterns(route_id, limit=pagination.limit, offset=pagination.offset)
    return {'route': route, 'patterns': page(patterns, pagination)}


@router.get('/routes/{route_id}/segments', response_model=Page[Segment])
def route_segments(route_id: Identifier, resources: ResourcesDep, pagination: PaginationDep,
                   pattern_id: Annotated[int | None, Query(ge=0, le=2**63 - 1)] = None):
    """Consecutive stops in each exported pattern; no journey routing or inferred geometry."""
    require_route(resources, route_id)
    if pattern_id is not None:
        if not resources.db.pattern_stops(route_id, pattern_id, limit=1):
            raise HTTPException(404, 'Pattern not found for this route')
    return page(resources.db.route_segments(route_id, pattern_id=pattern_id,
                limit=pagination.limit, offset=pagination.offset), pagination)


@router.get('/crowding', response_model=CrowdingResponse)
def crowding(resources: ResourcesDep, pagination: PaginationDep,
             route_id: Identifier, pattern_id: Annotated[int, Query(ge=0, le=2**63 - 1)],
             is_weekend: bool, time_slot: Annotated[int, Query(ge=0, le=47)],
             stop_sequence: Annotated[int | None, Query(ge=0, le=2**63 - 1)] = None,
             from_stop_id: Identifier | None = None, to_stop_id: Identifier | None = None):
    """Existing historical profiles only. Unavailable predictions are null, never invented zeros.

    Slot index is local Asia/Kolkata (0–47). The source already includes hourly
    fallback. Low-support exported numbers remain visible separately, while the
    usable prediction is null and the Insufficient Data classification is kept.
    """
    rows = resources.db.crowding_predictions(route_id, pattern_id, is_weekend, time_slot,
        stop_sequence=stop_sequence, from_stop_id=from_stop_id, to_stop_id=to_stop_id,
        limit=pagination.limit, offset=pagination.offset)
    items = []
    for row in rows:
        available = row['crowding_level'] != 'Insufficient Data' and row['predicted_load'] is not None
        items.append({**row, 'exported_predicted_load': row['predicted_load'],
                      'predicted_load': row['predicted_load'] if available else None,
                      'available': available,
                      'unavailable_reason': None if available else 'insufficient_data'})
    available_count = sum(item['available'] for item in items)
    if not items:
        status, reason = 'unavailable', 'no_profiles_on_page' if pagination.offset else 'no_matching_exported_profile'
    elif available_count == len(items):
        status, reason = 'available', None
    elif available_count:
        status, reason = 'partial', 'some_profiles_have_insufficient_data'
    else:
        status, reason = 'unavailable', 'insufficient_data'
    return {**page(items, pagination), 'status': status, 'unavailable_reason': reason}
