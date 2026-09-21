import re
import sys
from pathlib import Path

from pydantic import BaseModel

from src.schemas import Article

ABBREVIATIONS = ("Mr.", "Ms.", "Mrs.", "Dr.", "v.", "St.", "U.S.", "Inc.", "Co.", "Jr.")
QUOTE_PATTERN = re.compile(r"“([^”]+)”|\"([^\"]+)\"")
SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
QUOTE_PLACEHOLDER = "⟨quote⟩"
DEFAULT_SLUG = "accurate-job-descriptions-aid-return-to-work"


class Item(BaseModel):
    id: str
    paragraph: int
    text: str


class SegmentedArticle(BaseModel):
    paragraphs: list[str]
    quotes: list[Item]
    sentences: list[Item]

    def lookup(self, item_id: str) -> Item | None:
        for item in self.quotes + self.sentences:
            if item.id == item_id:
                return item
        return None


def split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n") if p.strip()]


def extract_quotes(paragraph: str) -> list[str]:
    quotes = []
    for match in QUOTE_PATTERN.finditer(paragraph):
        text = (match.group(1) or match.group(2)).strip().rstrip(",")
        quotes.append(text)
    return quotes


def split_sentences(paragraph: str) -> list[str]:
    sentences = []
    for piece in SENTENCE_BREAK.split(paragraph):
        if sentences and sentences[-1].endswith(ABBREVIATIONS):
            sentences[-1] += " " + piece
        else:
            sentences.append(piece)
    return sentences


def unquoted_sentences(paragraph: str) -> list[str]:
    masked = QUOTE_PATTERN.sub(QUOTE_PLACEHOLDER, paragraph)
    return [s for s in split_sentences(masked) if QUOTE_PLACEHOLDER not in s]


def segment_article(text: str) -> SegmentedArticle:
    paragraphs = split_paragraphs(text)
    quotes, sentences = [], []
    for number, paragraph in enumerate(paragraphs, start=1):
        for quote in extract_quotes(paragraph):
            quotes.append(Item(id=f"Q{len(quotes) + 1}", paragraph=number, text=quote))
        for sentence in unquoted_sentences(paragraph):
            sentences.append(Item(id=f"S{len(sentences) + 1}", paragraph=number, text=sentence))
    return SegmentedArticle(paragraphs=paragraphs, quotes=quotes, sentences=sentences)


if __name__ == "__main__":
    slug = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SLUG
    path = Path(f"data/articles/{slug}.json")
    article = Article.model_validate_json(path.read_text(encoding="utf-8"))
    segmented = segment_article(article.text)
    print(f"Paragraphs: {len(segmented.paragraphs)} | Quotes: {len(segmented.quotes)} | Sentences: {len(segmented.sentences)}\n")
    for item in segmented.quotes + segmented.sentences:
        print(f"[{item.id} | P{item.paragraph}] {item.text[:100]}")