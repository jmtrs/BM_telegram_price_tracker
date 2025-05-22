import unittest
from unittest.mock import patch, mock_open
import json # For creating test JSON
from main import clean_url, _parse_product_details

class TestURLCleaning(unittest.TestCase):
    def test_clean_url_simple(self):
        self.assertEqual(clean_url("http://example.com/path"), "http://example.com/path")

    def test_clean_url_with_l_param(self):
        self.assertEqual(clean_url("http://example.com/path?l=123&other=abc"), "http://example.com/path?l=123")

    def test_clean_url_with_other_params(self):
        self.assertEqual(clean_url("http://example.com/path?other=abc&another=def"), "http://example.com/path")

    def test_clean_url_already_clean(self):
        self.assertEqual(clean_url("http://example.com/path?l=456"), "http://example.com/path?l=456")
    
    def test_clean_url_https_and_fragment(self):
        self.assertEqual(clean_url("https://example.com/path?l=789&other=xyz#section1"), "https://example.com/path?l=789")

    def test_clean_url_no_query(self):
        self.assertEqual(clean_url("http://example.com/another"), "http://example.com/another")

    def test_clean_url_empty_query_l_param(self):
        self.assertEqual(clean_url("http://example.com/path?l=&other=abc"), "http://example.com/path?l=")


class TestProductParsing(unittest.TestCase):
    def setUp(self):
        # Try to read scraper.html, but don't fail if it's not there.
        # Tests that rely on it will be skipped or will use alternative content.
        try:
            with open("scraper.html", "r", encoding="utf-8") as f:
                self.sample_html_content_from_file = f.read()
        except FileNotFoundError:
            self.sample_html_content_from_file = None
            print("scraper.html not found, tests relying on it may be skipped or use defaults.")

    def test_parse_from_scraper_html(self):
        # This test depends on the actual content of scraper.html
        # Assuming scraper.html contains:
        # price: 120.50, availability: InStock, condition: NewCondition
        if self.sample_html_content_from_file:
            price, availability, condition = _parse_product_details(
                self.sample_html_content_from_file, "http://example.com/from_scraper_html"
            )
            # IMPORTANT: These expected values MUST match what is in your scraper.html
            # Based on the provided scraper.html, the price is 120.50.
            # Availability is InStock. Condition is NewCondition.
            self.assertEqual(price, 120.50) 
            self.assertEqual(availability, "InStock")
            self.assertEqual(condition, "NewCondition")
        else:
            # Fallback or skip if scraper.html is not available
            # For now, let's create a minimal HTML that matches the expected values
            print("Skipping test_parse_from_scraper_html as scraper.html was not found or is empty. Using fallback content.")
            fallback_html = """
            <script type="application/ld+json">
            {
              "@context": "http://schema.org",
              "@type": "Product",
              "name": "Test Product from Fallback",
              "offers": {
                "@type": "Offer",
                "price": "120.50",
                "availability": "http://schema.org/InStock",
                "itemCondition": "http://schema.org/NewCondition"
              }
            }
            </script>
            """
            price, availability, condition = _parse_product_details(
                fallback_html, "http://example.com/from_scraper_html_fallback"
            )
            self.assertEqual(price, 120.50)
            self.assertEqual(availability, "InStock")
            self.assertEqual(condition, "NewCondition")


    def test_parse_minimal_valid_json(self):
        minimal_html = """
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "Product",
          "offers": {
            "@type": "Offer",
            "price": "99.99",
            "availability": "http://schema.org/InStock",
            "itemCondition": "http://schema.org/NewCondition"
          }
        }
        </script>
        """
        price, availability, condition = _parse_product_details(minimal_html, "http://example.com/minimal")
        self.assertEqual(price, 99.99)
        self.assertEqual(availability, "InStock")
        self.assertEqual(condition, "NewCondition")

    def test_parse_minimal_valid_json_offer_list(self):
        minimal_html_list = """
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "Product",
          "offers": [
            {
              "@type": "Offer",
              "price": "101.99",
              "availability": "http://schema.org/OnlineOnly",
              "itemCondition": "http://schema.org/UsedCondition"
            }
          ]
        }
        </script>
        """
        price, availability, condition = _parse_product_details(minimal_html_list, "http://example.com/minimal_list")
        self.assertEqual(price, 101.99)
        self.assertEqual(availability, "OnlineOnly")
        self.assertEqual(condition, "UsedCondition")

    def test_parse_missing_data(self):
        html_missing_price = """
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "Product",
          "offers": {
            "@type": "Offer",
            "availability": "http://schema.org/InStock",
            "itemCondition": "http://schema.org/NewCondition"
          }
        }
        </script>
        """
        price, availability, condition = _parse_product_details(html_missing_price, "http://example.com/missing_price")
        self.assertIsNone(price)
        self.assertEqual(availability, "InStock") # Should still parse other valid fields
        self.assertEqual(condition, "NewCondition")

    def test_parse_missing_condition(self):
        html_missing_condition = """
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "Product",
          "offers": {
            "@type": "Offer",
            "price": "75.00",
            "availability": "http://schema.org/OutOfStock"
          }
        }
        </script>
        """
        price, availability, condition = _parse_product_details(html_missing_condition, "http://example.com/missing_condition")
        self.assertEqual(price, 75.00)
        self.assertEqual(availability, "OutOfStock")
        self.assertIsNone(condition)


    def test_parse_invalid_json(self):
        html_invalid_json = """
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "Product",
          "offers": {
            "@type": "Offer",
            "price": "99.99",
            "availability": "http://schema.org/InStock",
            "itemCondition": "http://schema.org/NewCondition" 
          } 
        </script> 
        """ # Missing closing brace for the main JSON object
        price, availability, condition = _parse_product_details(html_invalid_json, "http://example.com/invalid_json")
        self.assertIsNone(price)
        self.assertIsNone(availability)
        self.assertIsNone(condition)

    def test_parse_no_offers_key(self):
        html_no_offers = """
        <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "Product",
          "name": "A Product Name"
        }
        </script>
        """
        price, availability, condition = _parse_product_details(html_no_offers, "http://example.com/no_offers")
        self.assertIsNone(price)
        self.assertIsNone(availability)
        self.assertIsNone(condition)

    def test_parse_empty_script_tag(self):
        html_empty_script = '<script type="application/ld+json"></script>'
        price, availability, condition = _parse_product_details(html_empty_script, "http://example.com/empty_script")
        self.assertIsNone(price)
        self.assertIsNone(availability)
        self.assertIsNone(condition)
        
    def test_parse_no_ld_json_scripts(self):
        html_no_ld_json = '<p>This is a paragraph.</p><script type="text/javascript">var x=1;</script>'
        price, availability, condition = _parse_product_details(html_no_ld_json, "http://example.com/no_ld_json_scripts")
        self.assertIsNone(price)
        self.assertIsNone(availability)
        self.assertIsNone(condition)

if __name__ == '__main__':
    unittest.main()
