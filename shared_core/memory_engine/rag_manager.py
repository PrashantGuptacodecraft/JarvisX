"""
memory/rag_manager.py
Handles Local Retrieval-Augmented Generation (RAG) using ChromaDB.
"""
import os
import uuid
from config.logger import get_logger

log = get_logger("memory.rag")

class RAGManager:
    def __init__(self):
        self.collection = None
        self._init_db()

    def _init_db(self):
        try:
            import chromadb
            # Persist the vector db in data/chroma
            db_path = os.path.join(os.getcwd(), "data", "chroma")
            os.makedirs(db_path, exist_ok=True)
            self.client = chromadb.PersistentClient(path=db_path)
            self.collection = self.client.get_or_create_collection(name="jarvis_longterm_memory")
            log.info("ChromaDB initialized for RAG memory.")
        except Exception as e:
            log.warning(f"ChromaDB not available: {e}. RAG Memory disabled.")

    def ingest_text(self, text: str, source: str = "user_input"):
        """Chunk and insert text into the vector database."""
        if not self.collection: return "Error: RAG Memory disabled."
        
        # Simple chunking: 1000 characters
        chunks = [text[i:i+1000] for i in range(0, len(text), 1000)]
        ids = [str(uuid.uuid4()) for _ in chunks]
        metadatas = [{"source": source} for _ in chunks]
        
        try:
            self.collection.add(
                documents=chunks,
                metadatas=metadatas,
                ids=ids
            )
            return f"Successfully ingested text into memory (source: {source})."
        except Exception as e:
            log.error(f"Error ingesting text: {e}")
            return f"Error: {e}"

    def ingest_file(self, filepath: str):
        """Read a file and ingest its text."""
        if not self.collection: return "Error: RAG Memory disabled."
        if not os.path.exists(filepath): return "Error: File not found."
        
        text = ""
        ext = os.path.splitext(filepath)[-1].lower()
        
        try:
            if ext == ".pdf":
                import PyPDF2
                with open(filepath, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
            elif ext in [".txt", ".md", ".py", ".csv", ".json"]:
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
            else:
                return f"Error: Unsupported file format {ext}"
                
            if text.strip():
                return self.ingest_text(text, source=os.path.basename(filepath))
            else:
                return "Error: File is empty or could not be read."
        except Exception as e:
            log.error(f"Error reading file {filepath}: {e}")
            return f"Error reading file: {e}"

    def search(self, query: str, n_results: int = 3):
        """Search the vector database for relevant memories/documents."""
        if not self.collection: return "Error: RAG Memory disabled."
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            
            if not docs:
                return "No relevant information found in memory."
                
            out = "--- Search Results from Memory ---\n"
            for doc, meta in zip(docs, metas):
                src = meta.get("source", "unknown")
                out += f"[Source: {src}]\n{doc}\n\n"
            return out.strip()
        except Exception as e:
            log.error(f"Error searching memory: {e}")
            return f"Error searching memory: {e}"
