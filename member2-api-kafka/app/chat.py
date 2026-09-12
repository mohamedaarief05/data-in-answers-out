import re
import logging
from typing import Dict, Any, List, Optional, Tuple
from fastapi import APIRouter, status
from app.models import ChatRequest, ChatResponse
from app.neo4j import neo4j_manager

logger = logging.getLogger("member2.chat")
router = APIRouter()

UNGROUNDED_ANSWER = "I don't have that in the data."

ORDINAL_MAP = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10
}

INTERNAL_KEYS = {'id', 'dataset_id', 'job_id', 'row_index', 'created_at', 'updated_at', 'is_new'}


def format_row_properties(result_record: Dict[str, Any]) -> str:
    if "r" in result_record and isinstance(result_record["r"], dict):
        props = result_record["r"]
    elif isinstance(result_record, dict):
        props = result_record
    else:
        props = {}
    clean_props = {}
    for k, v in props.items():
        if k in INTERNAL_KEYS:
            continue
        display_k = "id" if k == "csv_id" else k
        clean_props[display_k] = v

    if not clean_props:
        clean_props = props
    return ", ".join(f"{k}='{v}'" if isinstance(v, str) else f"{k}={v}" for k, v in clean_props.items())


async def get_discovered_columns(dataset_id: Optional[str] = None) -> List[str]:
    if dataset_id:
        cypher = """MATCH (r:Row {dataset_id: $dataset_id})
UNWIND keys(r) AS key
WITH DISTINCT key
WHERE NOT key IN ['id', 'dataset_id', 'job_id', 'row_index', 'created_at', 'updated_at', 'is_new']
RETURN key AS column
ORDER BY column"""
        results = await neo4j_manager.execute_read_query(cypher, {"dataset_id": dataset_id})
    else:
        cypher = """MATCH (r:Row)
UNWIND keys(r) AS key
WITH DISTINCT key
WHERE NOT key IN ['id', 'dataset_id', 'job_id', 'row_index', 'created_at', 'updated_at', 'is_new']
RETURN key AS column
ORDER BY column"""
        results = await neo4j_manager.execute_read_query(cypher)
    return [r["column"] for r in results if "column" in r]


async def resolve_active_dataset_id(q_lower: str) -> Tuple[Optional[str], List[str]]:
    cypher_datasets = """MATCH (r:Row)
RETURN r.dataset_id AS dataset_id, coalesce(max(r.updated_at), max(r.created_at)) AS latest_time
ORDER BY latest_time DESC, dataset_id ASC"""
    res = await neo4j_manager.execute_read_query(cypher_datasets)
    available_dataset_ids = [r["dataset_id"] for r in res if "dataset_id" in r and r["dataset_id"]]

    if not available_dataset_ids:
        return None, []

    if len(available_dataset_ids) == 1:
        return available_dataset_ids[0], available_dataset_ids

    # Check if prompt specifies a specific dataset ID from the available ones
    for ds_id in available_dataset_ids:
        if ds_id.lower() in q_lower:
            return ds_id, available_dataset_ids

    # Check if prompt contains hex/alphanumeric dataset ID pattern
    dataset_match = re.search(r'\b([a-f0-9]{24}|ds_[a-zA-Z0-9_]+)\b', q_lower)
    if dataset_match and dataset_match.group(1) in available_dataset_ids:
        return dataset_match.group(1), available_dataset_ids

    # Default to the most recently created/ingested dataset
    return available_dataset_ids[0], available_dataset_ids


