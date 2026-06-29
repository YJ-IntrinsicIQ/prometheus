import os
os.environ["HF_HOME"] = "./hf_cache"

from sentence_transformers import SentenceTransformer
import chromadb

# Load local embedding model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Chroma client
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Create collection
collection = chroma_client.get_or_create_collection(
    name="finance_docs"
)

# Read document
with open("data/sample.txt", "r") as file:
    text = file.read()

# Generate embedding locally
embedding = model.encode(text).tolist()

# Store in vector DB
collection.add(
    documents=[text],
    embeddings=[embedding],
    ids=["doc1"]
)

print("Local embedding stored successfully!")