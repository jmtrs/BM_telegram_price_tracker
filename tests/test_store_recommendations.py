# tests/test_store_recommendations.py
import pytest
from use_cases.store_recommendations import store_recommendations


def test_store_recommendations_success(monkeypatch):
    # Dummy response JSON
    fake_response = {
        "recommendationRequestId": "req-123",
        "widgetId": "wid-456",
        "products": [
            {"id": "prod1", "name": "Product 1"},
            {"id": "prod2", "name": "Product 2"}
        ]
    }

    # Monkeypatch repository methods
    created_ids = {}

    def fake_create_recommendation_request(req_id, widget_id, response_json):
        # Assert correct arguments
        assert req_id == fake_response["recommendationRequestId"]
        assert widget_id == fake_response["widgetId"]
        assert response_json is fake_response
        # Return a fake UUID
        return "uuid-req-123"

    def fake_bulk_insert(request_uuid, products):
        # Assert correct arguments
        assert request_uuid == "uuid-req-123"
        assert products == fake_response["products"]
        created_ids['count'] = len(products)
        return created_ids['count']

    monkeypatch.setattr(
        'use_cases.store_recommendations.create_recommendation_request',
        fake_create_recommendation_request
    )
    monkeypatch.setattr(
        'use_cases.store_recommendations.bulk_insert_recommended_products',
        fake_bulk_insert
    )

    # Execute use case
    result_uuid = store_recommendations(fake_response)

    # Validate return value and side effects
    assert result_uuid == "uuid-req-123"
    assert created_ids['count'] == 2


@pytest.mark.parametrize("missing_key", ["recommendationRequestId", "widgetId", "products"])
def test_store_recommendations_missing_fields(monkeypatch, missing_key):
    # Response missing a key should not raise but handle gracefully
    fake_response = {
        "recommendationRequestId": "req-123",
        "widgetId": "wid-456",
        "products": []
    }
    # Remove the key under test
    fake_response.pop(missing_key, None)

    # Provide dummy implementations
    monkeypatch.setattr(
        'use_cases.store_recommendations.create_recommendation_request',
        lambda req_id, widget_id, response_json: "uuid-req-123"
    )
    monkeypatch.setattr(
        'use_cases.store_recommendations.bulk_insert_recommended_products',
        lambda request_uuid, products: 0
    )

    # Should not raise and return the fake UUID
    result_uuid = store_recommendations(fake_response)
    assert result_uuid == "uuid-req-123"
