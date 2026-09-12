import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.kafka import kafka_manager
from app.neo4j import neo4j_manager
from app.models import HealthResponse
from app.ingest import router as ingest_router
from app.status import router as status_router
from app.chat import router as chat_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("member2.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Member 2 API service...")
    await kafka_manager.start()
    await neo4j_manager.connect()
    yield
    logger.info("Shutting down Member 2 API service...")
    await kafka_manager.stop()
    await neo4j_manager.close()

app = FastAPI(
    title="RISE @ RST #5 Hackathon - Member 2 Backend API",
    description="Member 2 API + Kafka service for CSV ingestion, status tracking, and grounded Cypher chat.",
    version="1.0.0",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler to prevent stack trace leaks
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."}
    )

# Include endpoint routers
app.include_router(ingest_router)
app.include_router(status_router)
app.include_router(chat_router)

@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check for API, Kafka, and Neo4j",
    description="Verifies reachability of Kafka cluster and Neo4j database."
)
async def health_check():
    kafka_ok = await kafka_manager.is_connected()
    neo4j_ok = await neo4j_manager.verify_connectivity()

    is_healthy = kafka_ok and neo4j_ok
    health_status = "ok" if is_healthy else "degraded"

    return HealthResponse(
        status=health_status,
        kafka_connected=kafka_ok,
        neo4j_connected=neo4j_ok
    )
