import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[2] / "tools"))
import resolve_eng135a_provenance as r

def packet(tmp_path, item="X", excerpt=None):
    d=tmp_path/"companies/acme/company_memory"; d.mkdir(parents=True)
    p=d/"a.json"; p.write_text(json.dumps({"items":[{"source_item_id":item,"source_year":"fy24","source_text":excerpt,"page":12}]}))
    r.ROOT=tmp_path
    return {"company":"acme","record_id":"R1","source_refs":[{"source_artifact":"a.json","source_item_id":item,"source_year":"fy24"}]}

def test_exact_resolution(tmp_path):
    out=r.resolve(packet(tmp_path,excerpt="verbatim evidence")); assert out["resolution_status"]=="RESOLVED_EXACT"; assert out["passage"]=="verbatim evidence"

def test_missing_item(tmp_path):
    packet(tmp_path,item="present")
    out=r.resolve({"company":"acme","record_id":"R1","source_refs":[{"source_artifact":"a.json","source_item_id":"missing","source_year":"fy24"}]}); assert out["reason_code"]=="SOURCE_ITEM_NOT_FOUND"

def test_missing_passage_is_partial(tmp_path):
    out=r.resolve(packet(tmp_path,excerpt=None)); assert out["resolution_status"]=="RESOLVED_PARTIAL"; assert out["reason_code"]=="PASSAGE_NOT_PERSISTED"

def test_missing_artifact(tmp_path):
    r.ROOT=tmp_path; out=r.resolve({"company":"acme","record_id":"R1","source_refs":[{"source_artifact":"none.json","source_item_id":"X"}]}); assert out["reason_code"]=="SOURCE_ARTIFACT_MISSING"
