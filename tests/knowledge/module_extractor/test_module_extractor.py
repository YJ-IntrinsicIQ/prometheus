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