@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Data chatbot query endpoint",
    description="Grounded template-based Cypher querying over Neo4j dataset and row graph."
)
async def chat_query(request: ChatRequest):
    q_lower = request.question.strip().lower()
    if not q_lower:
        return ChatResponse(
            answer=UNGROUNDED_ANSWER,
            cypher="",
            result=[],
            grounded=False
        )

    # Dynamically resolve dataset_id from Neo4j without manual input or hardcoding
    target_dataset_id, available_datasets = await resolve_active_dataset_id(q_lower)

    # Rule 1: Dataset count & general dataset check
    if any(phrase in q_lower for phrase in ["how many datasets", "count datasets", "total datasets", "number of datasets"]):
        cypher = "MATCH (r:Row) RETURN count(DISTINCT r.dataset_id) AS count"
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

    # Handle cases where no Row nodes exist in Neo4j
    if not available_datasets:
        return ChatResponse(
            answer=UNGROUNDED_ANSWER,
            cypher="MATCH (r:Row) RETURN DISTINCT r.dataset_id AS dataset_id ORDER BY dataset_id",
            result=[],
            grounded=False
        )

    # Handle multiple datasets if target not identified
    if not target_dataset_id and len(available_datasets) > 1:
        return ChatResponse(
            answer="I found multiple datasets in the data. Please specify which dataset you want to use.",
            cypher="MATCH (r:Row) RETURN DISTINCT r.dataset_id AS dataset_id ORDER BY dataset_id",
            result=[{"dataset_id": d} for d in available_datasets],
            grounded=False
        )

    # -------------------------------------------------------------
    # Rule 2: Total row count / Dataset row count / Filtered count queries
    # -------------------------------------------------------------
    if any(phrase in q_lower for phrase in ["how many rows", "count rows", "total rows", "number of rows"]):
        # Extract potential filter after 'in', 'for', 'where', 'with'
        filter_match = re.search(r'(?:how\s+many\s+rows|count\s+rows|number\s+of\s+rows)\s+(?:are\s+)?(?:in|for|where|with)\s+(.+)$', q_lower)
        filter_term = filter_match.group(1).strip().rstrip("?.!,") if filter_match else None

        generic_terms = {"total", "the total", "dataset", "the dataset", "data", "the data", "database", "the database", "all", "rows"}
        if filter_term and filter_term.lower() not in generic_terms:
            cypher = """MATCH (r:Row {dataset_id: $dataset_id})
WHERE any(k IN keys(r) WHERE NOT k IN ['id', 'dataset_id', 'job_id', 'row_index', 'created_at', 'updated_at', 'is_new'] AND toLower(toString(r[k])) = toLower($search_term))
RETURN count(r) AS count"""
            params = {"dataset_id": target_dataset_id, "search_term": filter_term}
            results = await neo4j_manager.execute_read_query(cypher, params)
            if results and len(results) > 0 and results[0].get("count", 0) > 0:
                count = results[0]["count"]
                return ChatResponse(
                    answer=f"There are {count} rows where data matches '{filter_term}'.",
                    cypher=cypher,
                    result=results,
                    grounded=True
                )
            else:
                return ChatResponse(
                    answer=UNGROUNDED_ANSWER,
                    cypher=cypher,
                    result=[],
                    grounded=False
                )

        if "across all" in q_lower or "total rows in database" in q_lower:
            cypher = "MATCH (r:Row) RETURN count(r) AS count"
            params = {}
        else:
            cypher = "MATCH (r:Row {dataset_id: $dataset_id}) RETURN count(r) AS count"
            params = {"dataset_id": target_dataset_id}

        results = await neo4j_manager.execute_read_query(cypher, params)
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

    # -------------------------------------------------------------
    # Rule 3: Column discovery questions ("What columns are available?", "List columns", etc.)
    # -------------------------------------------------------------
    if any(phrase in q_lower for phrase in [
        "what columns", "list columns", "list the columns", "available columns",
        "what fields", "list fields", "what information is stored", "what information is available",
        "what departments are available", "departments are available"
    ]):
        columns = await get_discovered_columns(target_dataset_id)
        cypher = """MATCH (r:Row {dataset_id: $dataset_id})
UNWIND keys(r) AS key
WITH DISTINCT key
WHERE NOT key IN ['id', 'dataset_id', 'job_id', 'row_index', 'created_at', 'updated_at', 'is_new']
RETURN key AS column
ORDER BY column"""
        if columns:
            return ChatResponse(
                answer=f"Available columns in the dataset: {', '.join(columns)}.",
                cypher=cypher,
                result=[{"column": c} for c in columns],
                grounded=True
            )
        else:
            return ChatResponse(
                answer=UNGROUNDED_ANSWER,
                cypher=cypher,
                result=[],
                grounded=False
            )

    # -------------------------------------------------------------
    # Rule 4: First Row query ("Show me the first row", "What is the first row", etc.)
    # -------------------------------------------------------------
    if re.search(r'\b(first row|first record)\b', q_lower) or re.search(r'\bfirst\s+row\b', q_lower):
        cypher = "MATCH (r:Row {dataset_id: $dataset_id}) RETURN r ORDER BY r.row_index ASC LIMIT 1"
        params = {"dataset_id": target_dataset_id}

        results = await neo4j_manager.execute_read_query(cypher, params)
        if results and len(results) > 0:
            formatted = format_row_properties(results[0])
            return ChatResponse(
                answer=f"First row: {formatted}.",
                cypher=cypher,
                result=results,
                grounded=True
            )
        else:
            return ChatResponse(
                answer=UNGROUNDED_ANSWER,
                cypher=cypher,
                result=[],
                grounded=False
            )

    # -------------------------------------------------------------
    # Rule 5: Last Row query ("Show me the last row", "What is the last row", etc.)
    # -------------------------------------------------------------
    if re.search(r'\b(last row|last record)\b', q_lower) or re.search(r'\blast\s+row\b', q_lower):
        cypher = "MATCH (r:Row {dataset_id: $dataset_id}) RETURN r ORDER BY r.row_index DESC LIMIT 1"
        params = {"dataset_id": target_dataset_id}

        results = await neo4j_manager.execute_read_query(cypher, params)
        if results and len(results) > 0:
            formatted = format_row_properties(results[0])
            return ChatResponse(
                answer=f"Last row: {formatted}.",
                cypher=cypher,
                result=results,
                grounded=True
            )
        else:
            return ChatResponse(
                answer=UNGROUNDED_ANSWER,
                cypher=cypher,
                result=[],
                grounded=False
            )

    # -------------------------------------------------------------
    # Rule 6: Specific Row query ("Show me row 3", "Show me the third row", "Give me record 4")
    # -------------------------------------------------------------
    row_num = None
    digit_match = re.search(r'\b(?:row|record)\s+(\d+)\b', q_lower)
    if not digit_match:
        digit_match = re.search(r'\b(\d+)(?:st|nd|rd|th)?\s+(?:row|record)\b', q_lower)
    if digit_match:
        try:
            row_num = int(digit_match.group(1))
        except ValueError:
            pass

    if row_num is None:
        ordinal_match = re.search(r'\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+(?:row|record)\b', q_lower)
        if ordinal_match:
            word = ordinal_match.group(1)
            row_num = ORDINAL_MAP.get(word)

    if row_num is not None:
        cypher = "MATCH (r:Row {dataset_id: $dataset_id, row_index: $row_index}) RETURN r"
        params = {"dataset_id": target_dataset_id, "row_index": row_num}

        results = await neo4j_manager.execute_read_query(cypher, params)
        if results and len(results) > 0:
            formatted = format_row_properties(results[0])
            return ChatResponse(
                answer=f"Row {row_num}: {formatted}.",
                cypher=cypher,
                result=results,
                grounded=True
            )
        else:
            return ChatResponse(
                answer=UNGROUNDED_ANSWER,
                cypher=cypher,
                result=[],
                grounded=False
            )

    # -------------------------------------------------------------
    # Rule 7: Column Value queries ("Show me the name column", "values in city column", etc.)
    # -------------------------------------------------------------
    if any(k in q_lower for k in ["column", "values in"]):
        discovered_cols = await get_discovered_columns(target_dataset_id)
        matched_col = None
        for col in discovered_cols:
            pattern = r'\b' + re.escape(col.lower()) + r'\b'
            if re.search(pattern, q_lower):
                matched_col = col
                break

        if matched_col:
            cypher = f"MATCH (r:Row {{dataset_id: $dataset_id}}) WHERE r.{matched_col} IS NOT NULL RETURN r.{matched_col} AS value, r.row_index AS row_index ORDER BY r.row_index LIMIT 100"
            params = {"dataset_id": target_dataset_id}

            results = await neo4j_manager.execute_read_query(cypher, params)
            if results:
                val_strings = [str(r["value"]) for r in results if "value" in r]
                return ChatResponse(
                    answer=f"Values in '{matched_col}' column: {', '.join(val_strings)}.",
                    cypher=cypher,
                    result=results,
                    grounded=True
                )
            else:
                return ChatResponse(
                    answer=UNGROUNDED_ANSWER,
                    cypher=cypher,
                    result=[],
                    grounded=False
                )

    # -------------------------------------------------------------
    # Rule 8: Entity / Word Lookup ("What is Arun?", "Tell me about Billing", "Who is Arun?", etc.)
    # Dynamic property value search across all CSV columns with zero Cypher injection!
    # -------------------------------------------------------------
    search_term = None
    inquiry_match = re.search(
        r'^(?:what\s+is|who\s+is|tell\s+me\s+about|show\s+me\s+(?:information\s+about|details\s+(?:for|about)|info\s+about)?|what\s+do\s+you\s+know\s+about|information\s+(?:on|about)|details\s+(?:on|for)|find|search\s+for)\s+(?:a\s+|the\s+)?(.+?)\??$',
        q_lower,
        re.IGNORECASE
    )
    if inquiry_match:
        search_term = inquiry_match.group(1).strip().rstrip("?.!,")

    if not search_term and len(q_lower.split()) <= 4 and not any(k in q_lower for k in ["how many", "list", "show", "count"]):
        search_term = q_lower.strip().rstrip("?.!,")

    if search_term and search_term not in ["rows", "datasets", "data", "database", "columns"]:
        cypher = """MATCH (r:Row {dataset_id: $dataset_id})
WHERE any(k IN keys(r) WHERE NOT k IN ['id', 'dataset_id', 'job_id', 'row_index', 'created_at', 'updated_at', 'is_new'] AND toLower(toString(r[k])) = toLower($search_term))
RETURN r ORDER BY r.row_index LIMIT 10"""
        params = {"dataset_id": target_dataset_id, "search_term": search_term}

        results = await neo4j_manager.execute_read_query(cypher, params)

        if not results:
            cypher = """MATCH (r:Row {dataset_id: $dataset_id})
WHERE any(k IN keys(r) WHERE NOT k IN ['id', 'dataset_id', 'job_id', 'row_index', 'created_at', 'updated_at', 'is_new'] AND toLower(toString(r[k])) CONTAINS toLower($search_term))
RETURN r ORDER BY r.row_index LIMIT 10"""
            params = {"dataset_id": target_dataset_id, "search_term": search_term}

            results = await neo4j_manager.execute_read_query(cypher, params)

        if results:
            records_str = "; ".join(f"[{idx+1}] {format_row_properties(rec)}" for idx, rec in enumerate(results[:3]))
            return ChatResponse(
                answer=f"Found {len(results)} matching records for '{search_term}': {records_str}.",
                cypher=cypher,
                result=results,
                grounded=True
            )
        elif inquiry_match:
            return ChatResponse(
                answer=UNGROUNDED_ANSWER,
                cypher=cypher,
                result=[],
                grounded=False
            )

    # -------------------------------------------------------------
    # Rule 9: Show rows for dataset
    # -------------------------------------------------------------
    if "show" in q_lower or "rows" in q_lower or "list" in q_lower or "get" in q_lower:
        cypher = "MATCH (r:Row {dataset_id: $dataset_id}) RETURN r ORDER BY r.row_index LIMIT 100"
        results = await neo4j_manager.execute_read_query(cypher, {"dataset_id": target_dataset_id})

        if results:
            return ChatResponse(
                answer=f"Found {len(results)} rows for dataset '{target_dataset_id}'.",
                cypher=cypher,
                result=results,
                grounded=True
            )

    # -------------------------------------------------------------
    # Rule 10: Unsupported question fallback
    # -------------------------------------------------------------
    return ChatResponse(
        answer=UNGROUNDED_ANSWER,
        cypher="",
        result=[],
        grounded=False
    )


