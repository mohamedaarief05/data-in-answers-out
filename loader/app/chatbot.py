"""
Grounded Chatbot Module for Data In, Answers Out.
Answers strictly from Neo4j graph data. Never uses outside/general knowledge.
Uses deterministic question-to-Cypher templates with parameterized queries.
"""
import re
import logging
from typing import Dict, Any, Optional, List, Tuple
# pyrefly: ignore [missing-import]
from neo4j import Session
from .models import ChatbotResponse, sanitize_property_key
from .neo4j_writer import Neo4jWriter

logger = logging.getLogger("chatbot")

UNGROUNDED_ANSWER = "I don't have that in the data."


class GroundedChatbot:
    """
    Deterministic question-to-Cypher chatbot grounded entirely in Neo4j.
    """

    def __init__(self, writer: Neo4jWriter):
        self.writer = writer

    def get_available_properties(self) -> List[str]:
        """
        Dynamically discovers all active property keys on Row nodes in Neo4j.
        """
        try:
            return self.writer.get_all_properties_for_rows()
        except Exception as e:
            logger.warning(f"Could not retrieve Row properties from Neo4j: {e}")
            return []

    def find_property_and_count_for_value(
        self, value: str, candidate_properties: List[str]
    ) -> Optional[Tuple[str, int]]:
        """
        Given a value (e.g. 'Billing' or 'Chennai'), determines which property in
        Neo4j contains this value by querying the database.
        Returns (property_name, count) if found, else None.
        """
        if not candidate_properties or not value:
            return None

        with self.writer.get_session() as session:
            for prop in candidate_properties:
                # Safe parameterized check for each property
                query = f"""
                MATCH (r:Row)
                WHERE toLower(toString(r.{prop})) = toLower($val)
                RETURN count(r) AS c
                """
                try:
                    result = session.run(query, {"val": value})
                    record = result.single()
                    if record and record["c"] > 0:
                        return prop, record["c"]
                except Exception as e:
                    logger.debug(f"Error checking property {prop}: {e}")
                    continue

        return None

    def ask(self, question: str) -> ChatbotResponse:
        """
        Processes a user question, maps to parameterized Cypher if applicable,
        executes against Neo4j, and returns a grounded response.
        If the question cannot be grounded in Neo4j, refuses with UNGROUNDED_ANSWER.
        """
        cleaned_question = question.strip()
        if not cleaned_question:
            return ChatbotResponse(
                answer=UNGROUNDED_ANSWER,
                cypher=None,
                result=None,
                grounded=False,
            )

        active_properties = self.get_available_properties()

        # -------------------------------------------------------------
        # 1. Total row count queries:
        # e.g., "How many rows are in the database?", "How many rows total?", "How many rows?"
        # -------------------------------------------------------------
        if re.search(
            r"\b(how many rows( are)?( there)?( in (the )?(database|dataset|table|graph|total))?|how many total rows|count (all )?rows|total rows|how many records)\b\??$",
            cleaned_question,
            re.IGNORECASE,
        ):
            cypher = "MATCH (r:Row) RETURN count(r) AS count"
            with self.writer.get_session() as session:
                res = session.run(cypher)
                rec = res.single()
                total = rec["count"] if rec else 0

            if total > 0:
                return ChatbotResponse(
                    answer=f"There are {total} total rows in the data.",
                    cypher=cypher,
                    result={"count": total},
                    grounded=True,
                )
            else:
                return ChatbotResponse(
                    answer=UNGROUNDED_ANSWER,
                    cypher=cypher,
                    result={"count": 0},
                    grounded=False,
                )

        # -------------------------------------------------------------
        # 2. List datasets query:
        # e.g., "What datasets are there?", "List datasets", "Show datasets"
        # -------------------------------------------------------------
        if re.search(r"\b(what|list|show)\s+datasets\b", cleaned_question, re.IGNORECASE):
            cypher = (
                "MATCH (d:Dataset) OPTIONAL MATCH (d)-[:HAS_ROW]->(r:Row) "
                "RETURN d.id AS dataset_id, count(r) AS row_count"
            )
            with self.writer.get_session() as session:
                res = session.run(cypher)
                records = [dict(record) for record in res]

            if records:
                summary = ", ".join(f"'{r['dataset_id']}' ({r['row_count']} rows)" for r in records)
                return ChatbotResponse(
                    answer=f"Datasets available in Neo4j: {summary}.",
                    cypher=cypher,
                    result=records,
                    grounded=True,
                )
            else:
                return ChatbotResponse(
                    answer=UNGROUNDED_ANSWER,
                    cypher=cypher,
                    result=[],
                    grounded=False,
                )

        # -------------------------------------------------------------
        # 3. Explicit property queries:
        # e.g. "How many rows have department Billing?",
        #      "How many rows where city is Chennai?"
        # -------------------------------------------------------------
        explicit_prop_match = re.search(
            r"(?:how many rows|count rows)\s+(?:have|where|with)\s+([a-zA-Z0-9_ ]+?)\s+(?:is|=|as)?\s*['\"]?([a-zA-Z0-9_ ]+?)['\"]?\??$",
            cleaned_question,
            re.IGNORECASE,
        )
        if explicit_prop_match:
            raw_prop = explicit_prop_match.group(1).strip()
            raw_val = explicit_prop_match.group(2).strip().rstrip("?.!,")
            sanitized_prop = sanitize_property_key(raw_prop)

            if sanitized_prop in active_properties:
                cypher = (
                    f"MATCH (r:Row) "
                    f"WHERE toLower(toString(r.{sanitized_prop})) = toLower($val) "
                    f"RETURN count(r) AS count"
                )
                params = {"val": raw_val}
                with self.writer.get_session() as session:
                    res = session.run(cypher, params)
                    rec = res.single()
                    count = rec["count"] if rec else 0

                if count > 0:
                    return ChatbotResponse(
                        answer=f"There are {count} rows where {sanitized_prop} is '{raw_val}'.",
                        cypher=cypher,
                        result={"count": count, "property": sanitized_prop, "value": raw_val},
                        grounded=True,
                    )
                else:
                    return ChatbotResponse(
                        answer=UNGROUNDED_ANSWER,
                        cypher=cypher,
                        result={"count": 0},
                        grounded=False,
                    )

        # -------------------------------------------------------------
        # 4. Value-in-location/department query:
        # e.g., "How many rows are in Billing?", "How many rows are in Chennai?"
        # -------------------------------------------------------------
        count_in_match = re.search(
            r"(?:how many rows(?: are)?|count rows)\s+in\s+['\"]?([a-zA-Z0-9_ ]+?)['\"]?\??$",
            cleaned_question,
            re.IGNORECASE,
        )
        if count_in_match:
            raw_val = count_in_match.group(1).strip().rstrip("?.!,")
            if raw_val.lower() in ("the database", "database", "the dataset", "dataset", "the graph", "total"):
                cypher = "MATCH (r:Row) RETURN count(r) AS count"
                with self.writer.get_session() as session:
                    res = session.run(cypher)
                    rec = res.single()
                    total = rec["count"] if rec else 0
                if total > 0:
                    return ChatbotResponse(
                        answer=f"There are {total} total rows in the data.",
                        cypher=cypher,
                        result={"count": total},
                        grounded=True,
                    )
                else:
                    return ChatbotResponse(
                        answer=UNGROUNDED_ANSWER,
                        cypher=cypher,
                        result={"count": 0},
                        grounded=False,
                    )

            found = self.find_property_and_count_for_value(raw_val, active_properties)
            if found:
                prop_name, count = found
                cypher = (
                    f"MATCH (r:Row) "
                    f"WHERE toLower(toString(r.{prop_name})) = toLower($val) "
                    f"RETURN count(r) AS count"
                )
                return ChatbotResponse(
                    answer=f"There are {count} rows where {prop_name} is '{raw_val}'.",
                    cypher=cypher,
                    result={"count": count, "property": prop_name, "value": raw_val},
                    grounded=True,
                )
            else:
                return ChatbotResponse(
                    answer=UNGROUNDED_ANSWER,
                    cypher=None,
                    result=None,
                    grounded=False,
                )

        # -------------------------------------------------------------
        # 5. Retrieval query:
        # e.g., "Show rows in Billing.", "Show rows in Chennai.", "Show rows where department is Billing"
        # -------------------------------------------------------------
        show_match = re.search(
            r"(?:show|list|get|find)\s+rows\s+(?:in|for|where|with)\s+(?:([a-zA-Z0-9_ ]+?)\s+(?:is|=|as)\s+)?['\"]?([a-zA-Z0-9_ ]+?)['\"]?\??\.?$",
            cleaned_question,
            re.IGNORECASE,
        )
        if show_match:
            raw_prop = show_match.group(1)
            raw_val = show_match.group(2).strip().rstrip("?.!,")

            target_prop = None
            if raw_prop:
                sanitized_p = sanitize_property_key(raw_prop.strip())
                if sanitized_p in active_properties:
                    target_prop = sanitized_p
            else:
                found = self.find_property_and_count_for_value(raw_val, active_properties)
                if found:
                    target_prop = found[0]

            if target_prop:
                cypher = (
                    f"MATCH (r:Row) "
                    f"WHERE toLower(toString(r.{target_prop})) = toLower($val) "
                    f"RETURN properties(r) AS row_props "
                    f"LIMIT 10"
                )
                params = {"val": raw_val}
                with self.writer.get_session() as session:
                    res = session.run(cypher, params)
                    rows = [dict(record["row_props"]) for record in res]

                if rows:
                    return ChatbotResponse(
                        answer=f"Found {len(rows)} rows where {target_prop} is '{raw_val}'.",
                        cypher=cypher,
                        result=rows,
                        grounded=True,
                    )
                else:
                    return ChatbotResponse(
                        answer=UNGROUNDED_ANSWER,
                        cypher=cypher,
                        result=[],
                        grounded=False,
                    )

        # -------------------------------------------------------------
        # 6. Fallback / Safety:
        # Never guess, never hallucinate outside knowledge.
        # -------------------------------------------------------------
        return ChatbotResponse(
            answer=UNGROUNDED_ANSWER,
            cypher=None,
            result=None,
            grounded=False,
        )


def run_interactive_chatbot(uri: Optional[str] = None) -> None:
    """
    Interactive CLI helper for testing the grounded chatbot directly.
    """
    writer = Neo4jWriter(uri=uri)
    try:
        writer.connect()
    except Exception as e:
        print(f"Could not connect to Neo4j: {e}")
        return

    bot = GroundedChatbot(writer)
    print("=" * 60)
    print("Grounded Neo4j Chatbot (Type 'exit' to quit)")
    print("Source of truth: Neo4j database only")
    print("=" * 60)

    try:
        while True:
            try:
                question = input("\nUser: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if question.lower() in ("exit", "quit"):
                break
            if not question:
                continue

            response = bot.ask(question)
            print(f"\nAnswer:   {response.answer}")
            print(f"Cypher:   {response.cypher}")
            print(f"Result:   {response.result}")
            print(f"Grounded: {response.grounded}")
    finally:
        writer.close()


if __name__ == "__main__":
    import sys
    run_interactive_chatbot()
