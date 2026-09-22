const $ = (id) => document.getElementById(id);
const STAGES = [
  ["ingest", "Ingest", "Article text and metadata extracted from the page."],
  ["analyse", "Analyse", "GB spokespeople, exact quotes and key messages."],
  ["write", "Draft", "Three posts written in GB’s voice."],
  ["review", "Review", "Every claim checked against the article."],
];
const STAGE_NAMES = { ingest: "Ingest", analyse: "Analyse", write: "Draft", review: "Review" };
const CHANNELS = {
  company_page: ["Company page", "GB", "sq"],
  spokesperson: ["Spokesperson draft", "", "teal"],
  employee_advocacy: ["Employee advocacy", "··", "plain"],
};

const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const initials = (name) => name.split(" ").map((w) => w[0]).join("").slice(0, 2).toUpperCase();
const domainOf = (url) => { try { return new URL(url).hostname.replace("www.", ""); } catch { return url; } };
const thousands = (n) => n.toLocaleString("en-US");

function show(view) {
  ["home", "running", "detail"].forEach((name) => $("view-" + name).classList.toggle("hidden", name !== view));
  window.scrollTo(0, 0);
}

function highlight(text, marks) {
  const spans = [];
  marks.forEach(({ needle, cls }) => {
    if (!needle) return;
    const at = text.indexOf(needle);
    if (at >= 0) spans.push({ start: at, end: at + needle.length, cls });
  });
  spans.sort((a, b) => a.start - b.start);
  let out = "";
  let cursor = 0;
  spans.forEach((span) => {
    if (span.start < cursor) return;
    out += escapeHtml(text.slice(cursor, span.start));
    out += `<mark class="${span.cls}">${escapeHtml(text.slice(span.start, span.end))}</mark>`;
    cursor = span.end;
  });
  return out + escapeHtml(text.slice(cursor));
}

function articleHtml(result) {
  const marks = result.analysis.gb_statements.map((s) => ({
    needle: s.text,
    cls: s.type === "direct_quote" ? "quote" : "para",
  }));
  result.analysis.other_organizations
    .filter((o) => o.relation === "competitor")
    .forEach((o) => marks.push({ needle: o.name, cls: "comp" }));
  return result.article.text
    .split("\n")
    .filter((p) => p.trim())
    .map((p) => `<p>${highlight(p, marks)}</p>`)
    .join("");
}

function renderCards(results) {
  $("result-count").textContent = `${results.length} kits`;
  $("result-cards").innerHTML = results
    .map((r) => {
      const ok = r.cleared === r.total;
      const status = ok ? `${r.total} posts cleared` : `${r.total - r.cleared} of ${r.total} need changes`;
      const colour = ok ? "var(--green)" : "var(--red)";
      const cost = r.cost_usd !== undefined ? `$${r.cost_usd.toFixed(3)} · ${r.seconds} s` : "";
      return `<button class="card" data-slug="${r.slug}">
        <span class="meta">${escapeHtml(r.outlet || "")} · ${r.published_date || ""} · ${r.region}</span>
        <h3 class="serif">${escapeHtml(r.title || r.slug)}</h3>
        <span class="row">
          <span class="pill ${r.coverage_type === "announcement" ? "gold" : "teal"}">${r.coverage_type.replace("_", " ")}</span>
          <span class="row" style="color:${colour};font-size:13px;font-weight:500;gap:6px"><span class="dot" style="background:${colour}"></span>${status}</span>
        </span>
        <span class="meta">${cost}</span>
      </button>`;
    })
    .join("");
  document.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", () => openResult(card.dataset.slug));
  });
}

function renderSteps(stages) {
  $("step-list").innerHTML = STAGES.map(([key, name, blurb]) => {
    const stage = stages[key];
    const cost = stage.cost_usd ? ` · $${stage.cost_usd.toFixed(4)}` : "";
    const time = stage.seconds !== null ? `${stage.seconds} s${cost}` : stage.state === "running" ? "running" : "waiting";
    return `<div class="step ${stage.state}">
      <span class="bullet"></span>
      <span class="grow"><span class="name">${name}</span><br><span class="detail">${escapeHtml(stage.detail || blurb)}</span></span>
      <span class="mono detail">${time}</span>
    </div>`;
  }).join("");
}

