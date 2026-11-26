import json
import unittest
from io import BytesIO
from unittest.mock import patch

from duckduckgo_search import search_duckduckgo


class DuckDuckGoSearchTests(unittest.TestCase):
    @patch("duckduckgo_search.urlopen")
    def test_returns_answer_and_related_results_with_limit(self, mock_urlopen):
        payload = {
            "Answer": "Current answer",
            "AnswerType": "answer",
            "AnswerURL": "https://example.com/answer",
            "AbstractText": "Background information",
            "AbstractSource": "Example",
            "AbstractURL": "https://example.com/abstract",
            "RelatedTopics": [
                {"Text": "Related item", "FirstURL": "https://example.com/related"}
            ],
        }
        mock_urlopen.return_value = BytesIO(json.dumps(payload).encode("utf-8"))

        result = search_duckduckgo("  test query  ", max_results=2)

        self.assertEqual(result["query"], "test query")
        self.assertEqual(len(result["results"]), 2)
        self.assertEqual(result["results"][0]["snippet"], "Current answer")
        self.assertEqual(
            result["results"][1]["url"],
            "https://example.com/abstract",
        )
        self.assertIsNone(result["message"])

    @patch("duckduckgo_search.urlopen")
    def test_reports_when_no_instant_answers_are_available(self, mock_urlopen):
        mock_urlopen.return_value = BytesIO(b'{"RelatedTopics": []}')

        result = search_duckduckgo("current traffic")

        self.assertEqual(result["results"], [])
        self.assertIn("not provide comprehensive", result["message"])

    def test_rejects_empty_queries_and_invalid_result_limits(self):
        with self.assertRaises(ValueError):
            search_duckduckgo(" ")
        with self.assertRaises(ValueError):
            search_duckduckgo("test", max_results=11)


if __name__ == "__main__":
    unittest.main()
