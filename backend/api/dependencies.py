"""Shared request resource limits and pagination validation."""
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request

from ..database import Database
from ..exports import ExportRepository


@dataclass
class Resources:
    db: Database
    exports: ExportRepository


def get_resources(request: Request):
    semaphore = request.app.state.query_slots
    if not semaphore.acquire(blocking=True, timeout=1.0):
        raise HTTPException(503, 'Database request capacity reached; retry shortly.',
                            headers={'Retry-After': '1'})
    try:
        yield request.app.state.resources
    finally:
        semaphore.release()


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination(request: Request,
               limit: Annotated[int, Query(ge=1, le=1000)] = 100,
               offset: Annotated[int, Query(ge=0, le=2**63 - 1)] = 0):
    if limit > request.app.state.resources.db.settings.max_query_rows:
        raise HTTPException(422, 'limit exceeds the configured database result limit')
    return Pagination(limit, offset)


ResourcesDep = Annotated[Resources, Depends(get_resources)]
PaginationDep = Annotated[Pagination, Depends(pagination)]


def page(items, pagination):
    return {'items': items, 'limit': pagination.limit,
            'offset': pagination.offset, 'returned': len(items)}


def require_route(resources, route_id):
    routes = resources.db.routes(route_id=route_id, limit=1)
    if not routes:
        raise HTTPException(404, 'Route not found in the exported dataset')
    return routes[0]