function costPanel(result) {
  const stages = Object.entries(result.metrics);
  const seconds = stages.reduce((a, [, s]) => a + s.seconds, 0).toFixed(1);
  const cost = stages.reduce((a, [, s]) => a + s.cost_usd, 0);
  const tokens = stages.reduce((a, [, s]) => a + s.input_tokens + s.output_tokens, 0);
  const rows = stages
    .map(
      ([key, s]) => `<tr>
        <td>${STAGE_NAMES[key] || key}</td>
        <td class="mono">${s.seconds.toFixed(1)} s</td>
        <td class="mono">${thousands(s.input_tokens + s.output_tokens)}</td>
        <td class="mono">${s.calls}</td>
        <td class="mono">$${s.cost_usd.toFixed(4)}</td>
      </tr>`
    )
    .join("");
  return `<div class="panel">
    <h3>Time and cost</h3>
    <table class="metrics">
      <thead><tr><th>Stage</th><th>Time</th><th>Tokens</th><th>Calls</th><th>Cost</th></tr></thead>
      <tbody>${rows}</tbody>
      <tfoot><tr><td>Total</td><td class="mono">${seconds} s</td><td class="mono">${thousands(tokens)}</td><td></td><td class="mono">$${cost.toFixed(4)}</td></tr></tfoot>
    </table>
    <p class="notice">OpenAI API cost at list prices for gpt-4o, checked 22 September 2026. Review costs more than drafting because each post is fact-checked against the full article.</p>
  </div>`;
}

function analysisPane(result) {
  const a = result.analysis;
  const quotes = a.gb_statements.filter((s) => s.type === "direct_quote").length;
  const competitors = a.other_organizations.filter((o) => o.relation === "competitor");
  const people = a.gb_spokespeople
    .map(
      (s) => `<div class="row" style="gap:14px;margin-bottom:12px">
        <span class="avatar">${initials(s.name)}</span>
        <span><strong>${escapeHtml(s.name)}</strong><br><span class="detail" style="color:var(--body)">${escapeHtml(s.title)}${s.location ? " · " + escapeHtml(s.location) : ""}</span></span>
      </div>`
    )
    .join("");
  return `<div class="split">
    <div class="panel">
      <div class="legend">
        <span><mark class="quote">&nbsp;&nbsp;&nbsp;</mark> GB direct quote</span>
        <span><mark class="para">&nbsp;&nbsp;&nbsp;</mark> GB paraphrase</span>
        <span><mark class="comp">&nbsp;&nbsp;&nbsp;</mark> Other organisation, not amplified</span>
      </div>
      <div class="article">${articleHtml(result)}</div>
    </div>
    <div>
      <div class="panel">
        <h3>Coverage type</h3>
        <span class="pill ${a.coverage_type === "announcement" ? "gold" : "teal"}">${a.coverage_type.replace("_", " ")}</span>
        <p style="color:var(--body);margin:12px 0 0">${escapeHtml(a.coverage_rationale)}</p>
      </div>
      <div class="panel">
        <h3>GB spokespeople</h3>
        ${people}
        <div class="stats">
          <div><span class="n">${quotes}</span><span class="l">direct quotes</span></div>
          <div><span class="n">${a.gb_statements.length - quotes}</span><span class="l">paraphrases</span></div>
          <div><span class="n">0</span><span class="l">altered words</span></div>
        </div>
        <p class="notice">Titles come from the article. Verify against the internal title before publishing.</p>
      </div>
      <div class="panel">
        <h3>Key messages</h3>
        <ol class="messages">${a.key_messages.map((m) => `<li>${escapeHtml(m.message)}</li>`).join("")}</ol>
        <div class="row" style="margin-top:12px">${a.themes.map((t) => `<span class="pill teal">${escapeHtml(t)}</span>`).join("")}</div>
      </div>
      <div class="panel">
        <h3>Excluded from the posts</h3>
        <div class="row">${competitors.map((o) => `<span class="pill grey">${escapeHtml(o.name)}</span>`).join("") || "<span class='detail'>No competitors in this article.</span>"}</div>
      </div>
      ${costPanel(result)}
    </div>
  </div>`;
}

function postCard(post, review, result) {
  const [label, mono, variant] = CHANNELS[post.channel] || [post.channel, "GB", ""];
  const person = result.analysis.gb_spokespeople[0];
  const name = post.channel === "spokesperson" && person ? person.name : post.channel === "company_page" ? "Gallagher Bassett" : "Any GB employee";
  const avatar = post.channel === "spokesperson" && person ? initials(person.name) : mono;
  const blockers = review.issues.filter((i) => i.severity === "blocker");
  const badge = review.approved
    ? '<span class="pill green">Cleared by reviewer</span>'
    : `<span class="pill red">Needs changes · ${blockers.length} blocker${blockers.length === 1 ? "" : "s"}</span>`;
  const body = post.text.replace(result.article.url, "").trim();
  const marks = review.issues.map((i) => ({ needle: i.phrase, cls: i.severity === "blocker" ? "flag" : "warn" }));
  const issues = review.issues
    .map(
      (i) => `<div class="issue"><span class="q">${i.severity === "blocker" ? "⛔" : "⚠"} ${escapeHtml(i.phrase)}</span><br><span class="why">${escapeHtml(i.explanation)}</span></div>`
    )
    .join("");
  return `<div class="post">
    <div class="post-head"><span class="ch">${label}</span>${badge}</div>
    <div class="post-body">
      <div class="row" style="gap:12px"><span class="avatar ${variant}">${avatar}</span><span><strong>${escapeHtml(name)}</strong><br><span class="meta">${post.channel === "spokesperson" ? "Personal profile · first person" : "LinkedIn"}</span></span></div>
      <p class="post-text">${highlight(body, marks)}</p>
      <div class="preview"><div class="dom">${domainOf(result.article.url)}</div><div class="ti">${escapeHtml(result.article.title || "")}</div></div>
      ${issues}
    </div>
    <div class="actions">
      <button type="button" data-copy="${encodeURIComponent(post.text)}">Copy text</button>
      <button type="button" class="primary" ${review.approved ? "" : "disabled"}>Approve</button>
    </div>
  </div>`;
}

