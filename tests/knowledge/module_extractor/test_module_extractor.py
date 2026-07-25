from knowledge.module_extractor import ModuleExtractor, parse_module_extraction_payload
from knowledge.question_engine.schema import Question, QuestionModule


def test_parser_accepts_valid_payload():
    payload = '''{"module_id":"capex","module_name":"Capex","answers":[{"question_id":"q1","question":"What is the capex plan?","answer":"The company plans expansion.","confidence":0.91,"supporting_chunk_ids":["chunk-1"],"status":"FOUND"}]}'''
    result = parse_module_extraction_payload(payload)
    assert result.module_id == "capex"
    assert result.answers[0].status == "FOUND"


def test_extractor_uses_llm_response():
    class FakeLLM:
        def __call__(self, prompt):
            return '{"module_id":"capex","module_name":"Capex","answers":[{"question_id":"q1","question":"What is the capex plan?","answer":"Not Found","confidence":0.1,"supporting_chunk_ids":[],"status":"NOT_FOUND"}]}'

    module = QuestionModule(
        module_id="capex",
        module_name="Capex",
        description="Capex questions",
        questions=[Question(id="q1", module="capex", priority=1, category="capex", question="What is the capex plan?")],
    )

    extractor = ModuleExtractor(llm_client=FakeLLM())
    result = extractor.extract(module, [{"text": "sample evidence"}])

    assert result.answers[0].direct_answer == "Not Found"
    assert result.answers[0].status == "NOT_FOUND"


def test_extractor_builds_budget_aware_input_pack_with_business_dnas():
    captured = {}

    class FakeLLM:
        def __call__(self, prompt, llm_input_pack=None):
            captured["prompt"] = prompt
            captured["pack"] = llm_input_pack
            return '{"module_id":"capex","module_name":"Capex","answers":[{"question_id":"q1","question":"What is the capex plan?","answer":"Not Found","confidence":0.1,"supporting_chunk_ids":[],"status":"NOT_FOUND"}]}'

    module = QuestionModule(
        module_id="capex",
        module_name="Capex",
        description="Capex questions",
        questions=[Question(id="q1", module="capex", priority=1, category="capex", question="What is the capex plan?")],
    )

    extractor = ModuleExtractor(llm_client=FakeLLM())
    result = extractor.extract(
        module,
        [
            {
                "chunk_id": "chunk_keep",
                "text": "Management approved Rs 100 crore expansion capex in FY2025.",
                "retrieval_score": 0.95,
                "page": 5,
                "year": "fy25",
                "evidence_ids": ["ev_keep"],
                "evidence_quality": {"company_specificity": "high", "actor_type": "company"},
            },
            {
                "chunk_id": "chunk_macro",
                "text": "The global economy remains uncertain and industry outlook is mixed. " * 20,
                "retrieval_score": 0.1,
                "evidence_quality": {"company_specificity": "low", "actor_type": "industry"},
            },
        ],
        business_context={"business_dnas": ["Manufacturing", "Semiconductor"]},
    )

    pack = captured["pack"]
    payload = str(pack)
    assert pack["facts"][0]["business_dnas"] == ["Manufacturing", "Semiconductor"]
    assert "ev_keep" in payload
    assert any(chunk["chunk_id"] == "chunk_keep" for chunk in pack["observations"][0]["chunks"])
    assert result.answers[0].status == "NOT_FOUND"
