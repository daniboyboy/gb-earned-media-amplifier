import os
from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client, observe
from langfuse.openai import OpenAI

from src.config import COMPETITORS
from src.schemas import Article, ArticleAnalysis

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
ARTICLES_DIR = Path("data/articles")
ANALYSIS_DIR = Path("outputs/analysis")

client = OpenAI()

SYSTEM_PROMPT = """You are a media analyst for the marketing team of Gallagher Bassett (GB), a claims management company. You analyse published news articles in which GB appears, to identify what is worth amplifying on GB's own channels.

Rules:
1. Only people who work for Gallagher Bassett are GB spokespeople. People from other organizations are never GB spokespeople, even if they agree with GB.
2. gb_statements: capture everything GB spokespeople say or are reported as saying. Read the article paragraph by paragraph and check every sentence.
   - direct_quote: text inside quotation marks attributed to a GB spokesperson. Copy it exactly, character by character, without the surrounding quotation marks.
     When a quotation is interrupted by an attribution, each quoted segment is a separate statement. Example: "Costs are rising," he said. "We need better data." produces two direct_quote statements: "Costs are rising" and "We need better data."
   - paraphrase: a sentence in which the reporter conveys, without quotation marks, what a GB spokesperson said, believes, recommends or prioritises. This includes sentences attributed with a pronoun (she said, he added) that refers to a GB spokesperson, and sentences that report the spokesperson's views, plans or priorities without a speech verb. Copy the sentence exactly; you may omit only the attribution clause (for example ", she said" or ", said [name], [title]").
   Never correct, rephrase, shorten or join text from different sentences or quoted segments.
3. key_messages: 2 to 5 messages that represent GB's position or expertise in this article, each written in your own words as one sentence. Each must include a supporting_excerpt copied exactly from the article. Never attribute to GB ideas expressed by other organizations.
4. themes: 3 to 6 short labels (2 to 4 words) for the topics worth amplifying.
5. coverage_type:
   - expert_commentary: GB is one voice among several in an article about a broader industry topic.
   - feature: GB's commentary is central to the article or provides most of its substance.
   - announcement: news about GB itself (appointments, expansions, contracts, results).
   Explain your choice in one sentence in coverage_rationale.
6. other_organizations: every other organization quoted or mentioned. Mark as competitor any organization on this list: {competitors}, and any other company that provides claims administration or managed care services. Use legal for law firms and attorneys' associations, regulator for government bodies and courts, and other for everything else.
7. If the article contains more than one story (for example a related sidebar), analyse all parts.
8. Use only information in the article. Never add facts, figures or context from outside it."""


def load_article(path: Path) -> Article:
    return Article.model_validate_json(path.read_text(encoding="utf-8"))


def build_user_message(article: Article) -> str:
    return (
        f"Outlet: {article.outlet}\n"
        f"Title: {article.title}\n"
        f"Published: {article.published_date}\n"
        f"Region: {article.region}\n\n"
        f"ARTICLE TEXT:\n{article.text}"
    )


@observe(name="analyst")
def analyze_article(article: Article) -> ArticleAnalysis:
    completion = client.chat.completions.parse(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(competitors=", ".join(COMPETITORS))},
            {"role": "user", "content": build_user_message(article)},
        ],
        response_format=ArticleAnalysis,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Model did not return a valid analysis: {message.refusal}")
    return message.parsed


def save_analysis(analysis: ArticleAnalysis, article_path: Path) -> Path:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    path = ANALYSIS_DIR / article_path.name
    path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
    return path


def print_summary(analysis: ArticleAnalysis, title: str | None, path: Path) -> None:
    quotes = sum(s.type == "direct_quote" for s in analysis.gb_statements)
    paraphrases = len(analysis.gb_statements) - quotes
    competitors = [o.name for o in analysis.other_organizations if o.relation == "competitor"]
    print(f"\n✔ {title}")
    print(f"  Coverage: {analysis.coverage_type}: {analysis.coverage_rationale}")
    print(f"  GB spokespeople: {', '.join(s.name for s in analysis.gb_spokespeople)}")
    print(f"  Statements: {quotes} direct quotes, {paraphrases} paraphrases")
    print(f"  Key messages: {len(analysis.key_messages)} | Themes: {', '.join(analysis.themes)}")
    print(f"  Competitors: {', '.join(competitors) or 'none'}")
    print(f"  Saved to: {path}")


if __name__ == "__main__":
    for article_path in sorted(ARTICLES_DIR.glob("*.json")):
        article = load_article(article_path)
        analysis = analyze_article(article)
        print_summary(analysis, article.title, save_analysis(analysis, article_path))
    get_client().flush()