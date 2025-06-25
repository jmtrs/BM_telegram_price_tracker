# tests/test_ui_recommendations.py
import datetime
import pytest
from bot.ui import format_recommendations_message


def test_format_recommendations_message_empty():
    assert format_recommendations_message([], {}) == "📭 No hay recomendaciones disponibles."


def test_format_recommendations_message_single():
    # Preparar datos de prueba
    timestamp = datetime.datetime(2025, 6, 5, 12, 0, 0)
    requests = [
        {
            'id': 'r1',
            'recommendation_request_id': 'req1',
            'widget_id': 'w1',
            'requested_at': timestamp
        }
    ]
    products_map = {
        'r1': [
            {'title': 'Prod A', 'price_amount': 10, 'price_currency': 'EUR'}
        ]
    }
    message = format_recommendations_message(requests, products_map)
    # Verificar nueva cabecera y contenido
    assert message.startswith("📣 *Recomendaciones recientes*")
    assert f"🔔 *req1* (widget: w1) — {timestamp}" in message
    assert "  • Prod A — 10EUR" in message
