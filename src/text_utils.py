import re

QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
EDGE_CHARS = " \t\n\"'.,;:"


def normalize(text: str) -> str:
    text = text.translate(QUOTE_MAP)
    text = re.sub(r"\s+", " ", text)
    return text.strip(EDGE_CHARS)


def is_verbatim(fragment: str, source: str) -> bool:
    return normalize(fragment) in normalize(source)