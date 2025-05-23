# tests/test_main.py
# tests/test_main.py
from unittest.mock import AsyncMock, patch
import pytest
from main import main_async_logic

@pytest.mark.asyncio
@patch("main.db_connection.get_db_connection", new_callable=AsyncMock)
@patch("main.ApplicationBuilder")
async def test_main_async_logic(mock_app_builder, mock_get_db_connection):
    mock_app = mock_app_builder.return_value.token.return_value.build.return_value
    mock_app.run_polling = AsyncMock()

    mock_get_db_connection.return_value = AsyncMock(closed=False)
    await main_async_logic()

    mock_get_db_connection.assert_called_once()
    mock_app.run_polling.assert_awaited_once()
