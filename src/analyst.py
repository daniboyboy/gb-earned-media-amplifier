import os
from pathlib import Path
from src.usage import record

from dotenv import load_dotenv
from langfuse import get_client, observe
from langfuse.openai import OpenAI

from src.config import COMPETITORS
from src.schemas import (
    AnalystSelection,
    Article,
    ArticleAnalysis,
    KeyMessage,
    KeyMessageDraft,
    Statement,
)
from src.segmenter import SegmentedArticle, segment_article

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
ARTICLES_DIR = Path("data/articles")
ANALYSIS_DIR = Path("outputs/analysis")

client = OpenAI()

SYSTEM_PROMPT = """You are a media analyst for the marketing team of Gallagher Bassett (GB), a claims management company. You analyse published news articles in which GB appears.

Your first job is complete and accurate attribution: an inventory of everything in the article, not a selection. Deciding what is worth amplifying happens later, in another step.

The article is given in three views:
- Numbered paragraphs (P1, P2, ...), for context.
- Quoted segments (Q1, Q2, ...): every passage inside quotation marks, already split into separate segments.
- Sentences without quotation marks (S1, S2, ...).
You refer to items by their ID. Never write or rewrite article text yourself.

Rules:
1. gb_spokespeople: only people who work for Gallagher Bassett. People from other organizations are never GB spokespeople, even if they say similar things.
2. quote_attributions: exactly one entry for EVERY Q item, in order, with no exceptions. Give the full name and organization of the person speaking, using the paragraph context: attributions before or after the quote, and pronouns that refer back to a named person. If the quoted text is not a person's speech (for example, words quoted from a document), use null for speaker and organization.
3. sentence_attributions: exactly one entry for EVERY S item, in order, with no exceptions. Set conveys_gb_spokesperson to true when the sentence conveys what a GB spokesperson said, believes, recommends or prioritises. Apply standard news-writing attribution conventions:
   - An attribution at the end of a paragraph (for example "..., she said.") covers the preceding sentences of that paragraph that have no attribution of their own.
   - An unattributed sentence that follows a spokesperson's attributed sentence in the same paragraph continues that spokesperson's reported speech.
   - A pronoun (she, he) in an attribution refers to the most recently named person it can refer to, even if that person was named in a previous paragraph.
   - Sentences that report the spokesperson's views, plans or priorities count even without a speech verb.
   Set it to false for the reporter's own narration, statements by other organizations, facts about GB as a company and facts about a spokesperson's career. When true, give the spokesperson's full name as speaker.
4. key_messages: 2 to 5 messages that represent GB's position or expertise in this article, each written in your own words as one sentence, with the ID of the Q or S item that best supports it in supporting_id. Never attribute to GB ideas expressed by other organizations.
5. themes: 3 to 6 short labels (2 to 4 words) for the topics worth amplifying.
6. coverage_type:
   - expert_commentary: GB is one voice among several in an article about a broader industry topic.
   - feature: GB's commentary is central to the article or provides most of its substance.
   - announcement: news about GB itself (appointments, expansions, contracts, results).
   Explain your choice in one sentence in coverage_rationale.
7. other_organizations: every other organization quoted or mentioned. Mark as competitor any organization on this list: {competitors}, and any other company that provides claims administration or managed care services. Use legal for law firms and attorneys' associations, regulator for government bodies and courts, and other for everything else.
8. The article may contain more than one story (for example a related sidebar). Analyse all parts.
9. Use only information in the article. Never add facts, figures or context from outside it."""


def load_article(path: Path) -> Article:
    return Article.model_validate_json(path.read_text(encoding="utf-8"))


def build_user_message(article: Article, segmented: SegmentedArticle) -> str:
    paragraphs = "\n".join(f"P{i}: {p}" for i, p in enumerate(segmented.paragraphs, start=1))
    quotes = "\n".join(f"{q.id} (P{q.paragraph}): {q.text}" for q in segmented.quotes)
    sentences = "\n".join(f"{s.id} (P{s.paragraph}): {s.text}" for s in segmented.sentences)
    return (
        f"Outlet: {article.outlet}\nTitle: {article.title}\n"
        f"Published: {article.published_date}\nRegion: {article.region}\n\n"
        f"NUMBERED PARAGRAPHS:\n{paragraphs}\n\n"
        f"QUOTED SEGMENTS:\n{quotes}\n\n"
        f"SENTENCES WITHOUT QUOTATION MARKS:\n{sentences}"
    )


def select_items(article: Article, segmented: SegmentedArticle) -> AnalystSelection:
    completion = client.chat.completions.parse(
        model=MODEL,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(competitors=", ".join(COMPETITORS))},
            {"role": "user", "content": build_user_message(article, segmented)},
        ],
        response_format=AnalystSelection,
    )
    message = completion.choices[0].message
    record(completion, MODEL)
    if message.parsed is None:
        raise ValueError(f"Model did not return a valid selection: {message.refusal}")
    return message.parsed


def is_gb_speaker(speaker: str | None, gb_names: list[str]) -> bool:
    if not speaker:
        return False
    surname = speaker.split()[-1].lower()
    return any(surname in name.lower() for name in gb_names)


def check_coverage(attributed_ids: list[str], expected_ids: list[str], label: str) -> None:
    missing = [item_id for item_id in expected_ids if item_id not in attributed_ids]
    if missing:
        print(f"  ⚠ {label} not attributed by the model: {', '.join(missing)}")


def build_statements(selection: AnalystSelection, segmented: SegmentedArticle) -> list[Statement]:
    gb_names = [s.name for s in selection.gb_spokespeople]
    statements = []
    for quote in selection.quote_attributions:
        item = segmented.lookup(quote.id)
        if item and quote.id.startswith("Q") and is_gb_speaker(quote.speaker, gb_names):
            statements.append(Statement(speaker=quote.speaker, text=item.text, type="direct_quote"))
    for sentence in selection.sentence_attributions:
        item = segmented.lookup(sentence.id)
        if item and sentence.id.startswith("S") and sentence.conveys_gb_spokesperson:
            statements.append(Statement(speaker=sentence.speaker or gb_names[0], text=item.text, type="paraphrase"))
    return statements


def build_key_messages(drafts: list[KeyMessageDraft], segmented: SegmentedArticle) -> list[KeyMessage]:
    messages = []
    for draft in drafts:
        item = segmented.lookup(draft.supporting_id)
        if item is None:
            print(f"  ⚠ Ignored key message with invalid reference: {draft.supporting_id}")
            continue
        messages.append(KeyMessage(message=draft.message, supporting_excerpt=item.text))
    return messages


def assemble_analysis(selection: AnalystSelection, segmented: SegmentedArticle) -> ArticleAnalysis:
    check_coverage([q.id for q in selection.quote_attributions], [q.id for q in segmented.quotes], "Quotes")
    check_coverage([s.id for s in selection.sentence_attributions], [s.id for s in segmented.sentences], "Sentences")
    return ArticleAnalysis(
        coverage_type=selection.coverage_type,
        coverage_rationale=selection.coverage_rationale,
        gb_spokespeople=selection.gb_spokespeople,
        gb_statements=build_statements(selection, segmented),
        key_messages=build_key_messages(selection.key_messages, segmented),
        themes=selection.themes,
        other_organizations=selection.other_organizations,
    )


@observe(name="analyst")
def analyze_article(article: Article) -> ArticleAnalysis:
    segmented = segment_article(article.text)
    selection = select_items(article, segmented)
    return assemble_analysis(selection, segmented)


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