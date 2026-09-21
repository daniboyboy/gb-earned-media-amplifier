import json
from pathlib import Path
from urllib.parse import urlparse

import trafilatura

from src.schemas import Article

MIN_WORDS = 200
ARTICLES_DIR = Path("data/articles")
REGION_BY_PATH = {"au": "AU", "nz": "NZ", "uk": "UK", "ca": "CA", "us": "US"}

KNOWN_OUTLETS = {
    "businessinsurance.com": {"name": "Business Insurance", "region": "US"},
    "insurancebusinessmag.com": {"name": "Insurance Business", "region": None},
}

URLS = [
    "https://www.businessinsurance.com/automated-drug-reviews-promise-comp-savings-industry-cautious-of-ai/",
    "https://www.businessinsurance.com/accurate-job-descriptions-aid-return-to-work/",
    "https://www.insurancebusinessmag.com/au/news/breaking-news/gallagher-bassett-names-sa-gm-as-claims-model-expands-586200.aspx",
]


def lookup_outlet(url: str) -> dict:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return KNOWN_OUTLETS.get(host, {"name": host, "region": None})


def detect_region(url: str) -> str:
    parsed = urlparse(url)
    first_segment = parsed.path.strip("/").split("/")[0].lower()
    if first_segment in REGION_BY_PATH:
        return REGION_BY_PATH[first_segment]
    if parsed.netloc.endswith(".au"):
        return "AU"
    return lookup_outlet(url)["region"] or "unspecified"


def fetch_article(url: str) -> Article:
    html = trafilatura.fetch_url(url)
    if html is None:
        raise ValueError(f"Could not download page: {url}")
    raw = trafilatura.extract(html, output_format="json", with_metadata=True)
    if raw is None:
        raise ValueError(f"Could not extract text: {url}")
    data = json.loads(raw)
    text = data.get("text") or ""
    word_count = len(text.split())
    if word_count < MIN_WORDS:
        raise ValueError(f"Text too short ({word_count} words), possible registration wall: {url}")
    return Article(
        url=url,
        outlet=data.get("sitename") or lookup_outlet(url)["name"],
        title=data.get("title"),
        published_date=data.get("date"),
        region=detect_region(url),
        text=text,
        source="url",
    )


def save_article(article: Article) -> Path:
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    slug = Path(urlparse(article.url).path.strip("/").split("/")[-1]).stem[:80]
    path = ARTICLES_DIR / f"{slug}.json"
    path.write_text(article.model_dump_json(indent=2), encoding="utf-8")
    return path


def print_summary(article: Article, path: Path) -> None:
    print(f"\n✔ {article.title}")
    print(f"  Outlet: {article.outlet} | Date: {article.published_date} | Region: {article.region}")
    print(f"  Words: {len(article.text.split())} | Saved to: {path}")
    print(f"  Preview: {article.text[:200]}...")


if __name__ == "__main__":
    for url in URLS:
        try:
            article = fetch_article(url)
            print_summary(article, save_article(article))
        except ValueError as error:
            print(f"\n✘ {error}")