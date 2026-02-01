from pathlib import Path
from typing import List, Optional
import logging

from api.integrations.azure_openai import AzureOpenAIClient
from api.integrations.chroma_client import ChromaClient
from api.services.storage_service import get_session_dir

logger = logging.getLogger(__name__)

try:
    openai_client = AzureOpenAIClient()
except Exception as e:
    logger.warning(f"Azure OpenAI client initialization failed: {e}")
    openai_client = None

chroma = ChromaClient()


def _chunk_text(text: str, size: int = 800) -> list[str]:
    return [text[i:i+size] for i in range(0, len(text), size)]


def index_session(session_id: str, collection: str) -> int:
    if not openai_client:
        raise RuntimeError("OpenAI client not available")
    
    if not chroma.client:
        raise RuntimeError("Chroma client not available")
    
    sess_dir = get_session_dir(session_id)
    texts = []

    output_dir = sess_dir / "output"
    if not output_dir.exists():
        logger.warning(f"Output directory does not exist: {output_dir}")
        return 0

    for f in output_dir.glob("*.csv"):
        texts.append(f.read_text(encoding="utf-8"))

    chunks = []
    metadatas = []

    for t in texts:
        for chunk in _chunk_text(t):
            chunks.append(chunk)
            metadatas.append({"session_id": session_id})

    if not chunks:
        logger.warning(f"No chunks to index for session {session_id}")
        return 0

    embeddings = openai_client.embed_texts(chunks)
    col = chroma.get_or_create(collection)

    if not col:
        raise RuntimeError("Failed to create Chroma collection")

    # Chroma may expect embeddings in different formats depending on version
    try:
        # Try with explicit embeddings parameter first
        col.add(
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=[f"{collection}-{i}" for i in range(len(chunks))],
        )
    except (TypeError, ValueError):
        try:
            # Some Chroma versions need embeddings as numpy arrays
            import numpy as np
            col.add(
                documents=chunks,
                embeddings=np.array(embeddings, dtype=np.float32),
                metadatas=metadatas,
                ids=[f"{collection}-{i}" for i in range(len(chunks))],
            )
        except (TypeError, ImportError):
            # Fallback: let Chroma generate embeddings
            col.add(
                documents=chunks,
                metadatas=metadatas,
                ids=[f"{collection}-{i}" for i in range(len(chunks))],
            )

    return len(chunks)


def chat_with_collection(collection: str, question: str) -> dict:
    if not openai_client:
        raise RuntimeError("OpenAI client not available")
    
    if not chroma.client:
        raise RuntimeError("Chroma client not available")
    
    col = chroma.get_or_create(collection)

    if not col:
        raise RuntimeError("Collection not found or accessible")

    q_embed = openai_client.embed_texts([question])[0]
    res = col.query(query_embeddings=[q_embed], n_results=5)

    if not res:
        return {"answer": "No relevant documents found.", "citations": []}

    documents = res.get("documents")
    if not documents or not documents[0]:
        return {"answer": "No relevant documents found.", "citations": []}

    contexts = documents[0] if isinstance(documents, list) and len(documents) > 0 else []
    
    if not contexts:
        return {"answer": "No relevant documents found.", "citations": []}

    context_text = "\n\n".join(contexts)

    system = (
        "You are a RETv4 assistant. Answer strictly using the provided context. "
        "Cite facts from the context."
    )

    answer = openai_client.chat(system, f"Context:\n{context_text}\n\nQ:{question}")

    metadatas_list = res.get("metadatas", [])
    metadatas = metadatas_list[0] if isinstance(metadatas_list, list) and len(metadatas_list) > 0 else []
    
    distances_list = res.get("distances", [])
    scores = distances_list[0] if isinstance(distances_list, list) and len(distances_list) > 0 else []

    citations = [
        {"content": c, "metadata": m, "score": float(s)}
        for c, m, s in zip(contexts, metadatas, scores)
    ]

    return {
        "answer": answer,
        "citations": citations,
    }
