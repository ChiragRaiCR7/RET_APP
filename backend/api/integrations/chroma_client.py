import chromadb
from chromadb.config import Settings

class ChromaClient:
    def __init__(self, persist_dir: str = "./runtime/chroma"):
        self.client = chromadb.Client(
            Settings(persist_directory=persist_dir)
        )

    def get_or_create(self, name: str):
        return self.client.get_or_create_collection(name)

    def delete(self, name: str):
        self.client.delete_collection(name)
