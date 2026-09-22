import os
import re
from pathlib import Path
from src.usage import record

from dotenv import load_dotenv
from langfuse import get_client, observe
from langfuse.openai import OpenAI

from src.schemas import (
    AmplificationKit,
    AmplificationPlan,
    Article,
    ArticleAnalysis,
    LinkedInPost,
    PublishablePost,
)

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
ARTICLES_DIR = Path("data/articles")
ANALYSIS_DIR = Path("outputs/analysis")
KITS_DIR = Path("outputs/kits")
VOICE_GUIDE_PATH = Path("src/voice_guide.md")

CTA_PATTERNS = ["read more in", "read the full", "learn more in", "discover more", "check out", "explore the full", "see the full"]

client = OpenAI()

SYSTEM_PROMPT = """You are a senior B2B social media writer on the marketing team of Gallagher Bassett (GB), a claims management company. You turn a published media placement into a coordinated LinkedIn amplification plan.

You receive a structured analysis of the article. Use only that information.

Write exactly three posts:
- company_page: posted from the GB company page. Credit the outlet and name the spokesperson with their title.
- spokesperson: a first-person draft for the GB spokesperson to review and post from their own profile.
- employee_advocacy: a short post any GB employee can share.

Fidelity rules (these always apply):
1. Quotation marks may only contain text from QUOTABLE statements, copied exactly, character by character, including capitalisation and punctuation. PARAPHRASE statements may be conveyed in your own words, but never inside quotation marks and never presented as direct speech. Set quote_used to the exact QUOTABLE text you used, or null.
2. Never mention other companies or organizations except the outlet. Never add facts, figures, claims or outcomes that are not in the analysis. Do not suggest that GB conducted research, created tools or achieved results unless the analysis says so.
3. Never include a URL. End each body with a call to action on its own line that ends with a colon (for example "Read the full article in Business Insurance:"); the link is added automatically after it.

Adaptation rules:
4. For expert_commentary and feature coverage, lead with the insight, in a direct tone. For announcement coverage, lead with the news; measured enthusiasm is appropriate.
5. Use the spelling of the article's region: Australian English for AU, British English for UK, American English for US.

Voice, structure, length, names, hashtags and emojis: follow the GB voice guide below. Return an empty hashtags list whenever the guide says no hashtags.

primary_angle: the single idea that ties the three posts together. rationale: one sentence on why this angle suits GB and this coverage.

GB VOICE GUIDE:
{voice_guide}"""


def load_model(path: Path, model):
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def build_system_prompt() -> str:
    voice_guide = VOICE_GUIDE_PATH.read_text(encoding="utf-8")
    return SYSTEM_PROMPT.format(voice_guide=voice_guide)


def format_statements(analysis: ArticleAnalysis) -> str:
    lines = []
    for statement in analysis.gb_statements:
        label = "QUOTABLE" if statement.type == "direct_quote" else "PARAPHRASE (not quotable)"
        lines.append(f"- [{label}] {statement.speaker}: {statement.text}")
    return "\n".join(lines)


def build_writer_message(article: Article, analysis: ArticleAnalysis) -> str:
    spokespeople = "\n".join(f"- {s.name}, {s.title}" for s in analysis.gb_spokespeople)
    messages = "\n".join(f"- {m.message}" for m in analysis.key_messages)
    return (
        f"Outlet: {article.outlet}\nHeadline: {article.title}\n"
        f"Published: {article.published_date}\nRegion: {article.region}\n"
        f"Coverage type: {analysis.coverage_type}\n\n"
        f"GB SPOKESPEOPLE:\n{spokespeople}\n\n"
        f"GB STATEMENTS:\n{format_statements(analysis)}\n\n"
        f"KEY MESSAGES:\n{messages}\n\n"
        f"THEMES: {', '.join(analysis.themes)}"
    )


@observe(name="writer")
def write_plan(article: Article, analysis: ArticleAnalysis) -> AmplificationPlan:
    completion = client.chat.completions.parse(
        model=MODEL,
        temperature=0.7,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": build_writer_message(article, analysis)},
        ],
        response_format=AmplificationPlan,
    )
    message = completion.choices[0].message
    record(completion, MODEL)
    if message.parsed is None:
        raise ValueError(f"Model did not return a valid plan: {message.refusal}")
    return message.parsed


def assemble_text(body: str, url: str, hashtags: list[str]) -> str:
    body = re.sub(r"\s*#\w+", "", body).strip()
    lines = [line.strip() for line in body.split("\n") if line.strip()]
    if lines and not lines[-1].endswith(":") and any(p in lines[-1].lower() for p in CTA_PATTERNS):
        lines[-1] = lines[-1].rstrip(".") + ":"
    body = "\n\n".join(lines)
    text = f"{body} {url}" if body.endswith(":") else f"{body}\n\n{url}"
    if hashtags:
        text += "\n\n" + " ".join(f"#{tag.lstrip('#')}" for tag in hashtags)
    return text


def assemble_post(post: LinkedInPost, article: Article) -> PublishablePost:
    text = assemble_text(post.body, article.url, post.hashtags)
    return PublishablePost(
        channel=post.channel,
        angle=post.angle,
        text=text,
        quote_used=post.quote_used,
        character_count=len(text),
    )


def build_kit(article: Article, plan: AmplificationPlan) -> AmplificationKit:
    return AmplificationKit(
        article_url=article.url,
        outlet=article.outlet,
        title=article.title,
        primary_angle=plan.primary_angle,
        rationale=plan.rationale,
        posts=[assemble_post(post, article) for post in plan.posts],
    )


def save_kit(kit: AmplificationKit, slug: str) -> Path:
    KITS_DIR.mkdir(parents=True, exist_ok=True)
    path = KITS_DIR / f"{slug}.json"
    path.write_text(kit.model_dump_json(indent=2), encoding="utf-8")
    return path


def print_kit(kit: AmplificationKit, path: Path) -> None:
    print(f"\n{'=' * 70}\n{kit.title}\nAngle: {kit.primary_angle}\n{'=' * 70}")
    for post in kit.posts:
        words = len(post.text.split())
        print(f"\n--- {post.channel.upper()} ({words} words, {post.character_count} chars) ---")
        print(post.text)
    print(f"\nSaved to: {path}")


if __name__ == "__main__":
    for article_path in sorted(ARTICLES_DIR.glob("*.json")):
        article = load_model(article_path, Article)
        analysis = load_model(ANALYSIS_DIR / article_path.name, ArticleAnalysis)
        kit = build_kit(article, write_plan(article, analysis))
        print_kit(kit, save_kit(kit, article_path.stem))
    get_client().flush()