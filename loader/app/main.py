"""
Main entry point for the Loader service.
Orchestrates Neo4j connection, schema initialization,
and Kafka consumer loop.
"""
import sys
import signal
import logging
from .neo4j_writer import Neo4jWriter
from .kafka_consumer import KafkaConsumerService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("loader_main")


def main() -> None:
    logger.info("==================================================")
    logger.info("Starting Data In, Answers Out - Kafka Loader")
    logger.info("==================================================")

    # 1. Initialize Neo4j Writer & Schema
    writer = Neo4jWriter()
    try:
        writer.connect()
    except Exception as e:
        logger.error(f"FATAL: Failed to initialize Neo4j: {e}")
        sys.exit(1)

    # 2. Initialize Kafka Consumer Service
    consumer_service = KafkaConsumerService(writer=writer)

    # Setup signal handling for graceful shutdown
    def handle_signal(sig, frame):
        logger.info(f"Received signal {sig}. Initiating graceful shutdown...")
        consumer_service.stop()
        writer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # 3. Start Consumer loop
    try:
        consumer_service.connect()
        consumer_service.start()
    except Exception as e:
        logger.error(f"Loader service error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        consumer_service.stop()
        writer.close()
        logger.info("Loader service shutdown complete.")


if __name__ == "__main__":
    main()
