import pytest
from unittest.mock import MagicMock, patch
from services.config_service import get_settings
from services.sql_service import transpile_to_tsql, inject_safety_top
from services.agent_orchestrator import ReflectionOrchestrator

def test_config_loading():
    settings = get_settings()
    assert settings.app.env in ["development", "production"]
    assert settings.db.timeout == 15

def test_sql_transpilation():
    sql = "SELECT * FROM users LIMIT 10"
    tsql = transpile_to_tsql(sql, read_dialect="postgres")
    assert "TOP" in tsql or "FETCH NEXT" in tsql

def test_safety_injection():
    sql = "SELECT * FROM users"
    safe_sql = inject_safety_top(sql, limit=100)
    assert "TOP (100)" in safe_sql

@patch("services.agent_orchestrator.get_llm")
@patch("services.agent_orchestrator.get_db_connection")
def test_reflection_loop_success(mock_db, mock_llm):
    # Mock LLM response
    mock_llm.return_value.return_value = {
        "choices": [{"text": "SELECT * FROM users"}]
    }
    
    # Mock DB execution
    mock_conn = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value
    mock_cursor.description = [("id",), ("name",)]
    mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
    
    orchestrator = ReflectionOrchestrator(max_attempts=1)
    events = list(orchestrator.generate_sql_with_reflection("Show users", "Context"))
    
    # Verify success sequence
    event_types = [e["event"] for e in events]
    assert "attempt" in event_types
    assert "sql_generated" in event_types
    assert "result" in event_types
    assert "done" in event_types
    assert events[-1]["data"]["message"].startswith("Success")

@patch("services.agent_orchestrator.get_llm")
@patch("services.agent_orchestrator.get_db_connection")
def test_reflection_loop_retry(mock_db, mock_llm):
    # Mock LLM ALWAYS returns bad SQL first, then good SQL
    mock_llm.return_value.side_effect = [
        {"choices": [{"text": "SELECT BAD SQL"}]},
        {"choices": [{"text": "SELECT * FROM users"}]}
    ]
    
    # Mock DB failure then success
    mock_conn = MagicMock()
    mock_db.return_value.__enter__.return_value = mock_conn
    mock_cursor = mock_conn.cursor.return_value
    
    # First call to execute fails, second succeeds
    mock_cursor.execute.side_effect = [Exception("Syntax Error"), None]
    mock_cursor.description = [("id",)]
    mock_cursor.fetchall.return_value = [(1,)]
    
    orchestrator = ReflectionOrchestrator(max_attempts=2)
    events = list(orchestrator.generate_sql_with_reflection("Show users", "Context"))
    
    event_types = [e["event"] for e in events]
    assert event_types.count("attempt") == 2
    assert "reflection" in event_types
    assert "done" in event_types
