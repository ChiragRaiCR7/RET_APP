from pathlib import Path
from typing import List

from api.integrations.azure_openai import AzureOpenAIClient
from api.integrations.chroma_client import ChromaClient
from api.services.storage_service import get_session_dir

openai_client = AzureOpenAIClient()
chroma = ChromaClient()


def _chunk_text(text: str, size: int = 800) -> list[str]:
    return [text[i:i+size] for i in range(0, len(text), size)]


def index_session(session_id: str, collection: str) -> int:
    sess_dir = get_session_dir(session_id)
    texts = []

    for f in (sess_dir / "output").glob("*.csv"):
        texts.append(f.read_text(encoding="utf-8"))

    chunks = []
    metadatas = []

    for t in texts:
        for chunk in _chunk_text(t):
            chunks.append(chunk)
            metadatas.append({"session_id": session_id})

    embeddings = openai_client.embed_texts(chunks)
    col = chroma.get_or_create(collection)

    col.add(
        documents=chunks,
        embeddings=embeddings,
        metadatas=metadatas,
        ids=[f"{collection}-{i}" for i in range(len(chunks))],
    )

    return len(chunks)


def chat_with_collection(collection: str, question: str):
    col = chroma.get_or_create(collection)

    q_embed = openai_client.embed_texts([question])[0]
    res = col.query(query_embeddings=[q_embed], n_results=5)

    contexts = res["documents"][0]
    scores = res["distances"][0]
    metadatas = res["metadatas"][0]

    context_text = "\n\n".join(contexts)

    system = (
        "You are a RETv4 assistant. Answer strictly using the provided context. "
        "Cite facts from the context."
    )

    answer = openai_client.chat(system, f"Context:\n{context_text}\n\nQ:{question}")

    citations = [
        {"content": c, "metadata": m, "score": float(s)}
        for c, m, s in zip(contexts, metadatas, scores)
    ]

    return {
        "answer": answer,
        "citations": citations,
    }
