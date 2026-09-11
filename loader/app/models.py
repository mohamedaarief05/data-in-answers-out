"""
Data models and sanitization utilities for the CSV Loader and Neo4j Writer.
"""
from typing import Any, Dict, Optional
import re
from pydantic import BaseModel, Field, model_validator


def sanitize_property_key(raw_key: str, existing_keys: Optional[set] = None) -> str:
    """
    Safely sanitizes dynamic CSV column headers into valid, safe Neo4j property names.
    - Strips whitespace
    - Lowercases
    - Replaces non-alphanumeric characters with underscores
    - Prefixes with 'prop_' if it starts with a number or is empty
    - Dedupes multiple underscores
    - Handles duplicate keys in a row by appending a numeric suffix (_2, _3, ...)
    """
    if not raw_key or not isinstance(raw_key, str):
        cleaned = "unnamed_column"
    else:
        # Strip and replace punctuation/symbols/spaces with underscores
        cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', raw_key.strip().lower())
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')

        if not cleaned:
            cleaned = "unnamed_column"
        elif cleaned[0].isdigit():
            cleaned = f"col_{cleaned}"

    # Handle collision/duplicate column names if existing_keys tracker is passed
    if existing_keys is not None:
        base_name = cleaned
        counter = 2
        while cleaned in existing_keys:
            cleaned = f"{base_name}_{counter}"
            counter += 1
        existing_keys.add(cleaned)

    return cleaned


def sanitize_property_value(value: Any) -> Any:
    """
    Sanitizes property values.
    - Converts empty strings or whitespace-only strings to None (or empty indicator)
    - Automatically parses numeric integers and floats if applicable
    - Preserves booleans, numbers, and strings
    """
    if value is None:
        return None
    if isinstance(value, str):
        val_str = value.strip()
        if val_str == "":
            return None
        # Try integer conversion
        if re.match(r'^-?\d+$', val_str):
            try:
                return int(val_str)
            except ValueError:
                pass
        # Try float conversion
        if re.match(r'^-?\d+\.\d+$', val_str):
            try:
                return float(val_str)
            except ValueError:
                pass
        # Try boolean conversion
        if val_str.lower() in ("true", "yes"):
            return True
        if val_str.lower() in ("false", "no"):
            return False
        return val_str
    return value


def sanitize_row_properties(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a dynamic row dictionary into sanitized Neo4j properties.
    Ignores keys with None/empty values so Neo4j isn't cluttered with empty attributes.
    """
    sanitized: Dict[str, Any] = {}
    existing_keys: set = set()

    for raw_k, raw_v in raw_data.items():
        clean_k = sanitize_property_key(str(raw_k), existing_keys)
        clean_v = sanitize_property_value(raw_v)
        if clean_v is not None:
            sanitized[clean_k] = clean_v

    return sanitized


class CSVRowMessage(BaseModel):
    """
    Message structure expected from Kafka topic `csv-rows`.
    Supports both nested format {"dataset_id": ..., "data": {...}}
    and flat JSON formats where columns are at the root level.
    """
    dataset_id: str
    job_id: str
    row_index: int
    data: Dict[str, Any] = Field(default_factory=dict)
    rows_total: Optional[int] = None
    status: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def extract_flexible_data(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            raise ValueError("Payload must be a JSON dictionary")

        dataset_id = values.get("dataset_id")
        job_id = values.get("job_id")
        row_index = values.get("row_index")

        if dataset_id is None or job_id is None or row_index is None:
            raise ValueError("dataset_id, job_id, and row_index are required fields")

        # Cast row_index to int if it arrived as a string
        try:
            values["row_index"] = int(row_index)
        except (ValueError, TypeError):
            raise ValueError(f"row_index must be an integer, got {row_index}")

        # If 'data' is not explicitly provided, collect all other keys as row data
        if "data" not in values or not isinstance(values.get("data"), dict):
            reserved = {"dataset_id", "job_id", "row_index", "rows_total", "status"}
            extracted_data = {k: v for k, v in values.items() if k not in reserved}
            values["data"] = extracted_data

        return values

    @property
    def stable_row_id(self) -> str:
        """
        Deterministic, stable identifier: dataset_id + row_index.
        Guarantees idempotency when re-processing rows.
        """
        return f"{self.dataset_id}_{self.row_index}"

    def get_sanitized_properties(self) -> Dict[str, Any]:
        """
        Returns sanitized key-value pairs suitable for Neo4j node properties.
        """
        return sanitize_row_properties(self.data)


class JobMetrics(BaseModel):
    """
    Tracks ingestion progress metrics for a specific job/dataset.
    """
    job_id: str
    dataset_id: str
    rows_total: int = 0
    rows_loaded: int = 0
    rows_failed: int = 0
    status: str = "IN_PROGRESS"  # PENDING, IN_PROGRESS, COMPLETED, FAILED


class ChatbotResponse(BaseModel):
    """
    Grounded response format for user queries.
    Strictly answers ONLY using data from Neo4j.
    """
    answer: str
    cypher: Optional[str] = None
    result: Any = None
    grounded: bool = False
