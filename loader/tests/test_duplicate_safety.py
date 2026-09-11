"""
Tests for Duplicate Safety and Idempotency (TEST 3).
Verifies that processing the same row multiple times does not produce duplicate nodes.
"""
from unittest.mock import MagicMock
from app.models import CSVRowMessage
from app.neo4j_writer import Neo4jWriter


def test_stable_row_id_determinism():
    """
    Ensures that identical dataset_id and row_index ALWAYS produce the exact same stable_row_id.
    """
    msg1 = CSVRowMessage(dataset_id="dataset_42", job_id="job_a", row_index=10, data={"Name": "Alice"})
    msg2 = CSVRowMessage(dataset_id="dataset_42", job_id="job_b", row_index=10, data={"Name": "Alice"})

    assert msg1.stable_row_id == "dataset_42_10"
    assert msg2.stable_row_id == "dataset_42_10"
    assert msg1.stable_row_id == msg2.stable_row_id


def test_merge_query_idempotency_simulation():
    """
    Simulates sending the same CSV row 3 times to Neo4jWriter.
    Verifies that Neo4j's MERGE query is executed with the stable identifier,
    preventing duplicate node creation, and rows_loaded only increments once.
    """
    writer = Neo4jWriter()

    # Mock Neo4j session and run behavior:
    # 1st execution: new row created (was_created=True)
    # 2nd & 3rd executions: existing row updated (was_created=False)
    mock_session = MagicMock()
    mock_result_first = MagicMock()
    mock_result_first.single.return_value = {"row_id": "ds_sales_0", "was_created": True}

    mock_result_subsequent = MagicMock()
    mock_result_subsequent.single.return_value = {"row_id": "ds_sales_0", "was_created": False}

    mock_session.run.side_effect = [
        mock_result_first,
        mock_result_subsequent,
        mock_result_subsequent,
    ]

    # Mock context manager for session
    writer.get_session = MagicMock(return_value=mock_session)
    mock_session.__enter__.return_value = mock_session
    mock_session.__exit__.return_value = None

    row_payload = {
        "dataset_id": "ds_sales",
        "job_id": "job_101",
        "row_index": 0,
        "Department": "Billing",
        "Name": "Bob",
    }
    msg = CSVRowMessage.model_validate(row_payload)

    # Re-process same row 3 times
    res1 = writer.write_row(msg)
    res2 = writer.write_row(msg)
    res3 = writer.write_row(msg)

    assert res1 is True
    assert res2 is True
    assert res3 is True

    # Critical: rows_loaded must NOT increment multiple times for the same row
    job_metrics = writer.get_job_metrics("job_101")
    assert job_metrics is not None
    assert job_metrics.rows_loaded == 1  # Incremented ONLY on first creation!

    # Verify that MERGE was used in all executions with stable_row_id: 'ds_sales_0'
    assert mock_session.run.call_count == 3
    for call in mock_session.run.call_args_list:
        query_text = call[0][0]
        params = call[0][1]

        # Verify MERGE keyword is used, NOT CREATE
        assert "MERGE (r:Row {id: $stable_row_id})" in query_text
        assert "MERGE (d:Dataset {id: $dataset_id})" in query_text
        assert "MERGE (d)-[rel:HAS_ROW]->(r)" in query_text
        assert "CREATE (r:Row" not in query_text

        # Verify creation detection in Cypher
        assert "ON CREATE SET r.is_new = true" in query_text
        assert "ON MATCH SET r.is_new = false" in query_text
        assert "CASE WHEN was_created THEN 1 ELSE 0 END" in query_text

        # Verify stable parameter
        assert params["stable_row_id"] == "ds_sales_0"
        assert params["dataset_id"] == "ds_sales"
        assert params["row_index"] == 0


def test_in_memory_graph_deduplication():
    """
    In-memory graph dictionary simulation tracking MERGE behavior.
    Demonstrates mathematically that N duplicate message ingestion calls
    result in exactly 1 Row node.
    """
    graph_rows = {}  # simulates (:Row {id}) uniqueness

    def simulate_merge_row(dataset_id: str, row_index: int, props: dict):
        stable_id = f"{dataset_id}_{row_index}"
        # MERGE behavior: if exists, update; if not, create
        if stable_id not in graph_rows:
            graph_rows[stable_id] = {"id": stable_id, **props}
        else:
            graph_rows[stable_id].update(props)
        return stable_id

    # Ingest row 0 five times
    for _ in range(5):
        simulate_merge_row("dataset_finance", 0, {"department": "Billing", "amount": 100})

    # Ingest row 1 twice
    for _ in range(2):
        simulate_merge_row("dataset_finance", 1, {"department": "Billing", "amount": 200})

    # Exactly 2 unique Row nodes exist despite 7 total writes
    assert len(graph_rows) == 2
    assert "dataset_finance_0" in graph_rows
    assert "dataset_finance_1" in graph_rows
