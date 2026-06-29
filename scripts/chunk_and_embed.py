import os 
os.environ["HF_HOME"] = "./hf_cache"

from sentence_transformers import SentenceTransformer
import chromadb

model = SentenceTransformer("all-MiniLM-L6-v2")

chroma_client = chromadb.PersistentClient(path="./chroma_db")

collection = chroma_client.get_or_create_collection(
    name = "finance_docs"
)

with open("data/sample.txt") as f:
    text = f.read()

#Very simple chunking
chunks = text.split("\n")

#Embed and store chunks
for i, chunk in enumerate(chunks):
    if not chunk.strip():
        continue

    embedding = model.encode(chunk).tolist()

    collection.add(
        ids=[f"chunk_{i}"],
        documents=[chunk],
        embeddings=[embedding],
        metadatas=[{
            "company": "sample_company",
            "year": 2025,
            "section": "management_commentary"
        }]
    )

print("Chunks embedded and stored successfully!")
