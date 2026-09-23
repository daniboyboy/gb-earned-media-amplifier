# Amplifier â€” earned media to LinkedIn

An AI agent that turns a published media article into a coordinated LinkedIn amplification kit for a marketing team.

**Live app: https://gb-earned-media-amplifier-test.onrender.com**

Built by Daniel Duque for the Gallagher Bassett case study. Not affiliated with Gallagher Bassett.

## Before you open it

- The app runs on a free Render instance that sleeps after 15 minutes without traffic. The first visit can take up to a minute to wake it up.
- Three articles are already processed and visible immediately. You can also paste any article URL and watch the agent run; this takes about 30 seconds and uses my own OpenAI account, at roughly $0.05 per run.
- Nothing is ever published. Every post is a draft waiting for a person to approve it.

## What it does

| Brief requirement | How it is met |
|---|---|
| Ingest or analyse the published article | Extracts clean body text and metadata (outlet, date, region) from a URL |
| Identify key GB messages, spokesperson commentary and themes | An analyst agent attributes every quote and sentence in the article, then reports GB spokespeople, verbatim quotes, key messages and themes |
| Develop appropriate LinkedIn copy | A writer agent produces three coordinated drafts â€” company page, spokesperson and employee advocacy â€” in GB's observed LinkedIn voice |
| Retain a link back to the original media placement | The link is appended by code, never written by a model, and the reviewer verifies it appears exactly once |

Beyond the minimum, a reviewer agent fact-checks every claim in every draft against the source article before a person sees it.

## How it works

    URL â†’ Ingest â†’ Analyst â†’ Writer â†’ Reviewer â†’ Amplification kit

**Ingest** (`src/ingest.py`) extracts the article text and captures the URL, outlet, publication date and region deterministically.

**Analyst** (`src/analyst.py`, `src/segmenter.py`) does not let the model write article text. Code splits the article into numbered quoted segments and sentences; the model attributes every one of them; code rebuilds the analysis from the original text. Verbatim fidelity is therefore a property of the architecture, not of a prompt.

**Writer** (`src/writer.py`) works from the validated analysis, never from the raw article. It never sees competitor names, so it cannot leak one into a post. Only verified direct quotes may appear inside quotation marks. The observed GB voice is documented in `src/voice_guide.md`.

**Reviewer** (`src/reviewer.py`) has two layers. Code verifies what can be verified with certainty: the link appears once, no competitor names, quoted text matches the source, no figures absent from the article, length within range. An LLM judge then checks each claim against the full article and runs a voice checklist whose applicable rules are selected by code. Fidelity problems block a post; voice problems are warnings. Final approval always belongs to a person.

## Evaluation

`eval/golden_set.json` holds a human-annotated ground truth for the three articles. `src/evaluate.py` measures the analyst against it, with no LLM involved.

Analyst results on the development set:

| Metric | Result |
|---|---|
| Coverage type | 3/3 |
| GB spokespeople | 3/3 |
| Direct quotes | 6/6 |
| Paraphrases | 11/11 |
| Competitors identified | 7/7 |
| Competitor statements attributed to GB | 0 |
| Non-verbatim excerpts | 0 |

`eval/writer_issues.json` holds 10 human-annotated problems in 9 frozen drafts, used to measure the reviewer (`src/evaluate_reviewer.py`): 4 of 6 blockers detected, 7 of 9 approval decisions correct.

Every design decision and prompt iteration, including the ones that failed, is documented in `DECISIONS.md`.

## Time and cost

Measured per article, shown in the app:

| Article | Time | Cost |
|---|---|---|
| Accurate job descriptions aid return to work | 36.2 s | $0.065 |
| Automated drug reviews promise comp savings | 31.0 s | $0.056 |
| Gallagher Bassett names SA GM | 28.5 s | $0.049 |

Review costs about four times more than drafting, because each post is fact-checked against the full article. That is a deliberate design choice.

## Running it locally

    git clone https://github.com/daniboyboy/gb-earned-media-amplifier.git
    cd gb-earned-media-amplifier
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env

Add your OpenAI API key to `.env`, then either run the web app:

    uvicorn src.api:app --reload

or a single article from the command line:

    python -m src.pipeline https://www.businessinsurance.com/accurate-job-descriptions-aid-return-to-work/

## Known limitations

- **No held-out test set.** All three articles were used while iterating on the prompts, so the results above are development-set scores, not a measure of generalisation. A cleaner protocol would have reserved one article for testing.
- **The reviewer catches most, not all.** It detected 4 of 6 annotated blockers. The ones it misses are subtle distortions. This is why a person approves every post.
- **Spokesperson titles come from the article** and may differ from internal titles. The app flags this for human verification.
- **Registration walls.** Articles behind a login cannot be ingested from a URL. A paste-the-text fallback is designed but not built.
- **New results do not persist.** Articles processed through the live app are lost when the free instance restarts; the three preloaded ones always remain.
- **The competitor list is manual** (`src/config.py`), supplemented by the model's judgement for organisations not on it.

## Next steps

- Automatic detection of new coverage, so amplification starts without anyone pasting a URL
- More channels: email and blog snippets from the same analysis
- Measurement through GB's existing link tracking
- A cheaper model for mechanical steps, keeping the stronger one for fact-checking
