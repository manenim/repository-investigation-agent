"use strict";
const $ = (id) => document.getElementById(id);
let activeId = null,
  activeToken = "",
  sampleReport = null,
  polling = false;
const el = (tag, text, cls) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
};
function error(message) {
  $("error").textContent = message;
  $("error").hidden = false;
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + activeToken,
      ...options.headers,
    },
  });
  if (!response.ok) {
    let data = await response.json().catch(() => ({}));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Check the issue fields and try again.",
    );
  }
  return response.json();
}
function reset() {
  $("error").hidden = true;
  $("empty").hidden = true;
  $("report").hidden = true;
  $("progress").hidden = true;
}
function stageState(stage, progress = {}) {
  document.querySelectorAll("[data-stage]").forEach((n) => {
    n.classList.toggle("done", Boolean(progress[n.dataset.stage]));
    n.classList.toggle("active", stage === n.dataset.stage);
  });
}
function citation(e) {
  const a = el(
    "a",
    `${e.id} · ${e.path}:${e.start_line}–${e.end_line}`,
    "cite",
  );
  a.href = e.permalink;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}
function render(r, isSample = false) {
  reset();
  $("report").hidden = false;
  $("status-badge").textContent = isSample ? "Sample report" : "Review ready";
  const out = $("report");
  out.replaceChildren();
  out.append(
    el(
      "p",
      isSample
        ? "SAVED SAMPLE · " + r.mode.toUpperCase()
        : r.mode.toUpperCase(),
      "eyebrow",
    ),
    el("h2", r.issue.title),
  );
  out.append(
    el(
      "p",
      `${r.repository} / ${r.commit_sha}\n${r.model} · ${r.prompt_version} · Run ${r.run_id}`,
      "metadata",
    ),
  );
  out.append(
    el(
      "div",
      r.insufficient_evidence
        ? "Insufficient evidence for a complete conclusion. Review the observations, flagged claims and open questions below."
        : "Evidence-backed draft. Semantic review is a model judgment, not a guarantee of correctness.",
      "outcome" + (r.insufficient_evidence ? " caution" : ""),
    ),
  );
  const exports = el("div", undefined, "exports");
  for (const format of ["md", "json"]) {
    const button = el(
      "button",
      format === "md" ? "Export Markdown" : "Export JSON",
    );
    button.onclick = async () => {
      try {
        let blob;
        if (isSample) {
          if (format === "md") {
            const res = await fetch("/sample.md");
            if (!res.ok) throw new Error("Sample Markdown unavailable");
            blob = await res.blob();
          } else
            blob = new Blob([JSON.stringify(r, null, 2)], {
              type: "application/json",
            });
        } else {
          const response = await fetch(
            `/investigations/${activeId}/report.${format}`,
            { headers: { Authorization: "Bearer " + activeToken } },
          );
          if (!response.ok) throw new Error("Export failed");
          blob = await response.blob();
        }
        const url = URL.createObjectURL(blob),
          a = el("a");
        a.href = url;
        a.download = `investigation-${r.run_id}.${format}`;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (e) {
        error(e.message);
      }
    };
    exports.append(button);
  }
  out.append(exports);
  for (const [kind, heading] of [
    ["architecture", "Architecture & code paths"],
    ["observation", "Direct observations"],
    ["hypothesis", "Hypotheses to validate"],
  ]) {
    out.append(el("h3", heading));
    let count = 0;
    for (const v of r.claims.filter((v) => v.claim.kind === kind)) {
      count++;
      const box = el(
        "div",
        undefined,
        "claim" +
          (["unsupported", "insufficient_evidence"].includes(v.verdict)
            ? " flagged"
            : ""),
      );
      box.append(
        el(
          "span",
          `${v.verdict.replaceAll("_", " ")} · ${v.claim.confidence} confidence`,
          "verdict",
        ),
        el("p", v.claim.text),
      );
      for (const id of v.claim.evidence_ids) {
        const e = r.evidence.find((e) => e.id === id);
        if (e) box.append(citation(e));
      }
      if (v.supporting_quote) box.append(el("pre", v.supporting_quote));
      box.append(
        el(
          "small",
          `Reference validity: ${v.reference_valid ? "passed" : "failed"}. Support: ${v.reason}`,
        ),
        el("small", "Counter-evidence / limits: " + v.claim.counter_evidence),
      );
      out.append(box);
    }
    if (!count) out.append(el("p", "No claims in this category."));
  }
  out.append(el("h3", "Proposed fix & validation plan"));
  for (const p of r.investigation.proposals) {
    const box = el("div", undefined, "claim");
    box.append(
      el("p", p.action),
      el("small", "Affected files: " + p.affected_files.join(", ")),
      el("p", "Compatibility: " + p.compatibility),
      el("p", "Proposed checks: " + p.validation),
    );
    out.append(box);
  }
  for (const finding of r.proposal_findings || [])
    out.append(el("p", "Plan review: " + finding, "outcome caution"));
  out.append(
    el(
      "p",
      "These checks are proposed. No target repository code or tests were executed.",
    ),
  );
  out.append(el("h3", "Unresolved questions"));
  const questions = el("ul");
  for (const q of r.investigation.unanswered_questions)
    questions.append(el("li", q));
  out.append(questions);
  out.append(el("h3", "Evidence & citation checks"));
  for (const e of r.evidence) {
    const d = el("details"),
      s = el("summary", `${e.id} / ${e.path}:${e.start_line}–${e.end_line}`);
    d.append(s, citation(e), el("pre", e.excerpt));
    out.append(d);
  }
  out.append(el("h3", "Human review checklist"));
  const list = el("ul");
  for (const q of r.human_checklist) list.append(el("li", q));
  out.append(list);
  const details = el("details");
  details.append(
    el("summary", "Run timings, usage & source limits"),
    el(
      "pre",
      JSON.stringify(
        {
          timings: r.timings,
          usage: r.usage,
          source: r.snapshot.source,
          skipped: r.snapshot.skipped,
        },
        null,
        2,
      ),
    ),
  );
  out.append(details);
}
$("input-mode").onchange = () => {
  const paste = $("input-mode").value === "paste";
  $("paste-fields").hidden = !paste;
  $("url-fields").hidden = paste;
};
$("investigation-form").onsubmit = async (event) => {
  event.preventDefault();
  if (polling) return;
  activeToken = $("access-token").value;
  sampleReport = null;
  reset();
  $("submit").disabled = true;
  try {
    const body = { repository: $("repository").value, ref: $("ref").value };
    if ($("input-mode").value === "url") body.issue_url = $("issue-url").value;
    else {
      body.title = $("issue-title").value;
      body.body = $("issue-body").value;
    }
    const run = await api("/investigations", {
      method: "POST",
      body: JSON.stringify(body),
    });
    activeId = run.id;
    history.replaceState(null, "", "?run=" + activeId);
    polling = true;
    $("progress").hidden = false;
    while (polling) {
      const data = await api("/investigations/" + activeId);
      $("status-badge").textContent = data.status;
      stageState(data.stage, data.progress);
      $("progress-text").textContent =
        `Run ${activeId.slice(0, 8)} · ${data.stage}. You can keep this tab open while the worker runs.`;
      if (data.status === "complete") {
        polling = false;
        render(data.report);
        break;
      }
      if (data.status === "failed")
        throw new Error(data.error || "Investigation failed");
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
  } catch (e) {
    polling = false;
    $("progress").hidden = true;
    $("status-badge").textContent = "Needs attention";
    error(e.message);
  } finally {
    $("submit").disabled = false;
  }
};
$("sample").onclick = async () => {
  if (polling) return;
  try {
    const r = await api("/sample");
    sampleReport = r;
    stageState(
      "complete",
      Object.fromEntries(Object.keys(r.timings).map((k) => [k, true])),
    );
    render(r, true);
  } catch (e) {
    error(e.message);
  }
};
api("/config")
  .then((c) => {
    if (c.deployment_notice) {
      const notice = el("p", c.deployment_notice, "outcome caution");
      document.querySelector(".intro").append(notice);
    }
    if (c.public_sample_only) {
      $("submit").disabled = true;
      $("submit").textContent = "Public viewer · generation unavailable";
      $("access-token").disabled = true;
      $("mode-note").textContent =
        "Saved live-model report. Run the included backend for new investigations.";
      $("investigation-form").hidden = true;
      document.querySelector(".panel-heading h2").textContent =
        "Saved investigation";
      const liveLink = el("a", "Open the live app ↗", "cite");
      liveLink.href = "https://repository-investigation-agent.onrender.com";
      document.querySelector(".panel").append(liveLink);
      $("sample").click();
      return;
    }
    $("mode-note").textContent =
      c.provider === "sample"
        ? "Offline extractive sample mode. No model calls."
        : "Live model generation is access-controlled. Public sample reports are free to inspect.";
  })
  .catch(() => {
    $("mode-note").textContent = "Service unavailable. Refresh to retry.";
  });

const savedRun = new URLSearchParams(location.search).get("run");
if (savedRun && /^[a-f0-9]{32}$/.test(savedRun)) {
  const resume = el("button", "Open saved investigation →", "sample-button");
  resume.type = "button";
  $("sample").before(
    resume,
    el("p", "Enter your access token above to reopen this saved run.", "hint"),
  );
  resume.onclick = async () => {
    if (polling) return;
    activeToken = $("access-token").value;
    activeId = savedRun;
    try {
      const data = await api("/investigations/" + savedRun);
      stageState(data.stage, data.progress);
      if (data.status === "complete") render(data.report);
      else
        error(
          data.error || "This run is still processing. Open it again shortly.",
        );
    } catch (e) {
      error(e.message);
    }
  };
}
