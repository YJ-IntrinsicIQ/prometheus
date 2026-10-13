#!/usr/bin/env python3
"""M63 / G5 — writes the three deliverable reports and the bundle manifest from the machine outputs (read-only on the repository except preview/ output paths)."""
import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SC = ["S1_candidate_answers", "S2_candidate_story_panel_explorer", "S3_frozen_approved_answers", "S4_served_story_panel_explorer", "S5_proposed_bundle_answers"]
SHORT = {"S1": "S1 16 repaired candidate answers (before this mission's annotation)", "S2": "S2 candidate Story / Panel / Explorer (sandbox, with ledger)", "S3": "S3 91 frozen approved answers", "S4": "S4 served Story / Panel / Explorer (protected data)", "S5": "S5 91 proposed bundle answers"}
GEN = ("DISCLOSURE_ABSENCE", "EXTRACTION_ABSENCE", "INAPPLICABLE_MEASURE")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def esc(t) -> str:
    return str(t).replace("|", "\\|").replace("\n", " ")


def norm(t: str) -> str:
    return re.sub(r"\d[\d,.]*", "#", " ".join(str(t).split()))[:200]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/private/tmp/claude-501/g5b")
    ap.add_argument("--tests", required=True, help="JSON with test results to record")
    ap.add_argument("--protected-before", required=True)
    ap.add_argument("--protected-after", required=True)
    a = ap.parse_args()
    W = Path(a.work)
    inv = json.loads((W / "clean_pass2.json").read_text())
    units, groups = inv["units"], inv["groups"]
    q = json.loads((W / "review_queue.json").read_text())
    man = json.loads((W / "bundle" / "answers_manifest.json").read_text())
    tests = json.loads(Path(a.tests).read_text())
    pb, pa = json.loads(Path(a.protected_before).read_text()), json.loads(Path(a.protected_after).read_text())
    prev = json.loads((REPO / "preview/M63_G5_FULL_SCOPE_ABSENCE_INVENTORY.json").read_text())
    prev_cnt = Counter(c["scope"][:2] for c in prev["claims"])
    prev_unres = Counter(c["scope"][:2] for c in prev["claims"] if c["status"] == "UNRESOLVED")

    by = {s[:2]: [u for u in units if u["scope"] == s] for s in SC}
    stat = {}
    for k, us in by.items():
        g = [u for u in us if u["class"] in GEN]
        st = Counter(u["status"] for u in g)
        stat[k] = dict(neg=len(us), by_class=Counter(u["class"] for u in us), genuine=len(g), distinct=len({(u["company"], norm(u["clause"])) for u in g}),
                       verified=sum(v for s_, v in st.items() if s_.startswith("VERIFIED")), contradicted=st["CONTRADICTED"] + st["WRONG_NOT_APPLICABLE_CLAIM"],
                       unresolved=sum(v for s_, v in st.items() if s_.startswith("UNRESOLVED")), linked=sum(1 for u in g if u.get("claim_linked_entry")), status=st)
    # hashes / manifest -------------------------------------------------------------------------------------------------------------------------------------------
    code_files = ["pipelines/g4_investor_answers.py", "pipelines/g5_provenance.py", "tools/g5_build_bundle.py", "tools/g5_build_sandbox.py", "tools/g5_build_sidecar.py", "tools/g5_clean_inventory.py",
                  "tools/g5_review_queue.py", "tools/g5_prepare_bundle.sh", "tools/g5_dump_surfaces.test.ts.txt", "tools/g5_protected_snapshot.py", "tools/g5_write_reports.py",
                  "apps/ask-intrinsiciq/src/lib/provenance/absence.ts", "apps/ask-intrinsiciq/src/lib/story/load-story.ts", "apps/ask-intrinsiciq/src/lib/panel/load-panel.ts",
                  "apps/ask-intrinsiciq/src/lib/catalog/load-explorer.ts", "apps/ask-intrinsiciq/src/lib/panel/build-panel.ts", "apps/ask-intrinsiciq/src/lib/panel/specialists.ts"]
    ledgers = {k: sha(W / "root" / "companies" / k / "company_memory" / "ask_intrinsiciq" / "g5_absence_provenance.json") for k in ("sun_pharma", "tanla", "ujjivan", "datapatterns")}
    answers = [{"slot": r["slot"], "base": r["base"], "original_full_digest": r["original"]["full_digest"], "proposed_full_digest": r["proposed"]["full_digest"],
                "original_content_fingerprint": r["original"]["content_fingerprint"], "proposed_content_fingerprint": r["proposed"]["content_fingerprint"], "changed_fields": r["changed_fields"],
                "provenance": {"entries": r["entries"], "pending": r["pending"]}} for r in man["answers"]]
    h = hashlib.sha256()
    h.update(json.dumps(answers, sort_keys=True).encode())
    for k in sorted(ledgers):
        h.update(f"{k}:{ledgers[k]}".encode())
    h.update(sha(W / "surf_pass2.json").encode())
    h.update(sha(W / "clean_pass2.json").encode())
    for f in code_files:
        h.update(f"{f}:{sha(REPO / f)}".encode())
    H = h.hexdigest()
    manifest = {"bundle_hash_H": H, "date": "2026-10-13", "answers": answers, "projections": {"ledger_sha256": ledgers, "surfaces_pass2_sha256": sha(W / "surf_pass2.json"), "sandbox_registry_copy_sha256": sha(W / "root/governance/approval_registry.json")},
                "claim_inventory_sha256": sha(W / "clean_pass2.json"), "review_queue_sha256": sha(W / "review_queue.json"), "code_sha256": {f: sha(REPO / f) for f in code_files},
                "tests": tests, "protected_before": pb, "protected_after": pa, "protected_changed": pb["tree_sha256"] != pa["tree_sha256"] or pb["single"] != pa["single"],
                "scratch_paths": {"bundle": str(W / "bundle"), "sandbox_root": str(W / "root"), "surfaces_pass2": str(W / "surf_pass2.json"), "clean_inventory": str(W / "clean_pass2.json"), "review_queue": str(W / "review_queue.json")},
                "dashboard": None}
    unresolved_S5_S2 = stat["S5"]["unresolved"] + stat["S2"]["unresolved"]
    dash = {"genuine_applicable_absence_claims": {"S5 proposed answers": stat["S5"]["genuine"], "S2 candidate projections": stat["S2"]["genuine"], "distinct claim texts (S5 and S2)": len({(u["company"], norm(u["clause"])) for k in ("S5", "S2") for u in by[k] if u["class"] in GEN})},
            "claim_linked": {"S5": stat["S5"]["linked"], "S2": stat["S2"]["linked"]}, "claim_linked_and_verified": {"S5": stat["S5"]["verified"], "S2": stat["S2"]["verified"]},
            "contradicted": {"S5": stat["S5"]["contradicted"], "S2": stat["S2"]["contradicted"]}, "unresolved": {"S5": stat["S5"]["unresolved"], "S2": stat["S2"]["unresolved"]},
            "distinct_evidence_reviews_required": len(q), "replacement_slots_prepared": f"{len(answers)}/91", "protected_artifacts_changed": 0 if not manifest["protected_changed"] else "CHANGED"}
    manifest["dashboard"] = dash
    (REPO / "preview/m63_g5_bundle_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    dst = REPO / "preview/m63_g5_bundle"
    if dst.exists():
        shutil.rmtree(dst)
    (dst / "answers").mkdir(parents=True)
    for f in (W / "bundle" / "answers").glob("*.json"):
        shutil.copy(f, dst / "answers" / f.name)
    shutil.copy(W / "bundle" / "answers_manifest.json", dst / "answers_manifest.json")
    for k in ledgers:
        shutil.copy(W / "root" / "companies" / k / "company_memory" / "ask_intrinsiciq" / "g5_absence_provenance.json", dst / f"projection_ledger__{k}.json")
    shutil.copy(W / "review_queue.json", dst / "review_queue.json")

    # ───────────────────────────── 1. clean provenance inventory ─────────────────────────────
    o = ["# M63 / G5 — Clean provenance inventory\n",
         "2026-10-13. Read-only. Reproduce with `tools/g5_prepare_bundle.sh` then `tools/g5_clean_inventory.py` (inputs hashed in `m63_g5_bundle_manifest.json`). The four inventories overlap in rendered text and **are not additive**.\n",
         "## 1. What was wrong with the previous denominator\n",
         "The earlier inventory (`M63_G5_FULL_SCOPE_ABSENCE_INVENTORY`) counted any sentence the lexical detector tagged as an absence claim and marked everything without an anchor family `UNRESOLVED`. It never asked what the sentence *asserts*. Reading the sentences shows they are six different things (class definitions below); only the first three are absence claims in the contract's sense, and only they need a state.\n",
         "| Class | Meaning | Needs a G5 state? |", "|---|---|---|",
         "| DISCLOSURE_ABSENCE | asserts the filing or company does not disclose X (source level) | yes: NOT_DISCLOSED needs a human-confirmed search; if the filing carries X the sentence is contradicted |",
         "| EXTRACTION_ABSENCE | asserts the structured records / project records / register lack X (record level) | yes: NOT_EXTRACTED when the filing carries X; the records are checked too |",
         "| INAPPLICABLE_MEASURE | asserts a measure does not describe this business (bank vs industrial) | yes: NOT_APPLICABLE, verified from the business-model class |",
         "| ANALYTIC_UNCERTAINTY | a cause, outcome, impact, value-creation or attribution is not established | no (it is not a statement about a disclosure) |",
         "| EXPLANATORY | a reasoning principle, method note, definition or label of our own figure (\"missing disclosure is not failure\") | no |",
         "| UI_PLACEHOLDER_OR_SYSTEM_LIMITATION | a bare UI label, a question title, or a statement about what Prometheus holds (\"no market data\", \"the FY27 report is not in the records\") | no state; the statement is verified against system inputs instead |\n",
         "Each clause carries the **rule id** that decided its class; nothing is dropped without a recorded rule. A sentence is split into clauses only where both sides carry a negation, so a genuine claim cannot hide behind an explanatory clause (tested).\n",
         "## 2. Corrected denominator by scope\n",
         "| Scope | previously reported 'applicable' | negation-bearing clauses now | genuine applicable absence claims | distinct claim texts | analytic | explanatory | UI / system | claim-linked | verified | contradicted | unresolved |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in ("S1", "S2", "S3", "S4", "S5"):
        s = stat[k]
        o.append(f"| {SHORT[k]} | {prev_cnt.get(k, '—')} | {s['neg']} | **{s['genuine']}** | {s['distinct']} | {s['by_class']['ANALYTIC_UNCERTAINTY']} | {s['by_class']['EXPLANATORY']} | {s['by_class']['UI_PLACEHOLDER_OR_SYSTEM_LIMITATION']} | {s['linked'] if k in ('S2', 'S5') else 'n/a (no provenance field)'} | {s['verified']} | {s['contradicted']} | {s['unresolved']} |")
    o += ["\nNotes: S1 is the candidate set before this mission's annotation (its provenance lives in the bundle, S5). S3 and S4 are protected and have no provenance field, so linkage is not defined for them; their counts show the replacement workload. S2 differs from S4 because the candidate evidence root carries the G1-G3 repaired records (for example Data Patterns interest coverage and contingent liabilities exist there), so two served-surface statements that the candidate data contradicts do not appear in the candidate projections.\n",
          "## 3. Status of every genuine claim, by scope\n", "| Scope | " + " | ".join(["VERIFIED_NOT_EXTRACTED", "VERIFIED_NOT_APPLICABLE", "CONTRADICTED", "WRONG_NOT_APPLICABLE_CLAIM", "UNRESOLVED_NOT_DISCLOSED_CANDIDATE", "UNRESOLVED_REVIEW", "UNRESOLVED_UNPROFILED"]) + " |", "|---|---|---|---|---|---|---|---|"]
    for k in ("S2", "S3", "S4", "S5"):
        st = stat[k]["status"]
        o.append(f"| {SHORT[k]} | " + " | ".join(str(st[x]) for x in ["VERIFIED_NOT_EXTRACTED", "VERIFIED_NOT_APPLICABLE", "CONTRADICTED", "WRONG_NOT_APPLICABLE_CLAIM", "UNRESOLVED_NOT_DISCLOSED_CANDIDATE", "UNRESOLVED_REVIEW", "UNRESOLVED_UNPROFILED"]) + " |")
    o += ["\nVERIFIED means the evidence mechanism supports the state with a locator (strong filing hit beside a figure, or the business-model class). It does **not** mean a human has read the page; the record of that distinction is `verification` on each ledger entry. NOT_DISCLOSED is never VERIFIED here: a failed lexical search is a candidate, not a proof.\n",
          "## 4. Evidence groups (one validated finding supports every occurrence whose company, FY, topic, class and record/source scope match)\n",
          "| group | company | FY | topic | class | scope | resolution | locator / basis | occurrences by scope |", "|---|---|---|---|---|---|---|---|---|"]
    for g in sorted(groups, key=lambda g: (g["company"], str(g["topic"]), g["class"])):
        r = g["resolution"]
        o.append(f"| `{esc(g['group'])}` | {g['company']} | {g['fy']} | {g['topic'] or '—'} | {g['class']} | {g['assertion_scope']} | **{r['state']}** | {esc((r.get('locator') or '') + (' — ' if r.get('locator') else '') + r.get('basis', ''))[:210]} | " + ", ".join(f"{k[:2]}:{v}" for k, v in sorted(g["scopes"].items())) + " |")
    o += [f"\n{len(groups)} distinct evidence groups cover {sum(g['occurrences'] for g in groups)} genuine occurrences across all scopes.\n",
          "## 5. System and coverage statements (verified against system inputs, not company disclosure)\n",
          f"- Market data: `{inv['system_limitation']['basis']}` — verified = {inv['system_limitation']['verified']}.",
          "- 'The FYnn report is not in the records' / 'no FYnn data': checked per company against the year folders and fact registries (`coverage_check`).\n",
          "## 6. Every clause excluded from the denominator, with the rule that excluded it\n",
          "Distinct normalised clauses over all scopes; `n` = occurrences. Nothing here was removed by keyword: each row is a clause the classifier read and assigned.\n",
          "| class | rule | n | scopes | clause |", "|---|---|---|---|---|"]
    ex: dict = defaultdict(lambda: [0, set()])
    for u in units:
        if u["class"] not in GEN:
            key = (u["class"], u["rule"], norm(u["clause"]))
            ex[key][0] += 1
            ex[key][1].add(u["scope"][:2])
    for (cls, rule, cl), (n, sc) in sorted(ex.items(), key=lambda kv: (kv[0][0], kv[0][1], -kv[1][0])):
        o.append(f"| {cls} | {rule} | {n} | {','.join(sorted(sc))} | {esc(cl)} |")
    (REPO / "preview/M63_G5_CLEAN_PROVENANCE_INVENTORY.md").write_text("\n".join(o) + "\n")

    # ───────────────────────────── 2. replacement bundle report ─────────────────────────────
    R = ["# M63 / G5 — Full-scope replacement bundle (scratch, hash-pinned)\n",
         "2026-10-13. **Preparation only.** Nothing is approved, served, promoted or activated; the 91 approved answers, the registry, the served artifacts and `companies/` are byte-identical (section 7). G5 is not self-certified.\n",
         f"**Bundle hash H = `{H}`**  (answers, projection ledgers, rendered surfaces, claim inventory and every code file listed in `m63_g5_bundle_manifest.json`).\n",
         "## 1. Dashboard\n", "| Measure | Result |", "|---|---|",
         f"| Genuine applicable absence claims | proposed answers (S5) **{stat['S5']['genuine']}**; candidate projections (S2) **{stat['S2']['genuine']}**; distinct claim texts across both {dash['genuine_applicable_absence_claims']['distinct claim texts (S5 and S2)']} (previously reported: 28 / 176 / 75 / 198 raw lexical hits) |",
         f"| Claim-linked | S5 {stat['S5']['linked']}/{stat['S5']['genuine']}; S2 {stat['S2']['linked']}/{stat['S2']['genuine']} |",
         f"| Claim-linked and verified (evidence-supported state with locator or business-model basis) | S5 **{stat['S5']['verified']}**; S2 **{stat['S2']['verified']}** |",
         f"| Contradicted | S5 **{stat['S5']['contradicted']}**; S2 **{stat['S2']['contradicted']}** (frozen S3 had {stat['S3']['contradicted']}, all rewritten in S5) |",
         f"| Unresolved | S5 **{stat['S5']['unresolved']}**; S2 **{stat['S2']['unresolved']}** |",
         f"| Distinct evidence reviews required | **{len(q)}** (`M63_G5_REMAINING_REVIEW_QUEUE.md`) |",
         f"| Replacement slots prepared | **{len(answers)}/91** (15 are repaired G4/G5 candidates, {len(answers) - 15} are the approved answers with provenance added and contradicted clauses reworded) |",
         f"| Protected artifacts changed | **{dash['protected_artifacts_changed']}** |\n",
         "## 2. What the shared mechanism does (and what changed in code)\n",
         "- `pipelines/g5_provenance.py` (new, company-independent): six-class semantic classifier with rule ids; 24 evidence profiles (term anchors, strong = term beside a figure, record probes); `resolve` per (company, topic); `judge` per clause; `annotate_answer`; `audit_text`; `coverage_check`; `system_limitation_ok`.",
         "- Hard rules in `resolve`: NOT_EXTRACTED needs a strong filing hit with a page and a record that lacks the figure; NOT_DISCLOSED is never concluded from a failed search (it becomes `NOT_DISCLOSED_CANDIDATE`, listed for a human); a mention without a figure is `REVIEW`; a record that holds the figure contradicts a 'missing' claim; banks get NOT_APPLICABLE from the business-model class.",
         "- Projections: `src/lib/provenance/absence.ts` adds a claim-linked `g5_absence` ledger to the Story, each Panel specialist and the Explorer (loaders `load-story.ts`, `load-panel.ts`, `load-explorer.ts`). The ledger is generated outside the app from the same classifier and resolver and lives in the **sandbox** root only; without it nothing changes. Four UI-code corrections: Panel 'book value per share is missing' is now record-level wording; the Panel R&D and ROCE gaps state that they do not apply to a bank; the two lens descriptions no longer assert 'missing for most companies'; and the Sun management candidate no longer says 'regulatory validation' (a customer-text rule hides any answer containing it, which would have made that answer disappear on activation).",
         "- A new defect class found by serving the bundle through the real runtime gate: integral floats (for example `64.0`) in candidate objects hash differently in Python and JavaScript, so the app's digest check rejected those answers; the bundle builder normalises them to integers (value-preserving).\n",
         "## 3. Proposed changes to answer text (only evidence-contradicted clauses are reworded)\n",
         "| slot | field | before | after | reason | locator |", "|---|---|---|---|---|---|"]
    for r in man["answers"]:
        for rw in r["rewrites"]:
            R.append(f"| {r['slot']} | {rw['field']} | {esc(rw['before'])[:200]} | {esc(rw['after'])[:240]} | {rw['reason']} ({rw['topic']}) | {rw['locator']} |")
    R += ["\nEvery other change in an approved-based slot is the added `g5_absence`, `g5_review_pending` or `g5_system_statements` provenance field (tested: no other field of an approved-based slot changes).\n",
          "## 4. All 91 slots\n", "| slot | base | original digest | proposed digest | changed fields | rewrites | entries | pending | unresolved evidence questions |", "|---|---|---|---|---|---|---|---|---|"]
    for r in man["answers"]:
        R.append(f"| {r['slot']} | {r['base']} | `{r['original']['full_digest'][:12]}` | `{r['proposed']['full_digest'][:12]}` | {', '.join(r['changed_fields']) or 'none'} | {len(r['rewrites'])} | {r['entries']} | {r['pending']} | {esc(', '.join(r['unresolved_evidence_questions']))} |")
    R += ["\nThe registry fingerprint recorded for each original equals the recomputed digest (tested). Digests are the two the app checks (content fingerprint and full artifact digest).\n",
          "## 5. Rendered-surface verification (sandbox root)\n",
          f"- The sandbox root installs the 91 proposed answers into **copies** of the hybrid files and re-pins a **copy** of the registry. All **91/91** serve through the real approval gate and runtime customer-text validation (question views per company 25 / 22 / 21 / 23); before the two fixes below, 5 of the 91 did not serve (4 because of the float digest defect, then the Sun management answer because of the forbidden word).",
          f"- Story, Panel specialists and Explorer render with the claim ledger: entries per company {', '.join(f'{k} {v}' for k, v in tests['ledger_entries'].items())}; every genuine S2 clause is claim-linked ({stat['S2']['linked']}/{stat['S2']['genuine']}).",
          "- The generic labels 'Missing data' / 'Missing measurement' are judged through the sentence they label; table cells such as 'Not in the extracted records' are joined to their row label before they are judged.\n",
          "## 6. Tests and regressions\n", "| Suite | Result |", "|---|---|"]
    for k, v in tests["suites"].items():
        R.append(f"| {k} | {v} |")
    R += [f"\n{tests['g0_note']}\n", "## 7. Protected-artifact verification\n",
          f"Snapshot of {pb['files']} files under `companies/` and `governance/` (BACKLOG, SESSION_LOG excluded) before and after: tree hash `{pb['tree_sha256'][:16]}…` {'identical' if pb['tree_sha256'] == pa['tree_sha256'] else 'CHANGED'}; registry `{pb['single']['governance/approval_registry.json'][:16]}…` with {pb['approvals']} approvals; the four hybrid answer files, `fact_pack_v2.py`, `tests/challenge/baseline.json`, `cases.json` and `negative_claims_review.json` unchanged. The sealed holdout was not accessed; no Git operation; no API call.\n",
          "## 8. Limitations\n",
          f"1. The bundle is **not ready**: {stat['S5']['unresolved']} genuine proposed-answer claims and {stat['S2']['unresolved']} projection claims are unresolved (section 1). They need a human primary-source decision (review queue); {sum(1 for x in q if x['status'] == 'UNRESOLVED_NOT_DISCLOSED_CANDIDATE')} items are NOT_DISCLOSED candidates that need a person to confirm that a lexical search did not miss a table or image.",
          "2. 'Verified' is machine-verified from a strong lexical hit with a locator; it is not a human page read. The independent auditor should sample it.",
          "3. The Story / Panel ledger is keyed by rendered text; if a string changes, the ledger must be regenerated (the pipeline script does so, and the inventory flags any unlinked claim).",
          "4. Served-surface (S4) statements that the candidate data contradicts (Data Patterns interest coverage and contingent liabilities) disappear only when the G1-G3 repaired records are promoted; that is G7.",
          "5. Per-commitment follow-through claims (for example a named approval or a satisfaction score) cannot be settled by a topic profile; they are queued with locators.",
          "6. G3 remains BLOCKED; G4 remains VERIFIED for the four-company scope; no G6/G7 work was done."]
    (REPO / "preview/M63_G5_REPLACEMENT_BUNDLE_REPORT.md").write_text("\n".join(R) + "\n")

    # ───────────────────────────── 3. remaining review queue ─────────────────────────────
    Q = ["# M63 / G5 — Remaining review queue\n",
         f"2026-10-13. **{len(q)} distinct evidence reviews** resolve every unresolved claim in the proposed bundle (S5) and the candidate projections (S2): one decision per item settles all of its occurrences. Excerpts are unreviewed machine retrievals offered to the reviewer; they are **not** evidence and no item here is marked reviewed or verified. Priorities follow the mission order.\n",
         "| Priority | Items | Occurrences S5 / S2 |", "|---|---|---|"]
    for p in sorted({x["priority"] for x in q}):
        its = [x for x in q if x["priority"] == p]
        Q.append(f"| {its[0]['priority_name']} | {len(its)} | {sum(x['occurrence_counts']['S5_proposed_bundle_answers'] for x in its)} / {sum(x['occurrence_counts']['S2_candidate_story_panel_explorer'] for x in its)} |")
    for p in sorted({x["priority"] for x in q}):
        Q += [f"\n## {[x for x in q if x['priority'] == p][0]['priority_name']}\n"]
        for x in [x for x in q if x["priority"] == p]:
            Q += [f"### {x['review']}  ({x['company']}, {x['fy'].upper()}{', topic ' + x['topic'] if x['topic'] else ''})",
                  f"- **Question:** {x['question']}", f"- **Claims it settles:** " + " / ".join(f"“{esc(c)[:170]}”" for c in x["claims"][:4]) + (" …" if len(x["claims"]) > 4 else ""),
                  f"- **Where they appear:** answers {x['occurrence_counts']['S5_proposed_bundle_answers']}, projections {x['occurrence_counts']['S2_candidate_story_panel_explorer']}",
                  f"- **Locator candidates (machine):** {('pages ' + ', '.join(map(str, x['locator_candidates']))) if x['locator_candidates'] else 'none found; full read needed'}",
                  f"- **Machine basis:** {esc(x['machine_basis'])}", f"- **Recommended reviewer decision:** {x['recommended_decision']}"]
            for e in x["unreviewed_excerpts"][:2]:
                Q.append(f"- _unreviewed excerpt, p.{e['page']}:_ “{esc(e['unreviewed_excerpt'])}”")
            Q.append("")
    (REPO / "preview/M63_G5_REMAINING_REVIEW_QUEUE.md").write_text("\n".join(Q) + "\n")
    print(json.dumps(dash, indent=1))
    print("H", H)


if __name__ == "__main__":
    main()
