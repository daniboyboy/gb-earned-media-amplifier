import json
from pathlib import Path

from src.schemas import Article, ArticleAnalysis
from src.text_utils import is_verbatim, normalize

GOLDEN_PATH = Path("eval/golden_set.json")
ARTICLES_DIR = Path("data/articles")
ANALYSIS_DIR = Path("outputs/analysis")
REPORT_PATH = Path("outputs/eval_report.json")

METRICS = [
    ("spokespeople", "Spokespeople"),
    ("direct_quotes", "Direct quotes"),
    ("paraphrases", "Paraphrases"),
    ("competitors", "Competitors"),
]


def load_model(path: Path, model):
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def recall(expected: list[str], is_found) -> dict:
    missing = [item for item in expected if not is_found(item)]
    return {"found": len(expected) - len(missing), "expected": len(expected), "missing": missing}


def evaluate_article(golden: dict, analysis: ArticleAnalysis, article: Article) -> dict:
    names = [normalize(s.name).lower() for s in analysis.gb_spokespeople]
    quotes = [normalize(s.text) for s in analysis.gb_statements if s.type == "direct_quote"]
    statements = [normalize(s.text) for s in analysis.gb_statements]
    competitors = [o.name.lower() for o in analysis.other_organizations if o.relation == "competitor"]
    excerpts = [s.text for s in analysis.gb_statements] + [m.supporting_excerpt for m in analysis.key_messages]
    return {
        "coverage_type_ok": analysis.coverage_type == golden["coverage_type"],
        "spokespeople": recall(golden["gb_spokespeople"], lambda n: normalize(n).lower() in names),
        "unexpected_spokespeople": [s.name for s in analysis.gb_spokespeople if s.name not in golden["gb_spokespeople"]],
        "direct_quotes": recall(golden["direct_quotes"], lambda q: normalize(q) in quotes),
        "paraphrases": recall(golden["paraphrase_anchors"], lambda a: any(normalize(a) in s for s in statements)),
        "competitors": recall(golden["competitors"], lambda c: any(c.lower() in x for x in competitors)),
        "not_verbatim": [e for e in excerpts if not is_verbatim(e, article.text)],
    }


def mark(ok: bool) -> str:
    return "✔" if ok else "✘"


def print_result(slug: str, result: dict) -> None:
    print(f"\n{slug}")
    print(f"  {mark(result['coverage_type_ok'])} Coverage type")
    for key, label in METRICS:
        score = result[key]
        print(f"  {mark(not score['missing'])} {label}: {score['found']}/{score['expected']}")
        for item in score["missing"]:
            print(f"      missing: {item[:90]}")
    unexpected = result["unexpected_spokespeople"]
    print(f"  {mark(not unexpected)} Unexpected spokespeople: {', '.join(unexpected) or 'none'}")
    print(f"  {mark(not result['not_verbatim'])} Non-verbatim excerpts: {len(result['not_verbatim'])}")
    for text in result["not_verbatim"]:
        print(f"      {text[:90]}")


def print_totals(results: dict) -> None:
    print("\nTOTAL")
    coverage_ok = sum(r["coverage_type_ok"] for r in results.values())
    print(f"  Coverage type: {coverage_ok}/{len(results)}")
    for key, label in METRICS:
        found = sum(r[key]["found"] for r in results.values())
        expected = sum(r[key]["expected"] for r in results.values())
        print(f"  {label}: {found}/{expected}")
    print(f"  Non-verbatim excerpts: {sum(len(r['not_verbatim']) for r in results.values())}")


if __name__ == "__main__":
    golden_set = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    results = {}
    for slug, golden in golden_set.items():
        article = load_model(ARTICLES_DIR / f"{slug}.json", Article)
        analysis = load_model(ANALYSIS_DIR / f"{slug}.json", ArticleAnalysis)
        results[slug] = evaluate_article(golden, analysis, article)
        print_result(slug, results[slug])
    print_totals(results)
    REPORT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")