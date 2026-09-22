import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langfuse import get_client, observe
from langfuse.openai import OpenAI

from src.config import COMPETITORS
from src.schemas import (
    AmplificationKit,
    Article,
    ArticleAnalysis,
    FidelityVerdict,
    KitReview,
    PostReview,
    PublishablePost,
    ReviewIssue,
    VoiceChecklist,
)
from src.text_utils import normalize

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
JUDGE_MODEL = os.getenv("JUDGE_MODEL", MODEL)
ARTICLES_DIR = Path("data/articles")
FIXTURES_DIR = Path("eval/fixtures")
REVIEWS_DIR = Path("outputs/reviews")
VOICE_GUIDE_PATH = Path("src/voice_guide.md")

WORD_RANGES = {"company_page": (30, 90), "spokesperson": (50, 120), "employee_advocacy": (25, 60)}
QUOTE_PATTERN = re.compile(r"“([^”]+)”|\"([^\"]+)\"")
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*%?")
VERDICT_CATEGORIES = {"unsupported": "unsupported_claim", "distorted": "distortion", "misattributed": "misattribution"}

VOICE_RULES = {
    "opening_news": ("structure", "The news (what happened, and to whom) appears in the first two sentences."),
    "opening_insight": ("structure", "The post opens with the key insight, or with a question that frames it."),
    "no_enthusiasm": ("tone", "The post contains no expressions of enthusiasm or excitement (for example excited, thrilled, delighted, exciting)."),
    "no_cliches": ("tone", "The post contains no clichés or hype from the voice guide's avoid list, and no superlatives or success claims about GB itself. Expressions of enthusiasm are covered by a separate rule, and words describing topics other than GB are not superlatives about GB."),
    "cta_outlet": ("structure", "The post ends with a call to action that names the outlet."),
    "no_self_quote": ("style", "The spokesperson does not quote themselves in quotation marks in their own first-person post."),
}

client = OpenAI()

FIDELITY_PROMPT = """You are a fact-checker on the marketing team of Gallagher Bassett (GB), a claims management company. You check one LinkedIn draft that promotes a published news article in which GB appears.

Split the draft into atomic claims. A compound sentence contains several claims: check every subject-action pair separately (who or what does what). Include hooks and questions that frame a topic, predictions, and characterisations of GB, the spokesperson, their role, the topic or the industry. Ignore the call to action.

Skip only statements of a person's own feelings about themselves or the conversation (for example "I'm excited to...", "we're proud to...", "honoured to..."). They are checked elsewhere. Characterisations of a topic, a field or a situation (for example "an exciting time for X", "a critical issue") are claims and must be judged.

For each claim, copy a short, exact phrase from the draft and judge it against the ARTICLE TEXT:
- supported: the article states or clearly implies it, about the same subject.
- unsupported: the article does not say it. This includes predictions about the future, claims of success or impact, and added benefits.
- distorted: the article says something related, but the draft changes its meaning, scope or subject. This includes attributing a capability or action to the wrong tool, team or subject, and changing a precise term for a looser one (for example "permanent" to "new").
- misattributed: the draft presents as GB's view or topic something that, in the article, comes from another organization.

Give the article sentence you relied on as evidence, and make sure your explanation is consistent with the article. Be strict: a faithful paraphrase is supported, but any change of subject, scope or certainty is not."""

VOICE_PROMPT = """You are a brand editor on the marketing team of Gallagher Bassett (GB). You check one LinkedIn draft against a fixed list of rules.

Return exactly one check for each rule listed in the message, using its rule_id, and judge only those rules. Set passed to true when the draft complies. When it fails, copy the short, exact phrase from the draft that breaks the rule and explain why in one sentence.

The link to the article is added automatically after the call to action, so it is not in the draft. Do not check for the link itself.

GB voice guide, for reference:
{voice_guide}"""


def load_model(path: Path, model):
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def post_body(post: PublishablePost, url: str) -> str:
    body = post.text.replace(url, "")
    return re.sub(r"#\w+", "", body).strip()


def rule_issue(phrase: str, category: str, explanation: str, severity: str = "blocker") -> ReviewIssue:
    return ReviewIssue(phrase=phrase, category=category, severity=severity, explanation=explanation, source="rule")


def check_link(post: PublishablePost, url: str) -> list[ReviewIssue]:
    count = post.text.count(url)
    if count == 1:
        return []
    return [rule_issue(url, "link", f"The original article link appears {count} times; it must appear exactly once.")]


def competitor_names(analysis: ArticleAnalysis) -> list[str]:
    found = [o.name for o in analysis.other_organizations if o.relation == "competitor"]
    return list(dict.fromkeys(COMPETITORS + found))


def check_competitors(body: str, analysis: ArticleAnalysis) -> list[ReviewIssue]:
    lowered = body.lower()
    return [
        rule_issue(name, "competitor_mention", f"The draft mentions {name}, a competitor.")
        for name in competitor_names(analysis)
        if name.lower() in lowered
    ]


def check_quotes(body: str, analysis: ArticleAnalysis) -> list[ReviewIssue]:
    quotable = [normalize(s.text) for s in analysis.gb_statements if s.type == "direct_quote"]
    issues = []
    for match in QUOTE_PATTERN.finditer(body):
        quoted = match.group(1) or match.group(2)
        if not any(normalize(quoted) in quote for quote in quotable):
            issues.append(rule_issue(quoted, "misquote", "Text in quotation marks does not match any direct quote in the article."))
    return issues


def check_numbers(body: str, article: Article) -> list[ReviewIssue]:
    return [
        rule_issue(number, "unsupported_claim", f"The figure {number} does not appear in the article.")
        for number in NUMBER_PATTERN.findall(body)
        if number not in article.text
    ]


