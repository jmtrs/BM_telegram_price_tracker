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

def test_parse_product_details_with_partial_json_ld():
    html = """
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Partial Product",
        "offers": {
            "price": "199.99"
        }
    }
    </script>
    """
    result = _parse_product_details(html, "https://example.com")
    assert result["name"] == "Partial Product"
    assert result["price"] == 199.99
    assert result["availability"] is None

def test_parse_product_details_with_malformed_json_ld():
    html = """
    <script type="application/ld+json">
    {
        "@type": "Product",
        "name": "Malformed Product",
        "offers": {
            "price": "not_a_number"
        }
    }
    </script>
    """
    result = _parse_product_details(html, "https://example.com")
    assert result["name"] == "Malformed Product"
    assert result["price"] is None
    assert result["availability"] is None

def test_parse_product_details_with_html_fallback():
    html = """
    <html>
        <h1 data-test-id="product-title">HTML Product</h1>
        <meta name="description" content="HTML description">
        <meta property="og:image" content="https://example.com/image.jpg">
        <span class="product-color">Red</span>
        <span class="product-storage">128GB</span>
    </html>
    """
    result = _parse_product_details(html, "https://example.com")
    assert result["name"] == "HTML Product"
    assert result["description"] == "HTML description"
    assert result["image"] == "https://example.com/image.jpg"
    assert result["color"] == "Red"
    assert result["storage"] == "128GB"
