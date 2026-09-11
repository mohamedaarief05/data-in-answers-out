# Member 2 Integration Contract (Kafka & Neo4j Data Pipeline)

This document specifies the technical integration contract between **Member 2 (API + Kafka)** and **Member 3 (Loader / Consumer + Neo4j)** for the RISE @ RST #5 Hackathon project *"Data In, Answers Out"*.

---

## 1. Overview & Separation of Concerns

- **Member 2 Responsibilities**: Receives CSV files via HTTP `POST /ingest`, performs strict validation, calculates deterministic `dataset_id`, assigns unique `job_id`, and publishes **one Kafka message per CSV data row**.
- **Member 3 Responsibilities**: Consumes messages from Kafka topic `csv-rows` and writes nodes/relationships into Neo4j using idempotent Cypher `MERGE` queries.

> [!IMPORTANT]
> Member 2 **never** writes CSV data rows directly to Neo4j. All row population MUST occur asynchronously via Member 3's consumer.

---

## 2. Kafka Topic & Message Contract

- **Kafka Topic Name**: `csv-rows`
- **Serialization**: UTF-8 encoded JSON
- **Producer Configuration**: `acks=all` with delivery confirmation
- **Message Frequency**: 1 Kafka message per CSV DATA ROW (excluding header)

### Message Schema

```json
{
  "job_id": "b3f1a2c4",
  "dataset_id": "a1b2c3d4e5f6789012345678",
  "filename": "students.csv",
  "row_index": 1,
  "row": {
    "name": "Alice",
    "age": "21",
    "city": "Chennai"
  }
}
```

### Key Properties

1. **`dataset_id` (Deterministic Identity)**:
   - Generated as the first 24 characters of the SHA-256 hash of the raw uploaded CSV bytes.
   - Uploading the exact same CSV content multiple times guarantees the **same** `dataset_id`.
2. **`job_id` (Execution Identifier)**:
   - A unique identifier (e.g. `b3f1a2c4`) generated for each upload attempt.
3. **`row_index` (Row Position)**:
   - 1-based indexing for data rows (Row 1 is the first row after header).
4. **`row` (Key-Value Pair Data)**:
   - Dictionary mapping header column names to string row values.

---

## 3. Required Neo4j Graph Model (Member 3 Specification)

Member 3's consumer service must merge graph entities to ensure idempotency.

### Graph Schema

- **Dataset Node**: `(:Dataset {dataset_id: STRING})`
- **Row Node**: `(:Row {dataset_id: STRING, row_index: INTEGER})`
- **Relationship**: `(:Dataset)-[:HAS_ROW]->(:Row)`

### Required Cypher MERGE Query

Member 3 MUST execute the following Cypher query when consuming each message:

```cypher
MERGE (d:Dataset {dataset_id: $dataset_id})
MERGE (r:Row {
  dataset_id: $dataset_id,
  row_index: $row_index
})
SET r += $row
MERGE (d)-[:HAS_ROW]->(r)
```

> [!WARNING]
> **NEVER use `CREATE`** for Dataset or Row node insertion. Using `MERGE` on `(dataset_id, row_index)` ensures that replaying or re-ingesting duplicate rows will update properties rather than creating duplicate nodes.

---

## 4. Querying Status & Chat Integration

Member 2 queries Neo4j to verify ingestion completion and answer questions:

- **Status Query**:
  ```cypher
  MATCH (r:Row {dataset_id: $dataset_id})
  RETURN count(r) AS count
  ```
- **Total Rows Query**:
  ```cypher
  MATCH (r:Row)
  RETURN count(r) AS count
  ```
- **Dataset Lookup Query**:
  ```cypher
  MATCH (r:Row {dataset_id: $dataset_id})
  RETURN r
  ORDER BY r.row_index
  LIMIT 100
  ```
