"""Health and model provenance endpoints."""
from fastapi import APIRouter

from .dependencies import ResourcesDep
from ..schemas import Health, ModelInfo

router = APIRouter(tags=['System'])


@router.get('/health', response_model=Health)
def health(resources: ResourcesDep):
    """Check all eight Parquet views and parse all five JSON/CSV exports."""
    with resources.db.connection() as con:
        con.execute('SELECT 1').fetchall()
    resources.exports.verify()
    return {'status': 'ok', 'database': 'ready', 'model_files': 'ready'}


@router.get('/model-info', response_model=ModelInfo)
def model_info(resources: ResourcesDep):
    """Original model metadata and limitations; no training or recalibration."""
    return resources.exports.metadata().model_dump()
