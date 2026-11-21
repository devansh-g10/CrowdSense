"""Validated local-IST direct and one-transfer timetable planning."""
from datetime import date, time
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from .dependencies import ResourcesDep
from ..journey_planner import InvalidJourneyRequest, UnknownStopError
from ..journey_ranking import RankedJourneyService
from ..crowding_schemas import Preference
from ..journey_schemas import JourneyResponse
from ..schemas import Identifier

router = APIRouter(tags=['Journeys'])


@router.get('/journeys', response_model=JourneyResponse)
def journeys(resources: ResourcesDep, source_stop_id: Identifier, destination_stop_id: Identifier,
             travel_date: Annotated[date, Query(ge=date(1900, 1, 1), le=date(2100, 12, 31))],
             departure_time: Annotated[str, Query(pattern=r'^([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?$')],
             max_wait_minutes: Annotated[int, Query(ge=0, le=120)] = 30,
             min_transfer_minutes: Annotated[int, Query(ge=1, le=30)] = 2,
             max_journey_minutes: Annotated[int, Query(ge=1, le=720)] = 360,
             max_transfers: Annotated[int, Query(ge=0, le=1)] = 1,
             limit: Annotated[int, Query(ge=1, le=20)] = 10,
             preference: Preference = 'balanced'):
    """Use real exported trip instances only; no live bus or occupancy guarantee.

    Date/time are civil Asia/Kolkata values. GTFS 24+ hour events use the
    preceding service date. Max wait applies separately at the origin and
    transfer. Transfers are same-stop only. All arrival/duration values are
    approximate because this export contains departures, not arrivals.
    Crowding is joined at each scheduled segment departure, using its civil IST
    weekday/weekend and 30-minute slot. Recommendation scores are relative
    historical policy scores, never occupancy percentages or seat guarantees.
    """
    try:
        return RankedJourneyService(resources.db).plan(source_stop_id, destination_stop_id,
            travel_date, time.fromisoformat(departure_time), max_wait_minutes=max_wait_minutes,
            min_transfer_minutes=min_transfer_minutes, max_journey_minutes=max_journey_minutes,
            max_transfers=max_transfers, limit=limit, preference=preference)
    except InvalidJourneyRequest as exc:
        raise HTTPException(422, str(exc)) from exc
    except UnknownStopError as exc:
        raise HTTPException(404, str(exc)) from exc
