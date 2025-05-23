# tests/test_scraper_utils.py
import pytest
from scraper.utils import clean_url

def test_clean_url_with_valid_url():
    url = "https://example.com/product?l=123&ref=abc#details"
    expected = "https://example.com/product?l=123"
    assert clean_url(url) == expected

def test_clean_url_without_l_param():
    url = "https://example.com/product?ref=abc#details"
    expected = "https://example.com/product"
    assert clean_url(url) == expected

def test_clean_url_with_invalid_url():
    url = "invalid_url"
    assert clean_url(url) == "invalid_url"
