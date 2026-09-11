import logging
from fastapi import APIRouter, HTTPException, Query, status
from app.models import StatusResponse
from app.state import job_manager
from app.neo4j import neo4j_manager

logger = logging.getLogger("member2.status")
router = APIRouter()

@router.get(
    "/status",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get job ingestion and processing status",
    description="Queries Neo4j for count of loaded rows by dataset_id and computes job status: queued, loading, complete, or failed."
)
async def get_job_status(job_id: str = Query(..., description="Job ID returned from POST /ingest")):
    if not job_id or not job_id.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="job_id parameter is required."
        )

    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found."
        )

    # Obtain the number of loaded rows from Neo4j using dataset_id
    rows_loaded = await neo4j_manager.get_loaded_rows_count(job.dataset_id)

    # Compute status according to specified requirements:
    # 1. Publication/write failure occurred -> failed
    if job.rows_failed > 0 or job.status == "failed":
        computed_status = "failed"
    # 2. rows_loaded == rows_total -> complete
    elif rows_loaded >= job.rows_total and job.rows_total > 0:
        computed_status = "complete"
    # 3. rows_loaded > 0 -> loading
    elif rows_loaded > 0:
        computed_status = "loading"
    # 4. job exists and Kafka accepted rows (rows_loaded == 0) -> queued
    else:
        computed_status = "queued"

    # Update state
    job_manager.update_job(job_id, status=computed_status)

    return StatusResponse(
        job_id=job.job_id,
        status=computed_status,
        rows_total=job.rows_total,
        rows_loaded=rows_loaded,
        rows_failed=job.rows_failed
    )
