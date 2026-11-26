import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlencode
from urllib.request import Request, urlopen


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
NEWS_FEEDS = {
    "top": "https://feeds.bbci.co.uk/news/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
}
NEWS_STOP_WORDS = {
    "about",
    "latest",
    "news",
    "recent",
    "the",
    "today",
    "what",
}

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow",
    73: "Moderate snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _get_json(url: str, params: dict) -> dict:
    request = Request(
        f"{url}?{urlencode(params)}",
        headers={"User-Agent": "QuectelPiAIAssistant/1.0"},
    )
    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read(1_000_000))
    if not isinstance(payload, dict):
        raise ValueError("The live data service returned an invalid response")
    return payload


def _get_bytes(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "QuectelPiAIAssistant/1.0"})
    with urlopen(request, timeout=12) as response:
        return response.read(1_000_000)


def get_current_weather(location: str) -> dict:
    if not isinstance(location, str) or not location.strip():
        raise ValueError("A city or location is required for a weather lookup")

    geocoding = _get_json(
        GEOCODING_URL,
        {
            "name": location.strip(),
            "count": 1,
            "language": "en",
            "format": "json",
        },
    )
    locations = geocoding.get("results") or []
    if not locations:
        raise ValueError(f"Could not find a location matching {location!r}")

    place = locations[0]
    forecast = _get_json(
        WEATHER_URL,
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,wind_speed_10m"
            ),
            "timezone": "auto",
        },
    )
    current = forecast.get("current")
    if not isinstance(current, dict):
        raise ValueError("The weather service returned no current conditions")

    current_units = forecast.get("current_units") or {}
    location_parts = [place.get("name"), place.get("admin1"), place.get("country")]
    resolved_location = ", ".join(
        part
        for index, part in enumerate(location_parts)
        if part and (index == 0 or part != location_parts[index - 1])
    )
    weather_code = current.get("weather_code")

    return {
        "source": "Open-Meteo",
        "location": resolved_location,
        "observed_at": current.get("time"),
        "timezone": forecast.get("timezone"),
        "conditions": WEATHER_CODES.get(weather_code, "Unknown conditions"),
        "temperature": current.get("temperature_2m"),
        "temperature_unit": current_units.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "humidity_unit": current_units.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "precipitation_unit": current_units.get("precipitation"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_speed_unit": current_units.get("wind_speed_10m"),
    }


def get_latest_news(topic: str = "", max_results: int = 5) -> dict:
    if not isinstance(topic, str):
        raise ValueError("News topic must be text")
    if type(max_results) is not int or not 1 <= max_results <= 10:
        raise ValueError("max_results must be an integer from 1 to 10")

    normalized_topic = topic.strip()
    topic_words = {
        word
        for word in re.findall(r"[a-z0-9]+", normalized_topic.casefold())
        if word not in NEWS_STOP_WORDS
    }

    if topic_words & {"business", "economy", "finance", "market", "markets"}:
        feed_url = NEWS_FEEDS["business"]
    elif topic_words & {
        "ai",
        "computer",
        "cyber",
        "software",
        "tech",
        "technology",
    }:
        feed_url = NEWS_FEEDS["technology"]
    elif topic_words & {"global", "international", "world"}:
        feed_url = NEWS_FEEDS["world"]
    else:
        feed_url = NEWS_FEEDS["top"]

    try:
        root = ET.fromstring(_get_bytes(feed_url))
    except ET.ParseError as exc:
        raise ValueError("The news feed returned invalid XML") from exc

    results = []
    for item in root.findall("./channel/item"):
        title = item.findtext("title", default="").strip()
        description = item.findtext("description", default="").strip()
        searchable_text = f"{title} {description}".casefold()
        if topic_words and not any(word in searchable_text for word in topic_words):
            continue
        url = item.findtext("link", default="").strip()
        if not title or not url:
            continue
        results.append(
            {
                "title": title,
                "summary": description,
                "source": "BBC News",
                "published": item.findtext("pubDate"),
                "url": url,
            }
        )
        if len(results) >= max_results:
            break

    return {
        "source": "BBC News",
        "query": normalized_topic or "top headlines",
        "articles": results,
        "message": (
            None
            if results
            else "No recent BBC headlines matched that topic."
        ),
    }
