from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional
import threading

@dataclass
class JobRecord:
    job_id: str
    dataset_id: str
    filename: str
    rows_total: int
    rows_received: int = 0
    rows_failed: int = 0
    status: str = "queued"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class JobStateManager:
    """
    In-memory job state tracking for single API container instances.
    """
    def __init__(self):
        self._jobs: Dict[str, JobRecord] = {}
        self._lock = threading.Lock()

    def create_job(self, job_id: str, dataset_id: str, filename: str, rows_total: int) -> JobRecord:
        with self._lock:
            record = JobRecord(
                job_id=job_id,
                dataset_id=dataset_id,
                filename=filename,
                rows_total=rows_total,
                rows_received=0,
                rows_failed=0,
                status="queued"
            )
            self._jobs[job_id] = record
            return record

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(
        self,
        job_id: str,
        rows_received: Optional[int] = None,
        rows_failed: Optional[int] = None,
        status: Optional[str] = None
    ) -> Optional[JobRecord]:
        with self._lock:
            record = self._jobs.get(job_id)
            if not record:
                return None
            if rows_received is not None:
                record.rows_received = rows_received
            if rows_failed is not None:
                record.rows_failed = rows_failed
            if status is not None:
                record.status = status
            return record

job_manager = JobStateManager()
