# tests/test_db_queries.py
from unittest.mock import patch
from db.queries import get_alert_by_chat_and_clean_url

@patch("db.queries.get_db_connection")
def test_get_alert_by_chat_and_clean_url(mock_get_db_connection):
    # Mock the database connection and cursor
    mock_conn = mock_get_db_connection.return_value
    mock_cursor = mock_conn.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = {"id": "123", "chat_id": 1, "clean_url": "https://example.com"}

    # Call the function being tested
    result = get_alert_by_chat_and_clean_url(1, "https://example.com")

    # Assertions to verify the result
    assert result["id"] == "123"
    assert result["chat_id"] == 1
    assert result["clean_url"] == "https://example.com"
