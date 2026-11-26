import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.duckduckgo.com/"


def search_duckduckgo(query: str, max_results: int = 5) -> dict:
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must not be empty")
    if type(max_results) is not int or not 1 <= max_results <= 10:
        raise ValueError("max_results must be an integer from 1 to 10")

    params = urlencode(
        {
            "q": query.strip(),
            "format": "json",
            "no_html": 1,
            "no_redirect": 1,
            "skip_disambig": 1,
        }
    )
    request = Request(
        f"{API_URL}?{params}",
        headers={"User-Agent": "QuectelPiAIAssistant/1.0"},
    )
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read(1_000_000))

    if not isinstance(payload, dict):
        raise ValueError("DuckDuckGo returned an invalid response")

    results = []
    seen = set()

    def add_result(title, url, snippet):
        if not snippet:
            return
        key = (url, snippet)
        if key in seen or len(results) >= max_results:
            return
        seen.add(key)
        results.append(
            {
                "title": title or "DuckDuckGo result",
                "url": url or None,
                "snippet": snippet,
            }
        )

    answer = payload.get("Answer")
    if answer:
        add_result(
            payload.get("AnswerType"),
            payload.get("AnswerURL"),
            answer,
        )

    add_result(
        payload.get("AbstractSource") or payload.get("Heading"),
        payload.get("AbstractURL"),
        payload.get("AbstractText"),
    )

    def add_topics(topics):
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            nested_topics = topic.get("Topics")
            if isinstance(nested_topics, list):
                add_topics(nested_topics)
                continue
            add_result(
                topic.get("FirstURL"),
                topic.get("FirstURL"),
                topic.get("Text"),
            )

    related_topics = payload.get("RelatedTopics")
    if isinstance(related_topics, list):
        add_topics(related_topics)

    direct_results = payload.get("Results")
    if isinstance(direct_results, list):
        for item in direct_results:
            if isinstance(item, dict):
                add_result(
                    item.get("Text"),
                    item.get("FirstURL"),
                    item.get("Text"),
                )

    return {
        "query": query.strip(),
        "results": results,
        "message": (
            None
            if results
            else "No instant-answer results were returned. This API does not "
            "provide comprehensive web-search results."
        ),
    }
