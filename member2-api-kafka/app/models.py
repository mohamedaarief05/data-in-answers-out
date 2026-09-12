from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class IngestResponse(BaseModel):
    job_id: str = Field(..., description="Unique ID for this ingest job execution")
    dataset_id: Optional[str] = Field(None, description="SHA-256 dataset ID")
    rows_received: int = Field(..., description="Number of CSV rows successfully parsed and published to Kafka")
    status: str = Field(..., description="Current job status, e.g., 'queued'")

class StatusResponse(BaseModel):
    job_id: str = Field(..., description="Unique job ID")
    dataset_id: Optional[str] = Field(None, description="SHA-256 dataset ID")
    status: str = Field(..., description="Job status: queued, loading, complete, failed")
    rows_total: int = Field(..., description="Total rows in the uploaded CSV file")
    rows_loaded: int = Field(..., description="Rows confirmed written into Neo4j")
    rows_failed: int = Field(..., description="Rows that failed during publication")

class HealthResponse(BaseModel):
    status: str = Field(..., description="System health status: ok or degraded")
    kafka_connected: bool = Field(..., description="Kafka broker reachability")
    neo4j_connected: bool = Field(..., description="Neo4j database reachability")

class ChatRequest(BaseModel):
    question: str = Field(..., description="Natural language question", json_schema_extra={"example": "total rows"})

class ChatResponse(BaseModel):
    answer: str = Field(..., description="Chatbot answer")
    cypher: str = Field(..., description="Generated or executed Cypher query")
    result: List[Any] = Field(..., description="Query result items from Neo4j")
    grounded: bool = Field(..., description="True if answer is grounded in Neo4j data")

class KafkaRowPayload(BaseModel):
    job_id: str
    dataset_id: str
    filename: str
    row_index: int
    row: Dict[str, str]
