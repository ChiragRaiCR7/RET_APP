try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Settings = None

class ChromaClient:
    def __init__(self, persist_dir: str = "./runtime/chroma"):
        if CHROMADB_AVAILABLE and chromadb:
            self.client = chromadb.Client(
                Settings(persist_directory=persist_dir)
            )
        else:
            self.client = None

    def get_or_create(self, name: str):
        if self.client:
            return self.client.get_or_create_collection(name)
        return None

    def delete(self, name: str):
        if self.client:
            self.client.delete_collection(name)

