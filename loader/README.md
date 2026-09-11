# Data In, Answers Out — Loader & Grounded Chatbot (Member 3)

Welcome to the **Loader & Grounded Chatbot** service for the *Data In, Answers Out* pipeline.

---

## 1. What the Loader Does

In our end-to-end pipeline:
```
[User CSV Upload] ──> [API] ──> [Kafka: csv-rows] ──> [Loader] ──> [Neo4j Graph] ──> [Chatbot]
```

The **Loader** is the bridge between our streaming message queue (Kafka) and our graph database (Neo4j). It:
1. Listens continuously to Kafka for newly parsed CSV rows.
2. Safely sanitizes arbitrary CSV column headers and values.
3. Translates dynamic CSV row data into graph nodes.
4. Persists the data idempotently into Neo4j so duplicate messages never corrupt or inflate graph data.
5. Serves as the grounded data source for our deterministic chatbot.

---

## 2. How Kafka Connects to the Loader

- Upstream, when a CSV file is uploaded, the API splits the CSV into individual row payloads and publishes them to the Kafka topic:
  ```
  csv-rows
  ```
- The Loader uses `KafkaConsumer` configured with consumer group `loader-group`.
- It connects to the Kafka brokers specified by the `KAFKA_BOOTSTRAP_SERVERS` environment variable.
- The consumer reads JSON payloads containing:
  - `dataset_id`: Unique identifier for the uploaded CSV dataset.
  - `job_id`: Tracking identifier for the upload task.
  - `row_index`: The 0-indexed position of the row within the CSV.
  - Row columns: Either under a `"data"` object or as direct root fields.
- **Manual Offset Commits (`enable_auto_commit=False`)**: Offsets are committed *only* after a message is successfully written to Neo4j. If Neo4j writing fails, the offset is not committed, preventing silent data loss and enabling reliable message retries.
- If Kafka brokers are temporarily starting up, the Loader automatically retries with exponential backoff rather than failing immediately.

---

## 3. How the Loader Connects to Neo4j

- The Loader uses the **official Neo4j Python driver** (`neo4j>=5.24.0`), fully compatible with **Neo4j 5.24 Community Edition**.
- Connection settings come from environment variables:
  - `NEO4J_URI` (e.g., `bolt://localhost:7687` or `bolt://neo4j:7687`)
  - `NEO4J_USERNAME` (e.g., `neo4j`)
  - `NEO4J_PASSWORD`
  - `NEO4J_DATABASE` (default: `neo4j`)
- Upon startup, the Loader automatically sets up uniqueness constraints and indexes:
  ```cypher
  CREATE CONSTRAINT dataset_id_unique IF NOT EXISTS FOR (d:Dataset) REQUIRE d.id IS UNIQUE;
  CREATE CONSTRAINT row_id_unique IF NOT EXISTS FOR (r:Row) REQUIRE r.id IS UNIQUE;
  CREATE INDEX row_dataset_id_idx IF NOT EXISTS FOR (r:Row) ON (r.dataset_id);
  CREATE INDEX row_job_id_idx IF NOT EXISTS FOR (r:Row) ON (r.job_id);
  ```

---

## 4. What Dataset and Row Nodes Mean

Our graph follows this architecture:
```
(:Dataset {id: dataset_id}) ──[:HAS_ROW]──> (:Row {id: stable_row_id, ...columns})
```

- **`Dataset` Node**: Represents an entire uploaded CSV file or dataset. It stores `id`, `created_at`, and `updated_at`.
- **`Row` Node**: Represents an individual record (row) inside that dataset.
- **Dynamic Properties**: Every column present in the CSV becomes a property on that `Row` node (e.g. `department: "Billing"`, `city: "Chennai"`, `name: "Alice"`).
- **`[:HAS_ROW]` Relationship**: Connects each dataset to all of its constituent row nodes.

---

## 5. Why `MERGE` Is Used Instead of `CREATE`

In Cypher:
- `CREATE` **always** creates a brand-new node or relationship, even if an identical one already exists. If a network blip causes Kafka to re-deliver a message, or if a user uploads the same CSV file twice, `CREATE` would duplicate all nodes and corrupt counts.
- `MERGE` behaves like **"find or create"**:
  - If a node with the specified identifier already exists, Neo4j matches it.
  - If it does not exist, Neo4j creates it.
  - Combined with `SET r += $properties`, it updates properties without duplicating nodes.

---

## 6. How Duplicate Protection Works

Idempotency is guaranteed through a two-layer defense:

1. **Deterministic Stable Identifier**:
   Every row is assigned a stable ID computed from:
   $$\text{stable\_row\_id} = \text{dataset\_id} + \text{"\_"} + \text{row\_index}$$
   For example, row 0 of dataset `ds_sales` always receives ID `ds_sales_0`.
