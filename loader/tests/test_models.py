"""
Unit tests for data models, schema sanitization, and stable ID generation.
"""
import pytest
from app.models import (
    CSVRowMessage,
    sanitize_property_key,
    sanitize_property_value,
    sanitize_row_properties,
)


def test_sanitize_property_key():
    # Regular column
    assert sanitize_property_key("Department") == "department"
    # Column with spaces and symbols
    assert sanitize_property_key("Total ($)") == "total"
    assert sanitize_property_key("First Name") == "first_name"
    assert sanitize_property_key("  Email Address  ") == "email_address"
    # Leading digit
    assert sanitize_property_key("2024 Revenue") == "col_2024_revenue"
    # Empty or punctuation-only
    assert sanitize_property_key("   ") == "unnamed_column"
    assert sanitize_property_key("###") == "unnamed_column"


def test_duplicate_column_names_in_row():
    seen = set()
    col1 = sanitize_property_key("Department", seen)
    col2 = sanitize_property_key("Department", seen)
    col3 = sanitize_property_key("Department", seen)
    assert col1 == "department"
    assert col2 == "department_2"
    assert col3 == "department_3"


def test_sanitize_property_value():
    assert sanitize_property_value("  ") is None
    assert sanitize_property_value(None) is None
    assert sanitize_property_value("123") == 123
    assert sanitize_property_value("45.67") == 45.67
    assert sanitize_property_value("true") is True
    assert sanitize_property_value("no") is False
    assert sanitize_property_value("Billing") == "Billing"


def test_sanitize_row_properties():
    raw_data = {
        "Name": "Alice",
        "Department": "Billing",
        "City": "Chennai",
        "EmptyField": "   ",
        "Total ($)": "1500",
        "Active?": "yes",
    }
    cleaned = sanitize_row_properties(raw_data)
    assert cleaned["name"] == "Alice"
    assert cleaned["department"] == "Billing"
    assert cleaned["city"] == "Chennai"
    assert "emptyfield" not in cleaned  # Empty strings omitted
    assert cleaned["total"] == 1500
    assert cleaned["active"] is True


def test_csv_row_message_nested():
    payload = {
        "dataset_id": "ds_alpha",
        "job_id": "job_001",
        "row_index": 5,
        "data": {
            "Employee Name": "Bob",
            "Department": "Engineering",
        },
    }
    msg = CSVRowMessage.model_validate(payload)
    assert msg.dataset_id == "ds_alpha"
    assert msg.job_id == "job_001"
    assert msg.row_index == 5
    assert msg.stable_row_id == "ds_alpha_5"
    props = msg.get_sanitized_properties()
    assert props["employee_name"] == "Bob"
    assert props["department"] == "Engineering"


def test_csv_row_message_flat():
    # Test flat format where CSV columns are root keys
    payload = {
        "dataset_id": "ds_beta",
        "job_id": "job_002",
        "row_index": 0,
        "Name": "Charlie",
        "City": "Chennai",
    }
    msg = CSVRowMessage.model_validate(payload)
    assert msg.stable_row_id == "ds_beta_0"
    props = msg.get_sanitized_properties()
    assert props["name"] == "Charlie"
    assert props["city"] == "Chennai"


def test_csv_row_message_missing_required_fields():
    with pytest.raises(ValueError):
        CSVRowMessage.model_validate({"job_id": "job_1", "row_index": 0})
