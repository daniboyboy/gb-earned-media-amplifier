import sys
import time
from pathlib import Path

from langfuse import get_client, observe
from pydantic import BaseModel

from src.analyst import analyze_article
from src.ingest import fetch_article, save_article
from src.reviewer import review_kit
from src.schemas import AmplificationKit, Article, ArticleAnalysis, KitReview
from src.writer import build_kit, write_plan

RESULTS_DIR = Path("outputs/results")
DEFAULT_URL = "https://www.businessinsurance.com/accurate-job-descriptions-aid-return-to-work/"


class AmplificationResult(BaseModel):
    slug: str
    article: Article
    analysis: ArticleAnalysis
    kit: AmplificationKit
    review: KitReview
    timings: dict[str, float]


def timed(timings: dict, step: str, func, *args):
    start = time.perf_counter()
    result = func(*args)
    timings[step] = round(time.perf_counter() - start, 1)
    print(f"  ✔ {step} ({timings[step]}s)")
    return result


@observe(name="pipeline")
def run_pipeline(url: str) -> AmplificationResult:
    timings = {}
    article = timed(timings, "ingest", fetch_article, url)
    slug = save_article(article).stem
    analysis = timed(timings, "analyse", analyze_article, article)
    plan = timed(timings, "write", write_plan, article, analysis)
    kit = build_kit(article, plan)
    review = timed(timings, "review", review_kit, kit, article, analysis)
    return AmplificationResult(slug=slug, article=article, analysis=analysis, kit=kit, review=review, timings=timings)


def save_result(result: AmplificationResult) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{result.slug}.json"
    path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    return path


def print_result(result: AmplificationResult, path: Path) -> None:
    reviews = {post.channel: post for post in result.review.posts}
    print(f"\n{'=' * 70}\n{result.article.title}\nAngle: {result.kit.primary_angle}\n{'=' * 70}")
    for post in result.kit.posts:
        review = reviews[post.channel]
        status = "✔ APPROVED" if review.approved else "✘ NEEDS CHANGES"
        print(f"\n--- {post.channel.upper()}: {status} ---\n{post.text}")
        for issue in review.issues:
            icon = "⛔" if issue.severity == "blocker" else "⚠"
            print(f"   {icon} [{issue.category}] \"{issue.phrase[:70]}\"")
    print(f"\nTotal time: {sum(result.timings.values()):.1f}s | Saved to: {path}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print(f"Running pipeline for: {url}")
    try:
        result = run_pipeline(url)
        print_result(result, save_result(result))
    except ValueError as error:
        print(f"\n✘ {error}")
    finally:
        get_client().flush()