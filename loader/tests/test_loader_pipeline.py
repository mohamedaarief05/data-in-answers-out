"""
Tests for Kafka Consumer to Neo4j Loader Pipeline (TEST 1 and TEST 2).
"""
import pytest
from unittest.mock import MagicMock
from app.kafka_consumer import KafkaConsumerService
from app.neo4j_writer import Neo4jWriter


def test_kafka_message_reaches_loader_and_writes_to_neo4j():
    """
    TEST 1: Kafka message reaches Loader.
    TEST 2: Loader creates Dataset and Row in Neo4j.
    """
    mock_writer = MagicMock(spec=Neo4jWriter)
    mock_writer.write_row.return_value = True

    service = KafkaConsumerService(writer=mock_writer)

    # Valid message arriving from Kafka
    kafka_payload = {
        "dataset_id": "ds_demo",
        "job_id": "job_999",
        "row_index": 0,
        "data": {
            "Name": "Alice",
            "Department": "Billing",
            "City": "Chennai",
        },
    }

    # Step 1: Process message (simulating consumer receiving message from Kafka)
    processed = service.process_raw_message(kafka_payload)

    # Step 2: Verify success
    assert processed is True
    assert mock_writer.write_row.call_count == 1

    # Verify that the parsed CSVRowMessage has the expected properties
    saved_msg = mock_writer.write_row.call_args[0][0]
    assert saved_msg.dataset_id == "ds_demo"
    assert saved_msg.job_id == "job_999"
    assert saved_msg.row_index == 0
    assert saved_msg.stable_row_id == "ds_demo_0"
    assert saved_msg.data["Department"] == "Billing"
    assert saved_msg.data["City"] == "Chennai"


def test_malformed_kafka_message_fails_loudly():
    """
    Verifies that malformed rows are not silently ignored:
    Validation fails and returns False without crashing the service.
    """
    mock_writer = MagicMock(spec=Neo4jWriter)
    service = KafkaConsumerService(writer=mock_writer)

    # Missing dataset_id and row_index
    invalid_payload = {
        "job_id": "job_broken",
        "some_field": "val",
    }

    processed = service.process_raw_message(invalid_payload)

    # Must fail cleanly and not pass to writer
    assert processed is False
    assert mock_writer.write_row.call_count == 0


def test_flat_format_kafka_message():
    """
    Verifies compatibility with flat message format.
    """
    mock_writer = MagicMock(spec=Neo4jWriter)
    mock_writer.write_row.return_value = True
    service = KafkaConsumerService(writer=mock_writer)

    flat_payload = {
        "dataset_id": "ds_flat",
        "job_id": "job_flat_1",
        "row_index": 1,
        "Product": "Laptop",
        "Price": "1200",
    }

    processed = service.process_raw_message(flat_payload)
    assert processed is True
    saved_msg = mock_writer.write_row.call_args[0][0]
    assert saved_msg.stable_row_id == "ds_flat_1"
    props = saved_msg.get_sanitized_properties()
    assert props["product"] == "Laptop"
    assert props["price"] == 1200


class MockRecord:
    """Mock Kafka ConsumerRecord for testing manual commits."""
    def __init__(self, topic: str, partition: int, offset: int, value: dict):
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.value = value


def test_successful_neo4j_write_commits_kafka_offset():
    """
    Verifies that when Neo4j write succeeds, the Kafka offset IS committed.
    """
    mock_writer = MagicMock(spec=Neo4jWriter)
    mock_writer.write_row.return_value = True

    service = KafkaConsumerService(writer=mock_writer)
    mock_consumer = MagicMock()
    service.consumer = mock_consumer

    record = MockRecord(
        topic="csv-rows",
        partition=0,
        offset=105,
        value={"dataset_id": "ds_test", "job_id": "job_1", "row_index": 0, "Name": "Alice"}
    )

    result = service.process_record(record)

    assert result is True
    assert mock_writer.write_row.call_count == 1
    # Verify Kafka commit was called
    assert mock_consumer.commit.call_count == 1
    commit_args = mock_consumer.commit.call_args[0][0]
    tp = list(commit_args.keys())[0]
    assert tp.topic == "csv-rows"
    assert tp.partition == 0
    assert commit_args[tp].offset == 106  # record.offset + 1


def test_failed_neo4j_write_does_not_commit_kafka_offset():
    """
    Verifies that when Neo4j write fails, the Kafka offset is NOT committed,
    allowing the message to be safely re-processed.
    """
    mock_writer = MagicMock(spec=Neo4jWriter)
    mock_writer.write_row.return_value = False  # Neo4j write failed

    service = KafkaConsumerService(writer=mock_writer)
    mock_consumer = MagicMock()
    service.consumer = mock_consumer

    record = MockRecord(
        topic="csv-rows",
        partition=0,
        offset=105,
        value={"dataset_id": "ds_test", "job_id": "job_1", "row_index": 0, "Name": "Alice"}
    )

    result = service.process_record(record)

    assert result is False
    assert mock_writer.write_row.call_count == 1
    # Offset must NOT be committed
    assert mock_consumer.commit.call_count == 0


def test_malformed_message_does_not_commit_kafka_offset():
    """
    Verifies that malformed messages that fail validation do NOT commit offsets.
    """
    mock_writer = MagicMock(spec=Neo4jWriter)
    service = KafkaConsumerService(writer=mock_writer)
    mock_consumer = MagicMock()
    service.consumer = mock_consumer

    record = MockRecord(
        topic="csv-rows",
        partition=0,
        offset=200,
        value={"invalid": "payload"}
    )

    result = service.process_record(record)

    assert result is False
    assert mock_writer.write_row.call_count == 0
    assert mock_consumer.commit.call_count == 0


def test_neo4j_success_but_kafka_commit_fails_returns_false():
    """
    Verifies that if Neo4j write succeeds but the Kafka commit fails:
    1. commit_offset returns False
    2. process_record returns False
    3. The error is handled gracefully and logged
    """
    mock_writer = MagicMock(spec=Neo4jWriter)
    mock_writer.write_row.return_value = True

    service = KafkaConsumerService(writer=mock_writer)
    mock_consumer = MagicMock()
    mock_consumer.commit.side_effect = Exception("Kafka commit error")
    service.consumer = mock_consumer

    record = MockRecord(
        topic="csv-rows",
        partition=0,
        offset=300,
        value={"dataset_id": "ds_test", "job_id": "job_1", "row_index": 0, "Name": "Alice"}
    )

    # Directly verify commit_offset returns False on error
    assert service.commit_offset(record) is False

    # Verify process_record returns False when commit fails
    result = service.process_record(record)
    assert result is False
    assert mock_writer.write_row.call_count == 1


