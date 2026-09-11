import os
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    KAFKA_TOPIC: str = os.getenv("KAFKA_TOPIC", "csv-rows")
    KAFKA_CLIENT_ID: str = os.getenv("KAFKA_CLIENT_ID", "member2-api")
    
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "csvgraphdb")
    NEO4J_DATABASE: str = os.getenv("NEO4J_DATABASE", "CSV_Graph_DB")
    
    MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_BYTES", "52428800"))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