function postsPane(result) {
  const reviews = Object.fromEntries(result.review.posts.map((p) => [p.channel, p]));
  const cleared = result.review.posts.filter((p) => p.approved).length;
  const stages = Object.values(result.metrics);
  const seconds = stages.reduce((a, s) => a + s.seconds, 0).toFixed(1);
  const cost = stages.reduce((a, s) => a + s.cost_usd, 0);
  return `<div class="angle">
      <span><span class="label">Primary angle</span><br><span class="value">${escapeHtml(result.kit.primary_angle)}</span></span>
      <span class="row" style="gap:28px">
        <span class="stat"><span>Reviewer</span><strong>${cleared} of ${result.kit.posts.length} cleared</strong></span>
        <span class="stat"><span>Human sign-off</span><strong>0 of ${result.kit.posts.length}</strong></span>
        <span class="stat"><span>Run time</span><strong class="mono">${seconds} s</strong></span>
        <span class="stat"><span>API cost</span><strong class="mono">$${cost.toFixed(3)}</strong></span>
      </span>
    </div>
    <div class="posts">${result.kit.posts.map((p) => postCard(p, reviews[p.channel], result)).join("")}</div>`;
}

function renderDetail(result) {
  $("detail-meta").textContent = `${result.article.outlet} · ${result.article.published_date} · ${result.article.region}`;
  $("detail-title").textContent = result.article.title || result.slug;
  $("pane-analysis").innerHTML = analysisPane(result);
  $("pane-posts").innerHTML = postsPane(result);
  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", () => {
      navigator.clipboard.writeText(decodeURIComponent(button.dataset.copy));
      button.textContent = "Copied";
      setTimeout(() => (button.textContent = "Copy text"), 1500);
    });
  });
  selectTab("analysis");
  show("detail");
}

function selectTab(which) {
  $("tab-analysis").classList.toggle("active", which === "analysis");
  $("tab-posts").classList.toggle("active", which === "posts");
  $("pane-analysis").classList.toggle("hidden", which !== "analysis");
  $("pane-posts").classList.toggle("hidden", which !== "posts");
}

async function openResult(slug) {
  const response = await fetch(`/api/results/${slug}`);
  if (response.ok) renderDetail(await response.json());
}

async function loadResults() {
  const response = await fetch("/api/results");
  if (response.ok) renderCards(await response.json());
}

function poll(jobId) {
  const timer = setInterval(async () => {
    const job = await (await fetch(`/api/jobs/${jobId}`)).json();
    renderSteps(job.stages);
    if (job.status === "done") {
      clearInterval(timer);
      renderDetail(job.result);
      loadResults();
      $("run-btn").disabled = false;
    } else if (job.status === "error") {
      clearInterval(timer);
      $("run-error").textContent = job.error;
      $("run-error").classList.remove("hidden");
      $("run-btn").disabled = false;
    }
  }, 1200);
}

$("run-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = $("url").value.trim();
  $("home-error").classList.add("hidden");
  $("run-error").classList.add("hidden");
  $("run-btn").disabled = true;
  const response = await fetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!response.ok) {
    const error = await response.json();
    $("home-error").textContent = error.detail || "Something went wrong.";
    $("home-error").classList.remove("hidden");
    $("run-btn").disabled = false;
    return;
  }
  const { job_id: jobId } = await response.json();
  $("running-url").textContent = url;
  renderSteps(Object.fromEntries(STAGES.map(([key]) => [key, { state: "pending", seconds: null, detail: null, cost_usd: 0 }])));
  show("running");
  poll(jobId);
});

$("home-btn").addEventListener("click", () => show("home"));
$("tab-analysis").addEventListener("click", () => selectTab("analysis"));
$("tab-posts").addEventListener("click", () => selectTab("posts"));
loadResults();