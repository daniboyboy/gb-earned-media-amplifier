import json
from pathlib import Path

from src.schemas import KitReview, PostReview, ReviewIssue
from src.text_utils import normalize

GOLDEN_PATH = Path("eval/writer_issues.json")
REVIEWS_DIR = Path("outputs/reviews")
MIN_PHRASE_LENGTH = 8
MIN_WORD_OVERLAP = 0.75


def matches(anchor: str, phrase: str) -> bool:
    a, p = normalize(anchor).lower(), normalize(phrase).lower()
    if a in p or (len(p) >= MIN_PHRASE_LENGTH and p in a):
        return True
    anchor_words = set(a.split())
    return len(anchor_words & set(p.split())) / len(anchor_words) >= MIN_WORD_OVERLAP


def is_found(expected: dict, issues: list[ReviewIssue]) -> bool:
    candidates = [i for i in issues if expected["severity"] == "warning" or i.severity == "blocker"]
    return any(matches(expected["phrase"], i.phrase) for i in candidates)


def evaluate_post(expected: list[dict], review: PostReview) -> dict:
    found = [e for e in expected if is_found(e, review.issues)]
    unexpected = [i for i in review.issues if not any(matches(e["phrase"], i.phrase) for e in expected)]
    should_approve = not any(e["severity"] == "blocker" for e in expected)
    return {"expected": expected, "found": found, "unexpected": unexpected, "approval_ok": review.approved == should_approve}


def print_post_result(channel: str, result: dict) -> None:
    print(f"  {channel}: {'✔' if result['approval_ok'] else '✘'} approval decision")
    for issue in result["expected"]:
        mark = "✔" if issue in result["found"] else "✘"
        print(f"    {mark} expected [{issue['severity']}] {issue['phrase']}")
    for issue in result["unexpected"]:
        print(f"    + extra [{issue.severity}] [{issue.category}] {issue.phrase[:70]}")


def count(results: list[dict], key: str, severity: str) -> int:
    return sum(1 for r in results for e in r[key] if e["severity"] == severity)


def print_totals(results: list[dict]) -> None:
    print("\nTOTAL")
    for severity in ("blocker", "warning"):
        print(f"  {severity.capitalize()}s found: {count(results, 'found', severity)}/{count(results, 'expected', severity)}")
    print(f"  Correct approval decisions: {sum(r['approval_ok'] for r in results)}/{len(results)}")
    extra_blockers = sum(1 for r in results for i in r["unexpected"] if i.severity == "blocker")
    extra_warnings = sum(1 for r in results for i in r["unexpected"] if i.severity == "warning")
    print(f"  Extra blockers to review manually: {extra_blockers}")
    print(f"  Extra warnings (noise to review): {extra_warnings}")


if __name__ == "__main__":
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    results = []
    for slug, channels in golden.items():
        review = KitReview.model_validate_json((REVIEWS_DIR / f"{slug}.json").read_text(encoding="utf-8"))
        posts = {post.channel: post for post in review.posts}
        print(f"\n{slug}")
        for channel, expected in channels.items():
            result = evaluate_post(expected, posts[channel])
            print_post_result(channel, result)
            results.append(result)
    print_totals(results)