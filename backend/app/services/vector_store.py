"""
Vector Store Service for User-Based Document Chunk Storage

Provides user-isolated vector storage using ChromaDB for document chunks.
Supports hybrid retrieval (vector + keyword search) and hierarchical expansion.
"""

import uuid
from typing import List, Dict, Any, Optional
import logging
import os

logger = logging.getLogger(__name__)


class VectorStore:
    """User-based vector store for document chunks using ChromaDB with Google embeddings"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.collection_name = f"user_{user_id}"
        
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            from chromadb.config import Settings
            
            # Validate Google API key
            gemini_api_key = os.getenv("GEMINI_API_KEY")
            if not gemini_api_key:
                logger.error("GEMINI_API_KEY not found in environment variables")
                raise ValueError("GEMINI_API_KEY is required for Google embedding function")
            
            # Create Google embedding function using Gemini API key
            embedding_function = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
                api_key=gemini_api_key,
                model_name="models/text-embedding-004"
            )
            
            # Initialize ChromaDB client with in-memory storage for users
            self.client = chromadb.EphemeralClient()

            # Create or get collection for this user with Google embeddings
            self.collection = self.client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=embedding_function,
                metadata={"user_id": user_id, "embedding_model": "text-embedding-004"}
            )
            
            self.available = True
            logger.info(f"Initialized vector store for user {user_id} with Google text-embedding-004")
            
        except ImportError as e:
            logger.warning(f"ChromaDB or required dependencies not available: {e}")
            self.client = None
            self.collection = None
            self.available = False
            raise ImportError("ChromaDB and google-generativeai are required for vector store functionality")
        except ValueError as e:
            logger.error(f"Configuration error: {e}")
            self.client = None
            self.collection = None
            self.available = False
            raise e
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB with Google embeddings: {e}")
            self.client = None
            self.collection = None
            self.available = False
    
    def store_document_chunks(self, document_id: str, l1_chunks: List[Dict], l2_chunks: List[Dict]) -> int:
        """Store L2 chunks in vector DB with L1 metadata for retrieval"""
        
        if not self.available:
            logger.warning("Vector store not available, skipping chunk storage")
            return 0
        
        if not l2_chunks:
            logger.warning(f"No L2 chunks to store for document {document_id}")
            return 0
        
        try:
            # Prepare data for ChromaDB
            embeddings = []  # ChromaDB will auto-generate embeddings
            documents = []
            metadatas = []
            ids = []
            
            # Create parent lookup for L1 metadata
            l1_lookup = {chunk["chunk_id"]: chunk for chunk in l1_chunks}
            
            for l2_chunk in l2_chunks:
                chunk_id = l2_chunk["chunk_id"]
                parent_chunk = l1_lookup.get(l2_chunk["parent_id"])
                
                ids.append(chunk_id)
                documents.append(l2_chunk["text"])
                
                # Rich metadata for filtering and retrieval
                metadata = {
                    "document_id": document_id,
                    "parent_id": l2_chunk["parent_id"],
                    "level": 2,
                    "token_count": l2_chunk["token_count"],
                    "window_index": l2_chunk["window_index"],
                    "filename": l2_chunk["filename"],
                    "start_page": l2_chunk["start_page"],
                    "end_page": l2_chunk["end_page"],
                    "offset_start": l2_chunk["offset_start"],
                    "offset_end": l2_chunk["offset_end"]
                }
                
                # Add parent chunk metadata if available
                if parent_chunk:
                    metadata.update({
                        "parent_start_page": parent_chunk["start_page"],
                        "parent_end_page": parent_chunk["end_page"],
                        "parent_token_count": parent_chunk["token_count"],
                        "has_tables": len(parent_chunk.get("tables", [])) > 0,
                        "table_count": len(parent_chunk.get("tables", [])),
                        "paragraph_count": len(parent_chunk.get("paragraphs", []))
                    })
                
                metadatas.append(metadata)
            
            # Store in ChromaDB (will auto-generate embeddings)
            self.collection.add(
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )
            
            logger.info(f"Stored {len(l2_chunks)} L2 chunks for document {document_id}")
            return len(l2_chunks)
            
        except Exception as e:
            logger.error(f"Failed to store chunks for document {document_id}: {e}")
            return 0
    
    def delete_document_chunks(self, document_id: str) -> bool:
        """Remove all chunks for a document"""
        
        if not self.available:
            return True  # Consider it successful if vector store not available
        
        try:
            # Query for all chunks with this document_id
            results = self.collection.get(
                where={"document_id": document_id}
            )
            
            if results["ids"]:
                self.collection.delete(ids=results["ids"])
                logger.info(f"Deleted {len(results['ids'])} chunks for document {document_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete chunks for document {document_id}: {e}")
            return False
    
    def search_chunks(self, query: str, top_k: int = 40, document_ids: Optional[List[str]] = None) -> List[Dict]:
        """Search for relevant chunks using vector similarity"""
        
        if not self.available:
            logger.warning("Vector store not available, returning empty results")
            return []
        
        try:
            # Build where clause for filtering
            where_clause = {}
            if document_ids:
                where_clause["document_id"] = {"$in": document_ids}
            
            # Perform vector search
            results = self.collection.query(
                query_texts=[query],
                n_results=min(top_k, 100),  # ChromaDB limit
                where=where_clause if where_clause else None
            )
            
            # Format results
            chunks = []
            if results["ids"] and results["ids"][0]:  # Check if we have results
                for i in range(len(results["ids"][0])):
                    chunk = {
                        "chunk_id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "distance": results["distances"][0][i] if results.get("distances") else None
                    }
                    chunks.append(chunk)
            
            logger.info(f"Found {len(chunks)} chunks for query: {query[:50]}...")
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to search chunks: {e}")
            return []
    
    def get_chunk_neighbors(self, chunk_id: str, neighbor_count: int = 2) -> List[Dict]:
        """Get neighboring chunks (by window_index) for context expansion"""
        
        if not self.available:
            return []
        
        try:
            # Get the target chunk first
            target_results = self.collection.get(
                ids=[chunk_id],
                include=["metadatas"]
            )
            
            if not target_results["ids"]:
                return []
            
            target_metadata = target_results["metadatas"][0]
            parent_id = target_metadata["parent_id"]
            window_index = target_metadata["window_index"]
            
            # Get neighboring chunks from the same parent
            neighbor_results = self.collection.get(
                where={
                    "parent_id": parent_id,
                    "window_index": {
                        "$gte": max(0, window_index - neighbor_count),
                        "$lte": window_index + neighbor_count
                    }
                },
                include=["documents", "metadatas"]
            )
            
            # Format and sort by window_index
            neighbors = []
            if neighbor_results["ids"]:
                for i in range(len(neighbor_results["ids"])):
                    if neighbor_results["ids"][i] != chunk_id:  # Exclude the original chunk
                        neighbor = {
                            "chunk_id": neighbor_results["ids"][i],
                            "text": neighbor_results["documents"][i],
                            "metadata": neighbor_results["metadatas"][i]
                        }
                        neighbors.append(neighbor)
            
            # Sort by window_index
            neighbors.sort(key=lambda x: x["metadata"]["window_index"])
            
            return neighbors
            
        except Exception as e:
            logger.error(f"Failed to get neighbors for chunk {chunk_id}: {e}")
            return []
    
    def get_parent_chunk_context(self, l2_chunk_id: str, l1_chunks: List[Dict]) -> Optional[Dict]:
        """Get the parent L1 chunk for additional context"""
        
        if not self.available:
            return None
        
        try:
            # Get L2 chunk metadata
            results = self.collection.get(
                ids=[l2_chunk_id],
                include=["metadatas"]
            )
            
            if not results["ids"]:
                return None
            
            parent_id = results["metadatas"][0]["parent_id"]
            
            # Find parent in L1 chunks
            for l1_chunk in l1_chunks:
                if l1_chunk["chunk_id"] == parent_id:
                    return l1_chunk
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get parent context for chunk {l2_chunk_id}: {e}")
            return None
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """Get statistics about chunks stored in this session"""
        
        if not self.available:
            return {"available": False}
        
        try:
            # Get all chunks in the collection
            results = self.collection.get(include=["metadatas"])
            
            if not results["ids"]:
                return {
                    "available": True,
                    "total_chunks": 0,
                    "documents": 0
                }
            
            # Analyze metadata
            document_ids = set()
            token_counts = []
            page_ranges = []
            
            for metadata in results["metadatas"]:
                document_ids.add(metadata["document_id"])
                token_counts.append(metadata["token_count"])
                page_ranges.append((metadata["start_page"], metadata["end_page"]))
            
            return {
                "available": True,
                "total_chunks": len(results["ids"]),
                "documents": len(document_ids),
                "avg_tokens_per_chunk": sum(token_counts) / len(token_counts) if token_counts else 0,
                "total_tokens": sum(token_counts),
                "page_range": (min(p[0] for p in page_ranges), max(p[1] for p in page_ranges)) if page_ranges else (0, 0)
            }
            
        except Exception as e:
            logger.error(f"Failed to get session statistics: {e}")
            return {"available": False, "error": str(e)}
    
    def cleanup_user_session(self):
        """Clean up user resources"""
        
        if not self.available:
            return
        
        try:
            # Delete the collection
            self.client.delete_collection(self.collection_name)
            logger.info(f"Cleaned up vector store for user {self.user_id}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup user {self.user_id}: {e}")


class VectorStoreManager:
    """Manager for user-based vector stores"""
    
    def __init__(self):
        self.stores: Dict[str, VectorStore] = {}
    
    def get_store(self, user_id: str) -> VectorStore:
        """Get or create vector store for user"""
        print(user_id)
        if user_id not in self.stores:
            self.stores[user_id] = VectorStore(user_id)

        return self.stores[user_id]
    
    def cleanup_user_session(self, user_id: str):
        """Clean up vector store for user"""
        
        if user_id in self.stores:
            self.stores[user_id].cleanup_user_session()
            del self.stores[user_id]
    
    def get_active_sessions(self) -> List[str]:
        """Get list of active user IDs"""
        return list(self.stores.keys())


# Global manager instance
vector_store_manager = VectorStoreManager()
