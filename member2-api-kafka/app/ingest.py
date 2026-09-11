import csv
import hashlib
import io
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from app.config import settings
from app.models import IngestResponse
from app.state import job_manager
from app.kafka import kafka_manager

logger = logging.getLogger("member2.ingest")
router = APIRouter()

@router.post(
    "/ingest",
    response_model=IngestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload and ingest CSV data",
    description="Validates CSV, calculates deterministic SHA-256 dataset_id, and publishes rows to Kafka topic csv-rows."
)
async def ingest_csv(file: UploadFile = File(...)):
    # 1. Missing file check
    if not file or not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing upload file."
        )

    # 2. File extension check
    filename = file.filename
    if not filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file extension. Only .csv files are allowed."
        )

    # 3. Read bytes & size check
    try:
        raw_bytes = await file.read()
    except Exception as e:
        logger.error(f"Error reading upload file: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not read uploaded file."
        )

    if len(raw_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    if len(raw_bytes) > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_BYTES} bytes."
        )

    # 4. Valid UTF-8 check
    try:
        text_content = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content is not valid UTF-8 encoded text."
        )

    # 5. CSV Parsing & Validation
    string_io = io.StringIO(text_content)
    try:
        reader = csv.DictReader(string_io)
        headers = reader.fieldnames
    except Exception as e:
        logger.error(f"CSV parsing header error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid CSV format."
        )

    if not headers or len(headers) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV header is missing or empty."
        )

    # Check for empty column names in header
    for h in headers:
        if h is None or str(h).strip() == "":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV contains empty or invalid header column names."
            )

    rows = []
    try:
        for r in reader:
            rows.append(r)
    except Exception as e:
        logger.error(f"Error reading CSV rows: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Corrupted CSV rows encountered."
        )

    if len(rows) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Header-only CSV file with no data rows."
        )

    # 6. SHA-256 Dataset ID generation (first 24 hex characters)
    sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
    dataset_id = sha256_hash[:24]

    # 7. Job ID generation
    job_id = uuid.uuid4().hex[:8]
    rows_total = len(rows)

    # Register job state
    job_manager.create_job(
        job_id=job_id,
        dataset_id=dataset_id,
        filename=filename,
        rows_total=rows_total
    )

    # 8. Publish one Kafka message per CSV row
    rows_received = 0
    rows_failed = 0

    for idx, row_dict in enumerate(rows, start=1):
        # Convert non-string or None values in dict to string
        clean_row = {k: ("" if v is None else str(v)) for k, v in row_dict.items()}
        
        payload = {
            "job_id": job_id,
            "dataset_id": dataset_id,
            "filename": filename,
            "row_index": idx,
            "row": clean_row
        }

        published = await kafka_manager.publish_row(
            topic=settings.KAFKA_TOPIC,
            key=dataset_id,
            payload=payload
        )

        if published:
            rows_received += 1
        else:
            rows_failed += 1

    # Update job state
    job_status = "queued"
    if rows_failed == rows_total:
        job_status = "failed"
        job_manager.update_job(job_id, rows_received=0, rows_failed=rows_failed, status="failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish CSV rows to Kafka message broker."
        )
    elif rows_failed > 0:
        job_status = "failed"
        job_manager.update_job(job_id, rows_received=rows_received, rows_failed=rows_failed, status="failed")
    else:
        job_manager.update_job(job_id, rows_received=rows_received, rows_failed=0, status="queued")

    return IngestResponse(
        job_id=job_id,
        rows_received=rows_received,
        status="queued" if job_status == "queued" else "failed"
    )
