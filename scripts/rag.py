import os

os.environ["HF_HOME"] = "./hf_cache"

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from groq import Groq
import chromadb

from knowledge.ai.groq import resolve_groq_model

# Load env vars
load_dotenv()

# Groq Client
client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

# Embedding Model
embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

# Chroma
chroma_client = chromadb.PersistentClient(
    path="./chroma_db"
)

collection = chroma_client.get_collection(
    "finance_docs"
)

# question = "What did management say about margins?"
question = input(
    "Ask a question: "
)

# Convert query to embedding
query_embedding = embedding_model.encode(
    question
).tolist()

# Retrieve relevant chunks
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=5
)

for doc, distance in zip(
    results["documents"][0],
    results["distances"][0]
):
    print("=" * 50)
    print(f"Distance: {distance}")
    print(doc)

context = "\n\n".join(
    results["documents"][0]
)

prompt = f"""
You are a skeptical financial analyst.

Rules:

1. Answer only from supplied context.
2. Cite the relevant chunk.
3. If insufficient evidence exists, say so.
4. Do not speculate.
5. Mention uncertainty.

Context:
{context}

Question:
{question}
"""

response = client.chat.completions.create(
    model=resolve_groq_model(),
    messages=[
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0
)

print("\nANSWER:\n")
print(
    response.choices[0].message.content
)
