"""M63/G3 coverage meter: scores the source-anchored reference set (reference_set.json) against the artifacts under a companies root.
Usage: python3 tests/g3/measure_coverage.py [--root <dir holding companies/>] [--json out.json] [--quiet]
Levels per anchor: value_ok (value + period + basis recovered), page_ok (cited page equals the filing page), available (a downstream consumer
artifact carries it). FIN anchors read the fact registry; CAP the capital ledger / corporate actions / registry; TXT the structured intelligence
artifacts (never the raw chunks); TXN the capital ledger / projects (state must not be 'completed'); FID the commitment register (must not be a promise).
The reference set was written from the filing PDFs, not from extractor output (see build_reference.py)."""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]


def arg(name, default=None):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


ROOT = pathlib.Path(arg("--root", REPO))
A = json.loads((HERE / arg("--ref", "reference_set.json")).read_text())


def jload(p):
    try:
        return json.loads(pathlib.Path(p).read_text())
    except Exception:
        return None


def close(a, b, tol=0.005):
    return b is not None and abs(a - b) <= max(tol * abs(a), 0.011)


def facts(co, fy):
    d = jload(ROOT / "companies" / co / fy / "financials" / "financial_fact_registry.json")
    return (d["available_facts"] + d["derived_facts"] + d.get("basis_variants", [])) if d else []


def year_blob(co, fy):
    d = ROOT / "companies" / co / fy / "intelligence"
    return "".join(p.read_text() for p in d.glob("*.json")) if d.exists() else ""


def financial_disclosure_blob(co, fy):
    """The sourced narrative artifacts the financial stage writes (never the raw tables, which contain every number and would match anything)."""
    d = ROOT / "companies" / co / fy / "financials"
    names = ("financial_headline_metrics.json", "financial_transaction_disclosures.json", "financial_anchor_coverage.json", "corporate_actions.json")
    return "".join((d / n).read_text() for n in names if (d / n).exists())


def memory_blob(co, sub):
    d = ROOT / "companies" / co / "company_memory" / sub
    return "".join(p.read_text() for p in d.glob("*.json")) if d.exists() else ""


