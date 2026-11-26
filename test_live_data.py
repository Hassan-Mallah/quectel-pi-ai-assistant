import json
import unittest
from io import BytesIO
from unittest.mock import patch

from live_data import get_current_weather, get_latest_news


class LiveDataTests(unittest.TestCase):
    @patch("live_data.urlopen")
    def test_weather_resolves_location_and_returns_current_conditions(
        self, mock_urlopen
    ):
        mock_urlopen.side_effect = [
            BytesIO(
                json.dumps(
                    {
                        "results": [
                            {
                                "name": "Paris",
                                "admin1": "Ile-de-France",
                                "country": "France",
                                "latitude": 48.85,
                                "longitude": 2.35,
                            }
                        ]
                    }
                ).encode("utf-8")
            ),
            BytesIO(
                json.dumps(
                    {
                        "timezone": "Europe/Paris",
                        "current": {
                            "time": "2026-11-26T14:00",
                            "temperature_2m": 12.5,
                            "apparent_temperature": 11.0,
                            "relative_humidity_2m": 70,
                            "precipitation": 0.0,
                            "weather_code": 2,
                            "wind_speed_10m": 8.0,
                        },
                        "current_units": {
                            "temperature_2m": "°C",
                            "relative_humidity_2m": "%",
                            "precipitation": "mm",
                            "wind_speed_10m": "km/h",
                        },
                    }
                ).encode("utf-8")
            ),
        ]

        result = get_current_weather("Paris")

        self.assertEqual(result["location"], "Paris, Ile-de-France, France")
        self.assertEqual(result["conditions"], "Partly cloudy")
        self.assertEqual(result["temperature"], 12.5)
        self.assertEqual(result["source"], "Open-Meteo")

    @patch("live_data.urlopen")
    def test_weather_rejects_unknown_locations(self, mock_urlopen):
        mock_urlopen.return_value = BytesIO(b'{"results":[]}')

        with self.assertRaisesRegex(ValueError, "Could not find a location"):
            get_current_weather("Nowhere")
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("live_data.urlopen")
    def test_news_returns_recent_articles_and_uses_general_query_by_default(
        self, mock_urlopen
    ):
        mock_urlopen.return_value = BytesIO(
            b"""<rss><channel><item>
            <title>Headline</title>
            <description>News summary</description>
            <link>https://example.com/story</link>
            <pubDate>Thu, 26 Nov 2026 14:00:00 GMT</pubDate>
            </item></channel></rss>"""
        )

        result = get_latest_news()

        self.assertEqual(result["query"], "top headlines")
        self.assertEqual(result["articles"][0]["title"], "Headline")
        self.assertEqual(result["articles"][0]["source"], "BBC News")
        self.assertEqual(result["source"], "BBC News")

    @patch("live_data.urlopen")
    def test_news_filters_headlines_by_topic(self, mock_urlopen):
        mock_urlopen.return_value = BytesIO(
            b"""<rss><channel>
            <item>
            <title>AI research update</title>
            <description>New computing research</description>
            <link>https://example.com/ai</link>
            </item>
            <item>
            <title>Football final results</title>
            <description>Sports news</description>
            <link>https://example.com/sports</link>
            </item>
            </channel></rss>"""
        )

        result = get_latest_news("AI news")

        self.assertEqual([item["title"] for item in result["articles"]], [
            "AI research update"
        ])


if __name__ == "__main__":
    unittest.main()
