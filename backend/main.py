"""Local FastAPI app. Run: python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"""
import logging
from threading import BoundedSemaphore

import duckdb
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from .api import analytics, journeys, system, transit
from .api.dependencies import Resources
from .config import Settings
from .database import Database
from .exports import ExportRepository
from .schemas import ErrorResponse

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(title='CrowdRoute Delhi API', version='0.5.0',
        description=('Crowdedness-aware data API over existing Delhi model exports. '
                     'Relative historical crowding is not actual bus occupancy or guaranteed seat availability. '
                     'Bounded GTFS journeys use approximate departure-only timings and historical crowding-aware ranking.'))
    app.state.resources = Resources(Database(settings), ExportRepository(settings))
    app.state.query_slots = BoundedSemaphore(settings.max_concurrent_queries)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=['GET'], allow_headers=['Accept', 'Content-Type'],
                       allow_credentials=False)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, headers=exc.headers,
            content={'error': {'code': {404: 'not_found', 422: 'invalid_input', 503: 'service_unavailable'}.get(exc.status_code, 'http_error'),
                               'message': str(exc.detail)}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Do not echo arbitrary input strings, SQL or local paths in errors.
        fields = ', '.join('.'.join(map(str, error['loc'])) for error in exc.errors())
        return JSONResponse(status_code=422,
            content={'error': {'code': 'invalid_input', 'message': f'Invalid request fields: {fields}'}})

    async def data_error(request: Request, exc: Exception):
        logger.error('Dataset access failed for %s', request.url.path, exc_info=exc)
        return JSONResponse(status_code=503,
            content={'error': {'code': 'dataset_unavailable',
                               'message': 'Required model data is unavailable or incompatible.'}})

    for error in (duckdb.Error, OSError, ValueError):
        app.add_exception_handler(error, data_error)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error('Unhandled API error for %s', request.url.path, exc_info=exc)
        return JSONResponse(status_code=500,
            content={'error': {'code': 'internal_error', 'message': 'An internal server error occurred.'}})

    errors = {404: {'model': ErrorResponse}, 422: {'model': ErrorResponse},
              503: {'model': ErrorResponse}, 500: {'model': ErrorResponse}}
    for router in (system.router, transit.router, analytics.router, journeys.router):
        app.include_router(router, prefix='/api', responses=errors)
    return app


app = create_app()
