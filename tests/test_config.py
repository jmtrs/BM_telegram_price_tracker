# tests/test_config.py
import config

def test_logging_levels():
    assert config.LOGGING_LEVEL_NAME in ["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"]
    assert config.LOGGING_HTTPX_LEVEL_NAME in ["INFO", "DEBUG", "WARNING", "ERROR", "CRITICAL"]

def test_environment_variables():
    assert isinstance(config.CHECK_INTERVAL_SECONDS, int)
    assert isinstance(config.NOTIFY_COOLDOWN_HOURS, float)
