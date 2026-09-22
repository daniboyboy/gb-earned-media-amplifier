import sys
import time
from pathlib import Path

from langfuse import get_client, observe
from pydantic import BaseModel

from src.analyst import analyze_article
from src.ingest import fetch_article, save_article
from src.reviewer import review_kit
from src.schemas import AmplificationKit, Article, ArticleAnalysis, KitReview
from src.usage import track_usage
from src.writer import build_kit, write_plan

RESULTS_DIR = Path("outputs/results")
DEFAULT_URL = "https://www.businessinsurance.com/accurate-job-descriptions-aid-return-to-work/"


class StageMetrics(BaseModel):
    seconds: float
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    calls: int = 0


class AmplificationResult(BaseModel):
    slug: str
    article: Article
    analysis: ArticleAnalysis
    kit: AmplificationKit
    review: KitReview
    metrics: dict[str, StageMetrics]


def timed(metrics: dict, step: str, func, *args):
    start = time.perf_counter()
    with track_usage() as usage:
        result = func(*args)
    metrics[step] = StageMetrics(seconds=round(time.perf_counter() - start, 1), **usage)
    print(f"  ✔ {step} ({metrics[step].seconds}s, ${metrics[step].cost_usd:.4f})")
    return result


def total_cost(metrics: dict) -> float:
    return round(sum(stage.cost_usd for stage in metrics.values()), 4)


def total_seconds(metrics: dict) -> float:
    return round(sum(stage.seconds for stage in metrics.values()), 1)


@observe(name="pipeline")
def run_pipeline(url: str) -> AmplificationResult:
    metrics = {}
    article = timed(metrics, "ingest", fetch_article, url)
    slug = save_article(article).stem
    analysis = timed(metrics, "analyse", analyze_article, article)
    plan = timed(metrics, "write", write_plan, article, analysis)
    kit = build_kit(article, plan)
    review = timed(metrics, "review", review_kit, kit, article, analysis)
    return AmplificationResult(slug=slug, article=article, analysis=analysis, kit=kit, review=review, metrics=metrics)


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
    print(f"\nTotal: {total_seconds(result.metrics)}s · ${total_cost(result.metrics):.4f} | Saved to: {path}")


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    print(f"Running pipeline for: {url}")
    try:
        result = run_pipeline(url)
        print_result(result, save_result(result))
    except ValueError as error:
        print(f"\n✘ {error}")
    finally:
        try:
            get_client().flush()
        except Exception:
            pass