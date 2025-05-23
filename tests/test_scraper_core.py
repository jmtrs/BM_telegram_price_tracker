# tests/test_scraper_core.py
import pytest
from scraper.core import _parse_product_details

def test_parse_product_details_with_valid_html():
    html = """
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Test Product",
        "offers": {
            "price": "99.99",
            "availability": "http://schema.org/InStock"
        }
    }
    </script>
    """
    result = _parse_product_details(html, "https://example.com")
    assert result["name"] == "Test Product"
    assert result["price"] == 99.99
    assert result["availability"] == "InStock"

def test_parse_product_details_with_no_product_data():
    html = "<html><body>No product data here</body></html>"
    result = _parse_product_details(html, "https://example.com")
    assert result["name"] is None
    assert result["price"] is None
