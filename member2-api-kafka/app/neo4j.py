import logging
import asyncio
from typing import Optional, List, Dict, Any
from neo4j import AsyncGraphDatabase, AsyncDriver
from app.config import settings

logger = logging.getLogger("member2.neo4j")

class Neo4jManager:
    def __init__(self):
        self.driver: Optional[AsyncDriver] = None
        self.connected: bool = False

    async def connect(self):
        try:
            self.driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            await self.verify_connectivity()
            logger.info(f"Connected to Neo4j at {settings.NEO4J_URI}")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self.connected = False

    async def close(self):
        if self.driver:
            try:
                await self.driver.close()
            except Exception as e:
                logger.error(f"Error closing Neo4j driver: {e}")
            finally:
                self.connected = False

    async def verify_connectivity(self) -> bool:
        if not self.driver:
            return False
        try:
            await asyncio.wait_for(self.driver.verify_connectivity(), timeout=3.0)
            self.connected = True
            return True
        except Exception as e:
            logger.warning(f"Neo4j connectivity check failed: {e}")
            self.connected = False
            return False

    async def get_loaded_rows_count(self, dataset_id: str) -> int:
        if not self.driver:
            return 0
        query = "MATCH (r:Row {dataset_id: $dataset_id}) RETURN count(r) AS count"
        try:
            async with self.driver.session(database=settings.NEO4J_DATABASE) as session:
                result = await session.run(query, dataset_id=dataset_id)
                record = await result.single()
                if record:
                    return record["count"]
                return 0
        except Exception as e:
            logger.error(f"Error querying Neo4j loaded rows count for dataset {dataset_id}: {e}")
            return 0

    def _serialize_value(self, val: Any) -> Any:
        if isinstance(val, dict):
            return {k: self._serialize_value(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [self._serialize_value(v) for v in val]
        elif hasattr(val, "isoformat"):
            return val.isoformat()
        elif hasattr(val, "items"):
            return {k: self._serialize_value(v) for k, v in dict(val).items()}
        elif type(val).__name__ in ("DateTime", "Date", "Time", "Duration", "Point"):
            return str(val)
        return val

    async def execute_read_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if not self.driver:
            return []
        if params is None:
            params = {}
        records_data = []
        try:
            async with self.driver.session(database=settings.NEO4J_DATABASE) as session:
                result = await session.run(query, parameters=params)
                async for record in result:
                    raw_dict = record.data()
                    clean_dict = self._serialize_value(raw_dict)
                    records_data.append(clean_dict)
            return records_data
        except Exception as e:
            logger.error(f"Error executing Cypher query '{query}': {e}")
            return []

neo4j_manager = Neo4jManager()