2. **Database Unique Constraint & Atomic MERGE**:
   ```cypher
   MERGE (d:Dataset {id: $dataset_id})
   MERGE (r:Row {id: $stable_row_id})
   SET r += $properties,
       r.dataset_id = $dataset_id,
       r.job_id = $job_id,
       r.row_index = $row_index,
       r.updated_at = datetime()
   MERGE (d)-[:HAS_ROW]->(r)
   ```
   Even if the exact same message is processed 100 times, Neo4j will only ever contain **one** `Row` node with ID `ds_sales_0`.

---

## 7. Required Environment Variables

Configure these in your environment or container configuration (e.g. `.env` or Docker Compose service definition):

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Comma-separated list of Kafka broker hosts |
| `KAFKA_TOPIC` | `csv-rows` | Topic name for CSV row messages |
| `KAFKA_GROUP_ID` | `loader-group` | Kafka consumer group identifier |
| `KAFKA_AUTO_OFFSET_RESET` | `earliest` | Offset reset strategy (`earliest` or `latest`) |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j Bolt connection URI |
| `NEO4J_USERNAME` | `neo4j` | Neo4j database username |
| `NEO4J_PASSWORD` | `password` | Neo4j database password |
| `NEO4J_DATABASE` | `neo4j` | Neo4j database name |

---

## 8. How to Test the Loader

### Automated Verification Test Suite
Run the comprehensive test suite verifying TEST 1 through TEST 5:
```bash
python3 loader/tests/run_all_tests.py
# or using pytest directly:
pytest -v loader/tests/
```

### Manual Testing with Sample Kafka Message
To publish a test row directly into Kafka from the command line:
```bash
docker exec -i <kafka_container_name> kafka-console-producer.sh \
  --bootstrap-server localhost:9092 \
  --topic csv-rows <<EOF
{"dataset_id": "demo_ds", "job_id": "job_1", "row_index": 0, "Name": "Alice", "Department": "Billing", "City": "Chennai"}
{"dataset_id": "demo_ds", "job_id": "job_1", "row_index": 1, "Name": "Bob", "Department": "Billing", "City": "Bangalore"}
EOF
```

### Cypher Queries to Verify in Neo4j Browser

#### 1. Check Total Row Count
Run this query in Neo4j Browser to verify the exact number of `Row` nodes:
```cypher
MATCH (r:Row)
RETURN count(r) AS total_rows;
```

#### 2. Check Rows Grouped by Dataset
```cypher
MATCH (d:Dataset)-[:HAS_ROW]->(r:Row)
RETURN d.id AS dataset_id, count(r) AS rows_loaded;
```

#### 3. Duplicate Verification Query (TEST 3)
If you send the same row multiple times, run this query to verify there are **0 duplicates**:
```cypher
MATCH (r:Row)
WITH r.id AS row_id, count(r) AS appearances
WHERE appearances > 1
RETURN row_id, appearances;
```
*(This query will return 0 rows if duplicate safety is working properly).*

#### 4. View Sample Rows
```cypher
MATCH (d:Dataset)-[:HAS_ROW]->(r:Row)
RETURN d.id AS dataset, r.row_index AS idx, properties(r) AS props
ORDER BY idx ASC
LIMIT 10;
```

---

## 9. How the Chatbot Gets Answers

The chatbot is **100% grounded in Neo4j** and deterministic (no LLM, no hallucination, no guessing):

1. **Source of Truth**: The chatbot answers **ONLY** using data that currently exists in Neo4j.
2. **Schema Discovery**: When a query is asked, it dynamically discovers active properties on `Row` nodes (e.g., `department`, `city`, `name`).
3. **Safe Parameterized Cypher**:
   - Question: `"How many rows are in Billing?"`
     - Cypher:
       ```cypher
       MATCH (r:Row)
       WHERE toLower(toString(r.department)) = toLower($val)
       RETURN count(r) AS count
       ```
     - Result: `5`
     - Response: `"There are 5 rows where department is 'Billing'."` (`grounded: true`)
   - Question: `"Show rows in Billing."`
     - Cypher:
       ```cypher
       MATCH (r:Row)
       WHERE toLower(toString(r.department)) = toLower($val)
       RETURN properties(r) AS row_props LIMIT 10
       ```
     - Response: Displays actual row records (`grounded: true`)
4. **Safety & Refusal (TEST 5)**:
   If a user asks an outside knowledge question (e.g. *"Who is the president of France?"*) or asks about entities not found in the graph (e.g. *"How many rows are in Atlantis?"*), the chatbot **strictly refuses**:
   - `answer`: `"I don't have that in the data."`
   - `grounded`: `false`
   - `cypher`: `null`
   - `result`: `null`

### Run Chatbot Interactively:
```bash
python3 -m app.chatbot
```
Or import programmatically:
```python
from app.neo4j_writer import Neo4jWriter
from app.chatbot import GroundedChatbot

writer = Neo4jWriter()
bot = GroundedChatbot(writer)
response = bot.ask("How many rows are in Billing?")
print(response.model_dump_json(indent=2))
```