def check_length(body: str, channel: str) -> list[ReviewIssue]:
    low, high = WORD_RANGES.get(channel, (0, 10_000))
    words = len(body.split())
    if low <= words <= high:
        return []
    return [rule_issue(channel, "length", f"{words} words; the voice guide range for {channel} is {low} to {high}.", severity="warning")]


def rule_checks(post: PublishablePost, article: Article, analysis: ArticleAnalysis) -> list[ReviewIssue]:
    body = post_body(post, article.url)
    return (
        check_link(post, article.url)
        + check_competitors(body, analysis)
        + check_quotes(body, analysis)
        + check_numbers(body, article)
        + check_length(body, post.channel)
    )


def parse_with(model_name: str, system: str, user: str, response_format):
    extra = {"temperature": 0} if model_name.startswith("gpt-4") else {}
    completion = client.chat.completions.parse(
        model=model_name,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format=response_format,
        **extra,
    )
    message = completion.choices[0].message
    if message.parsed is None:
        raise ValueError(f"Judge did not return a valid response: {message.refusal}")
    return message.parsed


def build_fidelity_message(post: PublishablePost, article: Article, analysis: ArticleAnalysis) -> str:
    spokespeople = ", ".join(f"{s.name} ({s.title})" for s in analysis.gb_spokespeople)
    return (
        f"Channel: {post.channel}\nGB spokespeople: {spokespeople}\n\n"
        f"ARTICLE TEXT:\n{article.text}\n\n"
        f"LINKEDIN DRAFT:\n{post_body(post, article.url)}"
    )


@observe(name="fidelity_judge")
def judge_fidelity(post: PublishablePost, article: Article, analysis: ArticleAnalysis) -> list[ReviewIssue]:
    verdict = parse_with(JUDGE_MODEL, FIDELITY_PROMPT, build_fidelity_message(post, article, analysis), FidelityVerdict)
    return [
        ReviewIssue(phrase=c.phrase, category=VERDICT_CATEGORIES[c.verdict], severity="blocker", explanation=c.explanation, source="judge")
        for c in verdict.claims
        if c.verdict != "supported"
    ]


def applicable_rules(channel: str, coverage_type: str) -> list[str]:
    rules = ["opening_news"] if coverage_type == "announcement" else ["opening_insight", "no_enthusiasm"]
    rules += ["no_cliches", "cta_outlet"]
    if channel == "spokesperson":
        rules.append("no_self_quote")
    return rules


def build_voice_message(post: PublishablePost, article: Article, rules: list[str]) -> str:
    rule_lines = "\n".join(f"- {rule_id}: {VOICE_RULES[rule_id][1]}" for rule_id in rules)
    return (
        f"Channel: {post.channel}\nOutlet: {article.outlet}\n\n"
        f"RULES:\n{rule_lines}\n\n"
        f"LINKEDIN DRAFT:\n{post_body(post, article.url)}"
    )


@observe(name="voice_judge")
def judge_voice(post: PublishablePost, article: Article, analysis: ArticleAnalysis) -> list[ReviewIssue]:
    rules = applicable_rules(post.channel, analysis.coverage_type)
    system = VOICE_PROMPT.format(voice_guide=VOICE_GUIDE_PATH.read_text(encoding="utf-8"))
    checklist = parse_with(MODEL, system, build_voice_message(post, article, rules), VoiceChecklist)
    return [
        ReviewIssue(
            phrase=check.phrase or "",
            category=VOICE_RULES[check.rule_id][0],
            severity="warning",
            explanation=f"{check.rule_id}: {check.explanation}",
            source="judge",
        )
        for check in checklist.checks
        if check.rule_id in rules and not check.passed
    ]


def review_post(post: PublishablePost, article: Article, analysis: ArticleAnalysis) -> PostReview:
    issues = rule_checks(post, article, analysis) + judge_fidelity(post, article, analysis) + judge_voice(post, article, analysis)
    approved = not any(issue.severity == "blocker" for issue in issues)
    return PostReview(channel=post.channel, approved=approved, issues=issues)


@observe(name="reviewer")
def review_kit(kit: AmplificationKit, article: Article, analysis: ArticleAnalysis) -> KitReview:
    return KitReview(title=kit.title, posts=[review_post(post, article, analysis) for post in kit.posts])


def save_review(review: KitReview, slug: str) -> Path:
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    path = REVIEWS_DIR / f"{slug}.json"
    path.write_text(review.model_dump_json(indent=2), encoding="utf-8")
    return path


def print_review(review: KitReview, path: Path) -> None:
    print(f"\n{'=' * 70}\n{review.title}\n{'=' * 70}")
    for post in review.posts:
        status = "✔ APPROVED" if post.approved else "✘ NEEDS CHANGES"
        print(f"\n{post.channel.upper()}: {status}")
        for issue in post.issues:
            icon = "⛔" if issue.severity == "blocker" else "⚠"
            print(f"   {icon} [{issue.category}] \"{issue.phrase[:70]}\" ({issue.source})")
            print(f"      {issue.explanation[:140]}")
    print(f"\nSaved to: {path}")


if __name__ == "__main__":
    print(f"Fidelity judge model: {JUDGE_MODEL} | Voice judge model: {MODEL}")
    for kit_path in sorted((FIXTURES_DIR / "kits").glob("*.json")):
        kit = load_model(kit_path, AmplificationKit)
        article = load_model(ARTICLES_DIR / kit_path.name, Article)
        analysis = load_model(FIXTURES_DIR / "analysis" / kit_path.name, ArticleAnalysis)
        review = review_kit(kit, article, analysis)
        print_review(review, save_review(review, kit_path.stem))
    get_client().flush()