"""
Tests for Grounded Chatbot (TEST 4 and TEST 5).
Validates that the chatbot ONLY answers using actual Neo4j data,
never guesses, and strictly returns 'I don't have that in the data.'
with grounded=False when questions cannot be answered from the graph.
"""
from unittest.mock import MagicMock
from app.chatbot import GroundedChatbot, UNGROUNDED_ANSWER
from app.neo4j_writer import Neo4jWriter


def create_mocked_neo4j_chatbot():
    """
    Creates a GroundedChatbot instance backed by a mocked Neo4jWriter
    populated with sample graph data:
      - department: "Billing" (5 rows)
      - city: "Chennai" (3 rows)
    """
    writer = MagicMock(spec=Neo4jWriter)
    writer.get_all_properties_for_rows.return_value = ["department", "city", "name"]

    mock_session = MagicMock()

    def mock_run(query, params=None):
        params = params or {}
        q = query.strip()
        mock_result = MagicMock()

        # 1. Total rows query
        if "MATCH (r:Row) RETURN count(r) AS count" in q:
            mock_result.single.return_value = {"count": 8}
            return mock_result

        # 2. Check if property has value (find_property_and_count_for_value)
        val = str(params.get("val", "")).lower()
        if "toLower(toString(r.department)) = toLower($val)" in q and "RETURN count(r)" in q:
            if val == "billing":
                mock_result.single.return_value = {"c": 5, "count": 5}
                return mock_result
            else:
                mock_result.single.return_value = {"c": 0, "count": 0}
                return mock_result

        if "toLower(toString(r.city)) = toLower($val)" in q and "RETURN count(r)" in q:
            if val == "chennai":
                mock_result.single.return_value = {"c": 3, "count": 3}
                return mock_result
            else:
                mock_result.single.return_value = {"c": 0, "count": 0}
                return mock_result

        # 3. Retrieval query
        if "RETURN properties(r) AS row_props" in q:
            if val == "billing":
                rows = [
                    {"row_props": {"name": "Alice", "department": "Billing", "city": "Chennai"}},
                    {"row_props": {"name": "Bob", "department": "Billing", "city": "Bangalore"}},
                ]
                mock_result.__iter__.side_effect = lambda: iter(rows)
                return mock_result

        # Default empty result
        mock_result.single.return_value = {"c": 0, "count": 0}
        mock_result.__iter__.side_effect = lambda: iter([])
        return mock_result

    mock_session.run.side_effect = mock_run
    writer.get_session.return_value.__enter__.return_value = mock_session
    writer.get_session.return_value.__exit__.return_value = None

    return GroundedChatbot(writer)


def test_chatbot_answers_count_in_department():
    """
    TEST 4: Chatbot can answer a question using Neo4j.
    Question: 'How many rows are in Billing?'
    """
    bot = create_mocked_neo4j_chatbot()
    resp = bot.ask("How many rows are in Billing?")

    assert resp.grounded is True
    assert "5 rows" in resp.answer
    assert "department" in resp.answer
    assert resp.cypher is not None
    assert "MATCH (r:Row)" in resp.cypher
    assert "r.department" in resp.cypher
    assert resp.result["count"] == 5


def test_chatbot_answers_count_in_city():
    """
    TEST 4: Chatbot can answer city-based question using Neo4j.
    Question: 'How many rows are in Chennai?'
    """
    bot = create_mocked_neo4j_chatbot()
    resp = bot.ask("How many rows are in Chennai?")

    assert resp.grounded is True
    assert "3 rows" in resp.answer
    assert "city" in resp.answer
    assert resp.cypher is not None
    assert "r.city" in resp.cypher
    assert resp.result["count"] == 3


def test_chatbot_answers_show_rows():
    """
    TEST 4: Chatbot retrieval query: 'Show rows in Billing.'
    """
    bot = create_mocked_neo4j_chatbot()
    resp = bot.ask("Show rows in Billing.")

    assert resp.grounded is True
    assert "Found 2 rows" in resp.answer
    assert len(resp.result) == 2
    assert resp.result[0]["name"] == "Alice"


def test_chatbot_answers_total_rows():
    """
    TEST 4: Chatbot overall count query.
    """
    bot = create_mocked_neo4j_chatbot()
    resp = bot.ask("How many rows are in the database?")

    assert resp.grounded is True
    assert "8 total rows" in resp.answer
    assert resp.result["count"] == 8


def test_chatbot_refuses_general_knowledge_test_5():
    """
    TEST 5: Chatbot refuses to guess when the information is not in Neo4j.
    Must return 'I don't have that in the data.' with grounded=False.
    """
    bot = create_mocked_neo4j_chatbot()

    unrelated_questions = [
        "Who is the president of France?",
        "What is the capital of Japan?",
        "What is 2 + 2?",
        "Tell me a joke.",
        "How is the weather today?",
    ]

    for question in unrelated_questions:
        resp = bot.ask(question)
        assert resp.grounded is False
        assert resp.answer == UNGROUNDED_ANSWER
        assert resp.result is None
        assert resp.cypher is None


def test_chatbot_refuses_nonexistent_data_test_5():
    """
    TEST 5: When queried about a value/entity NOT present in Neo4j,
    it strictly refuses and does not invent data.
    """
    bot = create_mocked_neo4j_chatbot()

    resp = bot.ask("How many rows are in Atlantis?")
    assert resp.grounded is False
    assert resp.answer == UNGROUNDED_ANSWER
