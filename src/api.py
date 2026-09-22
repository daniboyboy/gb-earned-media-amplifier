import threading
import time
import uuid
from collections import deque
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.analyst import analyze_article
from src.ingest import fetch_article, save_article
from src.pipeline import RESULTS_DIR, AmplificationResult, StageMetrics, save_result, total_cost, total_seconds
from src.reviewer import review_kit
from src.usage import track_usage
from src.writer import build_kit, write_plan

STAGES = ["ingest", "analyse", "write", "review"]
PRELOADED_DIR = Path("data/preloaded")
WEB_DIR = Path("web")
MAX_JOBS_PER_HOUR = 20

app = FastAPI(title="GB Earned Media Amplifier")

jobs: dict[str, dict] = {}
recent_jobs: deque[float] = deque()


class JobRequest(BaseModel):
    url: str


def rate_limited() -> bool:
    now = time.time()
    while recent_jobs and now - recent_jobs[0] > 3600:
        recent_jobs.popleft()
    return len(recent_jobs) >= MAX_JOBS_PER_HOUR


def new_job(url: str) -> dict:
    empty = {"state": "pending", "seconds": None, "detail": None, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}
    return {
        "status": "running",
        "url": url,
        "stages": {stage: dict(empty) for stage in STAGES},
        "error": None,
        "slug": None,
        "result": None,
    }


def start_stage(job: dict, stage: str) -> float:
    job["stages"][stage]["state"] = "running"
    return time.perf_counter()


def finish_stage(job: dict, stage: str, started: float, detail: str, usage: dict) -> None:
    job["stages"][stage].update(
        state="done",
        seconds=round(time.perf_counter() - started, 1),
        detail=detail,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cost_usd=usage.get("cost_usd", 0.0),
        calls=usage.get("calls", 0),
    )


def stage_metrics(job: dict) -> dict[str, StageMetrics]:
    return {
        stage: StageMetrics(
            seconds=job["stages"][stage]["seconds"] or 0.0,
            input_tokens=job["stages"][stage]["input_tokens"],
            output_tokens=job["stages"][stage]["output_tokens"],
            cost_usd=job["stages"][stage]["cost_usd"],
            calls=job["stages"][stage]["calls"],
        )
        for stage in STAGES
    }


def run_job(job_id: str, url: str) -> None:
    job = jobs[job_id]
    try:
        started = start_stage(job, "ingest")
        article = fetch_article(url)
        slug = save_article(article).stem
        finish_stage(job, "ingest", started, f"{len(article.text.split())} words · {article.outlet} · {article.region}", {})

        started = start_stage(job, "analyse")
        with track_usage() as usage:
            analysis = analyze_article(article)
        quotes = sum(s.type == "direct_quote" for s in analysis.gb_statements)
        competitors = sum(o.relation == "competitor" for o in analysis.other_organizations)
        names = ", ".join(s.name for s in analysis.gb_spokespeople) or "no GB spokesperson found"
        finish_stage(job, "analyse", started, f"{names} · {quotes} direct quotes · {competitors} competitors excluded", usage)

        started = start_stage(job, "write")
        with track_usage() as usage:
            kit = build_kit(article, write_plan(article, analysis))
        finish_stage(job, "write", started, f"{len(kit.posts)} drafts written", usage)

        started = start_stage(job, "review")
        with track_usage() as usage:
            review = review_kit(kit, article, analysis)
        cleared = sum(post.approved for post in review.posts)
        finish_stage(job, "review", started, f"{cleared} of {len(review.posts)} cleared", usage)

        result = AmplificationResult(
            slug=slug, article=article, analysis=analysis, kit=kit, review=review, metrics=stage_metrics(job)
        )
        save_result(result)
        job["slug"] = slug
        job["result"] = result.model_dump()
        job["status"] = "done"
    except Exception as error:
        job["status"] = "error"
        job["error"] = str(error)
        for stage in job["stages"].values():
            if stage["state"] == "running":
                stage["state"] = "failed"


def result_paths() -> dict[str, Path]:
    paths = {path.stem: path for path in sorted(PRELOADED_DIR.glob("*.json"))} if PRELOADED_DIR.exists() else {}
    if RESULTS_DIR.exists():
        paths.update({path.stem: path for path in sorted(RESULTS_DIR.glob("*.json"))})
    return paths


def load_result(path: Path) -> AmplificationResult:
    return AmplificationResult.model_validate_json(path.read_text(encoding="utf-8"))


def summarise(result: AmplificationResult) -> dict:
    return {
        "slug": result.slug,
        "title": result.article.title,
        "outlet": result.article.outlet,
        "published_date": result.article.published_date,
        "region": result.article.region,
        "coverage_type": result.analysis.coverage_type,
        "spokespeople": [s.name for s in result.analysis.gb_spokespeople],
        "cleared": sum(post.approved for post in result.review.posts),
        "total": len(result.review.posts),
        "seconds": total_seconds(result.metrics),
        "cost_usd": total_cost(result.metrics),
    }


@app.post("/api/jobs")
def create_job(request: JobRequest) -> dict:
    if rate_limited():
        raise HTTPException(status_code=429, detail="This demo allows 20 runs per hour. Please try again later.")
    recent_jobs.append(time.time())
    job_id = uuid.uuid4().hex[:12]
    jobs[job_id] = new_job(request.url)
    threading.Thread(target=run_job, args=(job_id, request.url), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Unknown job")
    return jobs[job_id]


@app.get("/api/results")
def list_results() -> list[dict]:
    return [summarise(load_result(path)) for path in result_paths().values()]


@app.get("/api/results/{slug}")
def get_result(slug: str) -> dict:
    path = result_paths().get(slug)
    if path is None:
        raise HTTPException(status_code=404, detail="Unknown result")
    return load_result(path).model_dump()


app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")