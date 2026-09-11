import re
import logging
from fastapi import APIRouter, status
from app.models import ChatRequest, ChatResponse
from app.neo4j import neo4j_manager

logger = logging.getLogger("member2.chat")
router = APIRouter()

@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Data chatbot query endpoint",
    description="Grounded template-based Cypher querying over Neo4j dataset and row graph."
)
async def chat_query(request: ChatRequest):
    q_lower = request.question.strip().lower()

    # Rule 1: "How many rows are there?" or count rows query
    if any(phrase in q_lower for phrase in ["how many rows", "count rows", "total rows", "number of rows"]):
        cypher = "MATCH (r:Row) RETURN count(r) AS count"
        results = await neo4j_manager.execute_read_query(cypher)
        if results and len(results) > 0 and "count" in results[0]:
            count = results[0]["count"]
            return ChatResponse(
                answer=f"There are {count} rows in total.",
                cypher=cypher,
                result=results,
                grounded=True
            )
        else:
            return ChatResponse(
                answer="There are 0 rows in total.",
                cypher=cypher,
                result=[{"count": 0}],
                grounded=True
            )

    # Rule 2: "How many datasets are there?" or count datasets query
    if any(phrase in q_lower for phrase in ["how many datasets", "count datasets", "total datasets", "number of datasets"]):
        cypher = "MATCH (d:Dataset) RETURN count(d) AS count"
        results = await neo4j_manager.execute_read_query(cypher)
        if results and len(results) > 0 and "count" in results[0]:
            count = results[0]["count"]
            return ChatResponse(
                answer=f"There are {count} datasets in total.",
                cypher=cypher,
                result=results,
                grounded=True
            )
        else:
            return ChatResponse(
                answer="There are 0 datasets in total.",
                cypher=cypher,
                result=[{"count": 0}],
                grounded=True
            )

    # Rule 3: Show rows from dataset <dataset_id>
    # Match dataset_id (24 hex characters or pattern in question)
    dataset_match = re.search(r'\b([a-f0-9]{24})\b', q_lower)
    if not dataset_match:
        # Check for dataset pattern after 'dataset' keyword
        dataset_match = re.search(r'dataset\s+([a-zA-Z0-9_-]+)', q_lower)

    if dataset_match and ("show" in q_lower or "rows" in q_lower or "list" in q_lower or "get" in q_lower):
        target_dataset_id = dataset_match.group(1)
        cypher = "MATCH (r:Row {dataset_id: $dataset_id}) RETURN r ORDER BY r.row_index LIMIT 100"
        results = await neo4j_manager.execute_read_query(cypher, {"dataset_id": target_dataset_id})
        
        if results:
            return ChatResponse(
                answer=f"Found {len(results)} rows for dataset '{target_dataset_id}'.",
                cypher=cypher,
                result=results,
                grounded=True
            )
        else:
            return ChatResponse(
                answer=f"No rows found for dataset '{target_dataset_id}'.",
                cypher=cypher,
                result=[],
                grounded=True
            )

    # Rule 4: Unsupported question fallback
    return ChatResponse(
        answer="I don't have that in the data.",
        cypher="",
        result=[],
        grounded=False
    )
