"""
Kafka Consumer Service.
Subscribes to topic 'csv-rows', deserializes JSON messages,
validates them into CSVRowMessage models, and feeds them into Neo4jWriter.
"""
import os
import json
import time
import logging
import signal
from typing import Optional, Callable
from kafka import KafkaConsumer, TopicPartition, OffsetAndMetadata
from .models import CSVRowMessage
from .neo4j_writer import Neo4jWriter

logger = logging.getLogger("kafka_consumer")


class KafkaConsumerService:
    """
    Consumes CSV row messages from Kafka and writes them to Neo4j.
    Includes connection retry logic, manual offset commit on success, and clear logging.
    """

    def __init__(
        self,
        writer: Neo4jWriter,
        bootstrap_servers: Optional[str] = None,
        topic: Optional[str] = None,
        group_id: Optional[str] = None,
        auto_offset_reset: Optional[str] = None,
        max_retries: int = 15,
        retry_delay_seconds: float = 3.0,
    ):
        self.writer = writer
        self.bootstrap_servers = bootstrap_servers or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
        )
        self.topic = topic or os.getenv("KAFKA_TOPIC", "csv-rows")
        self.group_id = group_id or os.getenv("KAFKA_GROUP_ID", "loader-group")
        self.auto_offset_reset = auto_offset_reset or os.getenv(
            "KAFKA_AUTO_OFFSET_RESET", "earliest"
        )
        self.max_retries = max_retries
        self.retry_delay = retry_delay_seconds

        self.consumer: Optional[KafkaConsumer] = None
        self.running = False

    def connect(self) -> None:
        """
        Connects to Kafka broker with retries (critical for docker startup order).
        """
        attempt = 0
        last_error = None

        while attempt < self.max_retries:
            try:
                attempt += 1
                logger.info(
                    f"Connecting to Kafka brokers at {self.bootstrap_servers} "
                    f"(topic: '{self.topic}', attempt {attempt}/{self.max_retries})..."
                )
                self.consumer = KafkaConsumer(
                    self.topic,
                    bootstrap_servers=self.bootstrap_servers.split(","),
                    group_id=self.group_id,
                    auto_offset_reset=self.auto_offset_reset,
                    enable_auto_commit=False,
                    value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                    consumer_timeout_ms=1000,  # Poll timeout in ms
                )
                logger.info(f"Successfully subscribed to Kafka topic: {self.topic}")
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Kafka connection attempt {attempt} failed: {e}. "
                    f"Retrying in {self.retry_delay}s..."
                )
                time.sleep(self.retry_delay)

        raise ConnectionError(
            f"Failed to connect to Kafka brokers at {self.bootstrap_servers} "
            f"after {self.max_retries} attempts. Last error: {last_error}"
        )

    def commit_offset(self, record=None) -> bool:
        """
        Manually commits Kafka offset after successful write to Neo4j.
        If record is provided, commits partition offset (record.offset + 1).
        Otherwise commits latest retrieved offset.
        Returns True if commit succeeds, False otherwise.
        """
        if not self.consumer:
            logger.warning("Cannot commit offset: consumer is not initialized.")
            return False
        try:
            if (
                record is not None
                and hasattr(record, "topic")
                and hasattr(record, "partition")
                and hasattr(record, "offset")
            ):
                tp = TopicPartition(record.topic, record.partition)
                self.consumer.commit({tp: OffsetAndMetadata(record.offset + 1, "")})
            else:
                self.consumer.commit()
            logger.debug(
                f"Committed offset for partition {getattr(record, 'partition', 'all')}, "
                f"offset {getattr(record, 'offset', 'latest')}"
            )
            return True
        except Exception as commit_err:
            logger.error(f"Failed to commit Kafka offset: {commit_err}")
            return False

    def process_raw_message(self, raw_value: dict) -> bool:
        """
        Validates raw dictionary into CSVRowMessage and writes to Neo4j.
        Logs failure if the row cannot be validated or written.
        """
        try:
            message = CSVRowMessage.model_validate(raw_value)
        except Exception as val_err:
            logger.error(
                f"[VALIDATION FAILED] Could not parse Kafka message payload: {val_err}. "
                f"Payload: {raw_value}"
            )
            return False

        # Write to Neo4j
        return self.writer.write_row(message)

    def process_record(self, record) -> bool:
        """
        Processes a single Kafka ConsumerRecord:
        1. Validates and writes row to Neo4j.
        2. If Neo4j processing fails, return False and do not commit.
        3. If Neo4j succeeds, call commit_offset(record).
        4. If the Kafka commit succeeds, return True.
        5. If the Kafka commit fails, return False and log that the message
           was written to Neo4j but its Kafka offset was not committed.
        """
        neo4j_success = self.process_raw_message(record.value)
        if not neo4j_success:
            logger.warning(
                f"Processing failed for message at partition {getattr(record, 'partition', '?')}, "
                f"offset {getattr(record, 'offset', '?')}. Offset will NOT be committed."
            )
            return False

        commit_success = self.commit_offset(record)
        if commit_success:
            return True
        else:
            logger.error(
                f"Message at partition {getattr(record, 'partition', '?')}, "
                f"offset {getattr(record, 'offset', '?')} was successfully written to Neo4j, "
                f"but its Kafka offset was NOT committed."
            )
            return False

    def start(self, on_message_processed: Optional[Callable[[bool], None]] = None) -> None:
        """
        Starts the continuous message consumption loop with manual offset commits.
        """
        if not self.consumer:
            self.connect()

        self.running = True
        logger.info(f"Loader consumer loop started for topic '{self.topic}'. Waiting for messages...")

        try:
            while self.running:
                # Consumer timeout allows periodic checking of self.running
                for record in self.consumer:
                    if not self.running:
                        break

                    logger.debug(
                        f"Received Kafka message from partition {record.partition}, offset {record.offset}"
                    )
                    success = self.process_record(record)
                    if on_message_processed:
                        on_message_processed(success)

        except Exception as e:
            if self.running:
                logger.error(f"Unexpected error in consumer loop: {e}", exc_info=True)
                raise
        finally:
            self.stop()

    def stop(self) -> None:
        """Gracefully stops the Kafka consumer."""
        self.running = False
        if self.consumer:
            try:
                self.consumer.close()
                logger.info("Kafka consumer closed.")
            except Exception as e:
                logger.warning(f"Error while closing Kafka consumer: {e}")
            self.consumer = None
