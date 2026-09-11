"""
Neo4j Graph Writer module.
Handles schema initialization, idempotent row writes using MERGE,
safe property ingestion, and connection retry handling.
"""
import os
import time
import logging
from typing import Dict, Any, Optional, List
# pyrefly: ignore [missing-import]
from neo4j import GraphDatabase, Driver, Session, exceptions
from .models import CSVRowMessage, JobMetrics

logger = logging.getLogger("neo4j_writer")


class Neo4jWriter:
    """
    Idempotent Neo4j database writer for CSV ingestion.
    Enforces (:Dataset)-[:HAS_ROW]->(:Row) graph architecture.
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        max_connection_retries: int = 5,
        retry_delay_seconds: float = 2.0,
    ):
        self.uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.username = username or os.getenv("NEO4J_USERNAME", "neo4j")
        self.password = password or os.getenv("NEO4J_PASSWORD", "password")
        self.database = database or os.getenv("NEO4J_DATABASE", "neo4j")
        self.max_retries = max_connection_retries
        self.retry_delay = retry_delay_seconds

        self._driver: Optional[Driver] = None
        # Track job metrics in memory for real-time reporting
        self.jobs: Dict[str, JobMetrics] = {}

    def connect(self) -> None:
        """
        Establishes connection to Neo4j with exponential backoff retries.
        """
        attempt = 0
        last_exception = None

        while attempt < self.max_retries:
            try:
                attempt += 1
                logger.info(f"Connecting to Neo4j at {self.uri} (attempt {attempt}/{self.max_retries})...")
                self._driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.username, self.password),
                    max_connection_lifetime=30 * 60,
                    max_connection_pool_size=50,
                )
                # Verify connectivity
                self._driver.verify_connectivity()
                logger.info("Successfully connected to Neo4j.")
                self.initialize_schema()
                return
            except Exception as e:
                last_exception = e
                logger.warning(f"Neo4j connection attempt {attempt} failed: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay * attempt)

        raise ConnectionError(
            f"Failed to connect to Neo4j after {self.max_retries} attempts. Last error: {last_exception}"
        )

    def close(self) -> None:
        """Closes the Neo4j driver connection cleanly."""
        if self._driver:
            self._driver.close()
            logger.info("Closed Neo4j driver connection.")

    def get_session(self) -> Session:
        """Returns a managed Neo4j session."""
        if not self._driver:
            self.connect()
        return self._driver.session(database=self.database)

    def initialize_schema(self) -> None:
        """
        Creates constraints and indexes to guarantee unique dataset and row IDs.
        Compatible with Neo4j 5.24 Community Edition.
        """
        constraints = [
            "CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT row_id_unique IF NOT EXISTS FOR (r:Row) REQUIRE r.id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX row_dataset_id_idx IF NOT EXISTS FOR (r:Row) ON (r.dataset_id)",
            "CREATE INDEX row_job_id_idx IF NOT EXISTS FOR (r:Row) ON (r.job_id)",
        ]

        with self.get_session() as session:
            for query in constraints + indexes:
                try:
                    session.run(query)
                except Exception as e:
                    logger.warning(f"Schema statement warning ('{query}'): {e}")

        logger.info("Neo4j constraints and indexes verified.")

    def write_row(self, message: CSVRowMessage) -> bool:
        """
        Idempotently writes a single CSV row message into Neo4j using MERGE.
        Graph structure:
          MERGE (d:Dataset {id: $dataset_id})
          MERGE (r:Row {id: $stable_row_id})
          MERGE (d)-[:HAS_ROW]->(r)
        Also tracks job status and rows loaded / failed.
        rows_loaded is only incremented when a row is newly created.
        """
        # Ensure job metric tracking exists
        if message.job_id not in self.jobs:
            self.jobs[message.job_id] = JobMetrics(
                job_id=message.job_id,
                dataset_id=message.dataset_id,
                rows_total=message.rows_total or 0,
                rows_loaded=0,
                rows_failed=0,
                status="IN_PROGRESS",
            )
        job = self.jobs[message.job_id]
        if message.rows_total and job.rows_total == 0:
            job.rows_total = message.rows_total

        stable_id = message.stable_row_id
        properties = message.get_sanitized_properties()

        # Parameterized Cypher query: Zero string concatenation prevents Cypher injection
        # Detects whether the Row was created during this query using ON CREATE SET
        query = """
        MERGE (d:Dataset {id: $dataset_id})
          ON CREATE SET d.created_at = datetime(), d.updated_at = datetime()
          ON MATCH SET d.updated_at = datetime()

        MERGE (r:Row {id: $stable_row_id})
          ON CREATE SET r.is_new = true, r.created_at = datetime()
          ON MATCH SET r.is_new = false

        SET r += $properties,
            r.dataset_id = $dataset_id,
            r.job_id = $job_id,
            r.row_index = $row_index,
            r.updated_at = datetime()

        MERGE (d)-[rel:HAS_ROW]->(r)

        WITH r, r.is_new AS was_created
        REMOVE r.is_new

        MERGE (j:Job {id: $job_id})
          ON CREATE SET j.dataset_id = $dataset_id,
                        j.status = 'IN_PROGRESS',
                        j.rows_loaded = CASE WHEN was_created THEN 1 ELSE 0 END,
                        j.created_at = datetime()
          ON MATCH SET j.rows_loaded = coalesce(j.rows_loaded, 0) + CASE WHEN was_created THEN 1 ELSE 0 END,
                       j.updated_at = datetime()

        RETURN r.id AS row_id, was_created
        """

        params = {
            "dataset_id": message.dataset_id,
            "job_id": message.job_id,
            "row_index": message.row_index,
            "stable_row_id": stable_id,
            "properties": properties,
        }

        retries = 3
        for attempt in range(1, retries + 1):
            try:
                with self.get_session() as session:
                    result = session.run(query, params)
                    record = result.single()
                    if record and record["row_id"] == stable_id:
                        was_created = bool(record.get("was_created", False))
                        if was_created:
                            job.rows_loaded += 1
                        logger.info(
                            f"[SUCCESS] Row processed: dataset_id={message.dataset_id} "
                            f"job_id={message.job_id} row_index={message.row_index} "
                            f"stable_id={stable_id} was_created={was_created} properties_count={len(properties)}"
                        )
                        return True
                    else:
                        raise ValueError("Neo4j did not return expected row_id.")
            except (exceptions.TransientError, exceptions.ServiceUnavailable) as trans_err:
                logger.warning(
                    f"Transient Neo4j error writing row {stable_id} (attempt {attempt}/{retries}): {trans_err}"
                )
                if attempt < retries:
                    time.sleep(0.5 * attempt)
                else:
                    self._record_failure(job, message, trans_err)
                    return False
            except Exception as e:
                self._record_failure(job, message, e)
                return False

        return False

    def _record_failure(self, job: JobMetrics, message: CSVRowMessage, error: Exception) -> None:
        """Records and logs a failed row without silently ignoring it."""
        job.rows_failed += 1
        logger.error(
            f"[FAILED] Failed to load row: dataset_id={message.dataset_id} "
            f"job_id={message.job_id} row_index={message.row_index} "
            f"error={str(error)}"
        )

    def mark_job_status(self, job_id: str, status: str) -> None:
        """Updates job status (e.g. COMPLETED, FAILED)."""
        if job_id in self.jobs:
            self.jobs[job_id].status = status

        try:
            with self.get_session() as session:
                session.run(
                    "MERGE (j:Job {id: $job_id}) SET j.status = $status, j.updated_at = datetime()",
                    {"job_id": job_id, "status": status},
                )
        except Exception as e:
            logger.warning(f"Could not persist job status to Neo4j: {e}")

    def get_job_metrics(self, job_id: str) -> Optional[JobMetrics]:
        """Returns in-memory or persisted job statistics for API reporting."""
        return self.jobs.get(job_id)

    def count_total_rows(self) -> int:
        """Helper to count all Row nodes in the database."""
        with self.get_session() as session:
            result = session.run("MATCH (r:Row) RETURN count(r) AS total")
            record = result.single()
            return record["total"] if record else 0

    def count_dataset_rows(self, dataset_id: str) -> int:
        """Helper to count Row nodes connected to a specific Dataset."""
        with self.get_session() as session:
            result = session.run(
                "MATCH (d:Dataset {id: $dataset_id})-[:HAS_ROW]->(r:Row) RETURN count(r) AS count",
                {"dataset_id": dataset_id},
            )
            record = result.single()
            return record["count"] if record else 0

    def get_all_properties_for_rows(self) -> List[str]:
        """
        Inspects existing properties on Row nodes.
        Helps the chatbot dynamically discover columns.
        """
        with self.get_session() as session:
            # Query properties across Row nodes
            result = session.run(
                """
                MATCH (r:Row)
                UNWIND keys(r) AS key
                WITH DISTINCT key
                WHERE NOT key IN ['id', 'dataset_id', 'job_id', 'row_index', 'created_at', 'updated_at']
                RETURN key
                """
            )
            return [record["key"] for record in result]
