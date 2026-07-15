from knowledge.ai import get_llm

llm = get_llm()

response = llm.generate(
    prompt="Reply with exactly: Hello Prometheus",
    temperature=0.0,
    max_tokens=20,
)

print("=" * 40)
print("TEXT:", response.text)
print("PROVIDER:", response.provider)
print("MODEL:", response.model)
print("TOKENS:", response.total_tokens)
print("=" * 40)