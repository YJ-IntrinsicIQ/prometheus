from knowledge.discovery_runtime import DiscoveryRuntime
from knowledge.module_extractor.schema import ModuleAnswer, ModuleExtractionResult
from knowledge.question_engine.schema import DiscoveryPlan, Question, QuestionModule


class FakeRetriever:
    def build_company_index(self, company, year):
        return None

    def retrieve(self, query, top_k=10):
        class Chunk:
            def __init__(self, text):
                self.text = text
                self.chunk_id = "chunk-1"

        class Response:
            def __init__(self):
                self.chunks = [Chunk("evidence")]

        return Response()


class FakeExtractor:
    def extract(self, module, chunks, business_context=None):
        return ModuleExtractionResult(
            module_id=module.module_id,
            module_name=module.module_name,
            answers=[
                ModuleAnswer(
                    question_id=module.questions[0].id,
                    question=module.questions[0].question,
                    direct_answer="Found",
                    supporting_points=["Evidence present"],
                    primary_evidence=["chunk-1"],
                    secondary_evidence=[],
                    confidence=0.8,
                    status="FOUND",
                )
            ],
        )


def test_runtime_executes_plan_modules_and_collects_statistics():
    module = QuestionModule(
        module_id="capex",
        module_name="Capex",
        description="Capex questions",
        questions=[Question(id="q1", module="capex", priority=1, category="capex", question="What is the capex plan?")],
    )
    plan = DiscoveryPlan(
        business_dnas=["Manufacturing"],
        loaded_modules=[module.module_id],
        questions=module.questions,
    )

    runtime = DiscoveryRuntime(
        retriever=FakeRetriever(),
        extractor=FakeExtractor(),
        module_definitions=[module],
    )
    result = runtime.run(plan, business_classification={"business_dnas": ["Manufacturing"]})

    assert result.executed_modules == ["capex"]
    assert len(result.module_results) == 1
    assert result.statistics.modules_executed == 1
    assert result.statistics.llm_calls == 1
    assert result.statistics.retrieved_chunks == 1
    assert result.statistics.questions_answered == 1


def test_runtime_resolves_module_from_registry_without_explicit_definitions():
    plan = DiscoveryPlan(
        business_dnas=["Manufacturing"],
        loaded_modules=["capital_allocation"],
        questions=[
            Question(
                id="q1",
                module="capital_allocation",
                priority=1,
                category="capital",
                question="What is the capital allocation plan?",
            )
        ],
    )

    runtime = DiscoveryRuntime(retriever=FakeRetriever())
    result = runtime.run(plan, business_classification={"business_dnas": ["Manufacturing"]})

    assert result.executed_modules == ["capital_allocation"]
    assert result.statistics.modules_executed == 1
    assert result.statistics.questions_answered == 6


def test_runtime_runs_without_retriever():
    plan = DiscoveryPlan(
        business_dnas=["Manufacturing"],
        loaded_modules=["capital_allocation"],
        questions=[
            Question(
                id="q1",
                module="capital_allocation",
                priority=1,
                category="capital",
                question="What is the capital allocation plan?",
            )
        ],
    )

    runtime = DiscoveryRuntime()
    result = runtime.run(plan, business_classification={"company": "polymatech", "year": "2024"})

    assert result.executed_modules == ["capital_allocation"]
    assert result.statistics.modules_executed == 1


def test_runtime_caps_chunks_per_question_when_env_is_set(monkeypatch):
    module = QuestionModule(
        module_id="capex",
        module_name="Capex",
        description="Capex questions",
        questions=[Question(id="q1", module="capex", priority=1, category="capex", question="What is the capex plan?")],
    )
    plan = DiscoveryPlan(
        business_dnas=["Manufacturing"],
        loaded_modules=[module.module_id],
        questions=module.questions,
    )
    seen = {}

    class ManyChunkRetriever:
        def build_company_index(self, company, year):
            return None

        def retrieve(self, query, top_k=10):
            class Chunk:
                def __init__(self, idx):
                    self.text = f"evidence-{idx}"
                    self.chunk_id = f"chunk-{idx}"

            class Response:
                def __init__(self):
                    self.chunks = [Chunk(1), Chunk(2), Chunk(3)]

            return Response()

    class RecordingExtractor:
        def extract(self, module, chunks, business_context=None):
            seen["chunk_ids"] = [chunk.chunk_id for chunk in chunks]
            return ModuleExtractionResult(
                module_id=module.module_id,
                module_name=module.module_name,
                answers=[
                    ModuleAnswer(
                        question_id=module.questions[0].id,
                        question=module.questions[0].question,
                        direct_answer="Found",
                        supporting_points=[],
                        primary_evidence=seen["chunk_ids"],
                        secondary_evidence=[],
                        confidence=0.8,
                        status="FOUND",
                    )
                ],
            )

    monkeypatch.setenv("BI_MAX_CHUNKS_PER_QUESTION", "2")
    runtime = DiscoveryRuntime(
        retriever=ManyChunkRetriever(),
        extractor=RecordingExtractor(),
        module_definitions=[module],
    )
    result = runtime.run(plan, business_classification={"business_dnas": ["Manufacturing"]})

    assert seen["chunk_ids"] == ["chunk-1", "chunk-2"]
    assert result.statistics.retrieved_chunks == 2
