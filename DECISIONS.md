# Design Decisions and Prompt Iterations

## Evaluation approach
- Golden set (`eval/golden_set.json`): human-annotated ground truth for 3 real articles — expected GB spokespeople, exact direct quotes, paraphrase anchors, competitors and coverage type.
- Evaluation (`src/evaluate.py`): deterministic, no LLM. Measures recall per category and verifies that every extracted statement and supporting excerpt exists verbatim in the source article (after normalising quotes, whitespace and edge punctuation).

## Baseline (prompt v1)

| Metric | Result |
|---|---|
| Coverage type | 3/3 |
| Spokespeople | 3/3 |
| Competitors | 7/7 |
| Unexpected spokespeople | 0 |
| Direct quotes | 4/6 |
| Paraphrases | 6/9 |
| Non-verbatim excerpts | 2 |

Failure analysis:
1. An interrupted quote ("...," Ms. Simpson said. "...") was merged into a single string that does not exist verbatim in the article.
2. A paraphrase attributed only through a pronoun ("she said") was missed.
3. Sentences reporting a spokesperson's views or priorities, rather than direct speech, were missed.

Attribution was fully correct: no competitor spokesperson was attributed to GB.

## Iteration 1 (prompt v2)

Change: rewrote rule 2 to (a) require a paragraph-by-paragraph pass, (b) give an explicit example of splitting interrupted quotes, (c) include pronoun-attributed sentences and sentences reporting views or priorities, (d) allow omitting only the attribution clause in paraphrases.

Guard against overfitting: the example in the prompt is generic and not taken from any golden set article.

Results: pending.

## Iteration 1 (prompt v2)

Change: rewrote rule 2 to (a) require a paragraph-by-paragraph pass, (b) give an explicit example of splitting interrupted quotes, (c) include pronoun-attributed sentences and sentences reporting views or priorities, (d) allow omitting only the attribution clause in paraphrases.

Guard against overfitting: the example in the prompt is generic and not taken from any golden set article.

| Metric | Baseline | v2 |
|---|---|---|
| Direct quotes | 4/6 | 4/6 |
| Paraphrases | 6/9 | 6/9 |
| Non-verbatim excerpts | 2 | 1 |

Conclusion: prompt instructions did not change extraction behaviour. The model still merged the interrupted quote and missed the same paraphrases. The root cause is architectural: the model is asked both to judge (attribution, relevance) and to copy text verbatim, and LLMs are unreliable copiers. Next step: move text handling to deterministic code and restrict the model to selecting numbered items.

## Iteration 2 (architecture v3: select by ID)

Change: text handling moved to deterministic code. `src/segmenter.py` numbers every quoted segment (Q) and every unquoted sentence (S). The model returns item IDs only; code assembles the analysis from the original text.

| Metric | Baseline | v2 | v3 |
|---|---|---|---|
| Direct quotes | 4/6 | 4/6 | 4/6 |
| Paraphrases | 6/9 | 6/9 | 7/9 |
| Non-verbatim excerpts | 2 | 1 | 0 |

Result: verbatim fidelity is now guaranteed by construction. The Australian article is fully correct. Remaining misses are recall failures: the model no longer merges quotes but omits some GB items entirely.

Diagnosis: the prompt asked the model to identify what is "worth amplifying", so it curated instead of inventorying. Extraction (what did GB say?) and prioritisation (what should we amplify?) are different jobs.

## Iteration 3 (architecture v4: exhaustive attribution)

Change: the model must attribute every Q and every S item (speaker or none), with no option to skip. Code filters GB items and warns if any item is missing. Attribution fields come before key messages in the schema, so the model classifies before it summarises. Prioritisation is deferred to the strategist agent.

Results: pending.

| Metric | Baseline | v2 | v3 | v4 |
|---|---|---|---|---|
| Direct quotes | 4/6 | 4/6 | 4/6 | 6/6 |
| Paraphrases | 6/9 | 6/9 | 7/9 | 7/9 |
| Non-verbatim excerpts | 2 | 1 | 0 | 0 |

Result: all direct quotes recovered, including both segments of the interrupted quote. No items were skipped (coverage check passed). Remaining misses are two paraphrases whose attribution is indirect: a pronoun resolved across paragraphs, and a sentence covered by an attribution at the end of the following sentence.

### Golden set refinement

Paraphrase anchors in the return-to-work entry were originally one per paragraph, matching the paragraph-level output of prompt v1. After segmentation moved to sentence level, two anchors were added so that each sentence is evaluated on its own: "Future applications..." (which the model found) and "Adjusters may fail..." (which it did not). The change follows the segmentation granularity, not the model's output, and it lowers the score rather than raising it. Corrected v4 result: paraphrases 8/11.

Failure pattern: the model finds every sentence with an explicit attribution but misses implicit ones — an unattributed sentence continuing a spokesperson's reported speech, a sentence covered by an attribution at the end of the next sentence, and a pronoun whose antecedent is in the previous paragraph.

## Iteration 4 (prompt v5: news-writing attribution conventions)

Change: rule 3 now states three general news-writing conventions: an end-of-paragraph attribution covers the preceding unattributed sentences; an unattributed sentence following a spokesperson's attributed sentence continues their reported speech; a pronoun in an attribution refers to the most recently named person, even across paragraphs. These are general conventions, not rules tailored to the golden set articles.

| Metric | Baseline | v2 | v3 | v4 | v5 |
|---|---|---|---|---|---|
| Direct quotes | 4/6 | 4/6 | 4/6 | 6/6 | 6/6 |
| Paraphrases | 6/9 | 6/9 | 7/9 | 8/11 | 11/11 |
| Non-verbatim excerpts | 2 | 1 | 0 | 0 | 0 |

Result: full recall on the development set, with no false positives (the number of extracted paraphrases equals the number expected in every article). Prompt iteration on the development set stops here; generalisation is tested on a held-out set of unseen articles.

## Known limitation: no held-out set

All three articles were used during prompt iteration, so the 11/11 result is a development-set score, not a measure of generalisation. A cleaner protocol would have reserved one article as a held-out test set before iterating. Two points limit the risk: verbatim fidelity is guaranteed by the architecture regardless of the article, and the attribution rules added in iteration 4 are general news-writing conventions rather than article-specific fixes. Evaluating on unseen coverage is the first step for any production use.