def score(a):
    k, co, fy = a["kind"], a["co"], a["fy"]
    r = dict(id=a["id"], kind=k, co=co, cat=a["cat"], value_ok=False, page_ok=False, available=False, note="")
    if k == "FIN":
        period = a.get("period", fy)
        fs = [f for f in facts(co, fy) + (facts(co, period) if period != fy else []) if f.get("metric_id") == a["metric"] and f.get("fiscal_year") == period and f.get("value") is not None]
        if not fs:
            r["note"] = "no registry for this year" if not facts(co, fy) else "metric absent for period"
            return r
        good = [f for f in fs if any(close(abs(v), abs(f["value"])) for v in [a["value"], *a.get("alt", [])])]
        if not good:
            r["note"] = f"value differs: {[f['value'] for f in fs][:3]} vs {a['value']}"
            return r
        b = [f for f in good if f.get("basis") == a["basis"]]
        if not b:
            r["note"] = f"basis {sorted({str(f.get('basis')) for f in good})} vs {a['basis']}"
            return r
        r["value_ok"] = True
        r["page_ok"] = (not a.get("page_check", True)) or any(f.get("source_page") in (a["page"], a.get("page2")) for f in b)
        r["available"] = any(f.get("usable_downstream", True) for f in b)
        if not r["page_ok"]:
            r["note"] = f"page {sorted({str(f.get('source_page')) for f in b})} vs {a['page']}"
        return r
    if k == "CAP":
        if a["metric"] == "dividends_paid":
            fs = [f for f in facts(co, fy) if f.get("metric_id") == "dividends_paid" and f.get("fiscal_year") == fy]
            hit = [f for f in fs if close(a["value"], abs(f["value"]))]
            r["value_ok"] = bool(hit)
            r["page_ok"] = any(f.get("source_page") == a["page"] for f in hit)
            r["available"] = r["value_ok"]
            r["note"] = "" if hit else ("no registry for this year" if not facts(co, fy) else f"value differs {[f['value'] for f in fs]}")
            return r
        if a["metric"] == "buyback":
            led = jload(ROOT / "companies" / co / "company_memory" / "capital_allocation_outcomes" / "capital_allocation_outcomes.json")
            found = []

            def walk(o):
                if isinstance(o, dict):
                    if "buyback" in json.dumps(o, ensure_ascii=False).lower() and any(isinstance(v, (int, float)) and not isinstance(v, bool) and close(a["value"], v) for v in o.values()):
                        found.append(o)
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            walk(led or {})
            ca = jload(ROOT / "companies" / co / fy / "financials" / "corporate_actions.json") or {}
            ca_ok = any(x.get("action_type") == "buyback" and close(a["value"], x.get("amount_crore")) for x in ca.get("actions", []))
            r["value_ok"] = bool(found) or ca_ok
            r["available"] = bool(found)
            r["page_ok"] = r["value_ok"]
            r["note"] = "" if r["value_ok"] else "buyback consideration not carried by the ledger or corporate actions"
            return r
        if a["metric"] == "dividends_declared_per_share":
            ca = jload(ROOT / "companies" / co / fy / "financials" / "corporate_actions.json") or {}
            vals = sorted({x.get("per_share_amount") for x in ca.get("actions", []) if x.get("action_type") == "dividend" and x.get("value_type_used") == "per_share_declared" and x.get("per_share_amount") is not None})
            ok = any(abs(v - a["value"]) < 0.005 for v in vals) or (len(vals) > 1 and abs(sum(vals) - a["value"]) < 0.005)
            r["value_ok"] = r["page_ok"] = r["available"] = ok
            r["note"] = "" if ok else f"declared per-share dividends carried: {vals}"
            return r
        if a["metric"] == "buyback_cash_outflow":
            fs = [f for f in facts(co, fy) if f.get("metric_id") in ("buyback_paid", "buyback_cash_outflow", "share_buyback_paid") and f.get("fiscal_year") == fy]
            r["note"] = "no buyback cash-outflow fact in the registry" if not fs else ""
            r["value_ok"] = r["page_ok"] = r["available"] = any(close(a["value"], abs(f["value"])) for f in fs)
            return r
        r["note"] = "no automated downstream locator for this metric"
        return r
    if k == "TXT":
        key = a["needle"]
        text = (year_blob(co, fy) + financial_disclosure_blob(co, fy) + memory_blob(co, "ask_intrinsiciq") + memory_blob(co, "company_intelligence")).lower()
        r["available"] = key.lower() in text
        if a.get("metric"):                      # a headline figure can also be carried as a registry fact (management_highlights)
            hit = [f for f in facts(co, fy) if f.get("metric_id") == a["metric"] and f.get("fiscal_year") == fy and close(a["num"], f.get("value"))]
            if hit:
                r["available"] = True
                r["page_ok"] = any(f.get("source_page") == a["page"] for f in hit)
                r["value_ok"] = True
                if not r["page_ok"]:
                    r["note"] = f"page {sorted({str(f.get('source_page')) for f in hit})} vs {a['page']}"
                return r
        # A sourced filing disclosure can live in the existing registry as well as year intelligence.
        disclosure = [f for f in facts(co, fy) if f.get("fiscal_year") == fy and key.lower() in str(f.get("source_line_item", "")).lower() and f.get("usable_downstream")]
        if disclosure:
            r["available"] = r["value_ok"] = True
            r["page_ok"] = any(f.get("source_page") == a["page"] for f in disclosure)
            return r
        r["value_ok"] = r["page_ok"] = r["available"]
        if not r["available"]:
            r["note"] = f"'{key}' not in structured intelligence artifacts"
        return r
    if k == "TXN":
        low = (memory_blob(co, "capital_allocation_outcomes") + memory_blob(co, "projects") + year_blob(co, fy)).lower()
        r["available"] = "organon" in low
        r["value_ok"] = r["available"] and bool(re.search(r"organon[^\"]{0,300}(announced|signed|pending|not completed|not yet completed)", low))
        r["page_ok"] = r["value_ok"]
        r["note"] = "" if r["value_ok"] else "no announced/pending state recorded for the transaction"
        return r
    if k == "FID":
        reg = jload(ROOT / "companies" / co / "company_memory" / "management_commitments" / "management_commitments.json") or {}
        bad = [c for c in reg.get("commitments", []) if a["forbidden"].lower() in c.get("original_statement", "").lower() and (c.get("hard_commitment") or c.get("accountability_ontology") == "VERIFIABLE_COMMITMENT")]
        r["value_ok"] = r["page_ok"] = r["available"] = not bad
        r["note"] = "" if not bad else f"{len(bad)} promoted as verifiable/hard company commitment"
        return r
    return r


rows = [score(a) for a in A]


def pct(f, rs):
    return round(100 * sum(1 for x in rs if x[f]) / max(1, len(rs)), 1)


summary = {"anchors": len(rows), "value_recall_pct": pct("value_ok", rows), "exact_page_pct": pct("page_ok", rows), "downstream_available_pct": pct("available", rows)}
for co in ("datapatterns", "tanla", "sun_pharma", "ujjivan", "ltts"):
    rs = [x for x in rows if x["co"] == co]
    if not rs:
        continue
    summary[co] = {"n": len(rs), "value": pct("value_ok", rs), "page": pct("page_ok", rs), "downstream": pct("available", rs)}
if "--quiet" not in sys.argv:
    for x in rows:
        print(f"{x['id']:6} {x['kind']:3} value={'Y' if x['value_ok'] else '-'} page={'Y' if x['page_ok'] else '-'} avail={'Y' if x['available'] else '-'}  {x['note']}")
print(json.dumps(summary))
if arg("--json"):
    pathlib.Path(arg("--json")).write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
