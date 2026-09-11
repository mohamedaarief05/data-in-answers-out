import json
import logging
import asyncio
from typing import Optional, Dict, Any
from aiokafka import AIOKafkaProducer
from app.config import settings

logger = logging.getLogger("member2.kafka")

class KafkaManager:
    def __init__(self):
        self.producer: Optional[AIOKafkaProducer] = None
        self.connected: bool = False

    async def start(self):
        try:
            self.producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                client_id=settings.KAFKA_CLIENT_ID,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                enable_idempotence=True,
                request_timeout_ms=5000
            )
            await self.producer.start()
            self.connected = True
            logger.info(f"Kafka producer connected to {settings.KAFKA_BOOTSTRAP_SERVERS}")
        except Exception as e:
            logger.error(f"Failed to start Kafka producer: {e}")
            self.connected = False

    async def stop(self):
        if self.producer:
            try:
                await self.producer.stop()
            except Exception as e:
                logger.error(f"Error stopping Kafka producer: {e}")
            finally:
                self.connected = False

    async def is_connected(self) -> bool:
        if not self.producer:
            return False
        try:
            await asyncio.wait_for(self.producer.client.fetch_all_metadata(), timeout=3.0)
            self.connected = True
            return True
        except Exception as e:
            logger.warning(f"Kafka connection check failed: {e}")
            self.connected = False
            return False

    async def publish_row(self, topic: str, key: str, payload: Dict[str, Any]) -> bool:
        if not self.producer:
            await self.start()
            if not self.producer:
                return False
        try:
            key_bytes = key.encode("utf-8") if key else None
            # Wait for Kafka acknowledgement
            await self.producer.send_and_wait(topic, value=payload, key=key_bytes)
            return True
        except Exception as e:
            logger.error(f"Failed to publish row to Kafka: {e}")
            return False

kafka_manager = KafkaManager()
