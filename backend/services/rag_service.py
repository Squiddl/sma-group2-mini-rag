import os
import logging
from typing import List, Dict, Any, Iterator, Generator, Callable
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from config.settings import settings
from services.embeddings import VectorStoreService
from services.reranker import RerankerService
from services.document_processor import DocumentProcessor
from sqlalchemy.orm import Session
from models.database import Document

logger = logging.getLogger(__name__)

# Minimum rerank score threshold to consider results "good"
MIN_RERANK_SCORE = 0.3


class RAGService:
    """Service for RAG-based question answering"""
    
    def __init__(
        self,
        vector_store: VectorStoreService,
        reranker: RerankerService,
        doc_processor: DocumentProcessor
    ):
        self.vector_store = vector_store
        self.reranker = reranker
        self.doc_processor = doc_processor
        self.llm = ChatOpenAI(
            model=settings.llm_model,
            openai_api_key=settings.llm_api_key,
            openai_api_base=settings.llm_api_base,
            temperature=0.7,
            streaming=True
        )
        # Non-streaming LLM for query generation
        self.llm_sync = ChatOpenAI(
            model=settings.llm_model,
            openai_api_key=settings.llm_api_key,
            openai_api_base=settings.llm_api_base,
            temperature=0.7,
            streaming=False
        )

    def generate_query_variations(self, original_query: str) -> List[str]:
        """Generate 3 different query variations using LLM."""
        messages = [
            SystemMessage(content=(
                "You are a query expansion assistant. Given a user question, generate exactly 3 different "
                "variations of the question that might help find relevant information. Each variation should "
                "approach the question from a different angle or use different keywords.\n\n"
                "Return ONLY the 3 queries, one per line, without numbering or bullets."
            )),
            HumanMessage(content=f"Original question: {original_query}")
        ]
        
        response = self.llm_sync.invoke(messages)
        variations = [q.strip() for q in response.content.strip().split('\n') if q.strip()]
        # Return up to 3 variations, or pad with original if needed
        result = variations[:3]
        while len(result) < 3:
            result.append(original_query)
        return result

    def retrieve_for_query(self, query: str) -> List[Dict[str, Any]]:
        """Retrieve chunks for a single query."""
        return self.vector_store.search(query, top_k=settings.top_k_retrieval)

    def multi_query_retrieve_and_rerank(
        self, 
        original_query: str, 
        db: Session,
        on_thinking: Callable[[str], None] | None = None
    ) -> tuple[List[str], List[Dict[str, str]], List[Dict[str, Any]]]:
        """
        Multi-query retrieval with automatic retry if results are poor.
        
        Returns:
            Tuple of (parent_contexts, source_descriptions, thinking_steps)
        """
        thinking_steps: List[Dict[str, Any]] = []
        
        def emit_thinking(step_type: str, message: str, details: Any = None):
            step = {"type": step_type, "message": message, "details": details}
            thinking_steps.append(step)
            if on_thinking:
                on_thinking(step)
        
        emit_thinking("start", "Starting multi-query retrieval...")
        
        # Round 1: Generate query variations
        emit_thinking("generating_queries", "Generating 3 query variations...")
        query_variations = self.generate_query_variations(original_query)
        emit_thinking("queries_generated", f"Generated query variations", query_variations)
        
        # Retrieve for all queries
        all_chunks: List[Dict[str, Any]] = []
        seen_chunk_keys = set()
        
        for i, query in enumerate(query_variations):
            emit_thinking("searching", f"Searching with query {i+1}: \"{query[:80]}...\"" if len(query) > 80 else f"Searching with query {i+1}: \"{query}\"")
            chunks = self.retrieve_for_query(query)
            for chunk in chunks:
                chunk_key = f"{chunk.get('doc_id')}_{chunk.get('chunk_id')}"
                if chunk_key not in seen_chunk_keys:
                    seen_chunk_keys.add(chunk_key)
                    all_chunks.append(chunk)
            emit_thinking("search_complete", f"Query {i+1} returned {len(chunks)} chunks")
        
        emit_thinking("deduplication", f"Total unique chunks after deduplication: {len(all_chunks)}")
        
        if not all_chunks:
            emit_thinking("no_results", "No chunks found in round 1")
            # Try round 2 with reformulated queries
            return self._retry_with_new_queries(original_query, db, thinking_steps, emit_thinking)
        
        # Rerank all chunks together
        emit_thinking("reranking", f"Reranking {len(all_chunks)} chunks...")
        reranked_chunks = self.reranker.rerank(original_query, all_chunks, top_k=settings.top_k_rerank)
        
        # Check if results are good enough
        best_score = reranked_chunks[0].get('rerank_score', 0) if reranked_chunks else 0
        emit_thinking("rerank_complete", f"Best rerank score: {best_score:.3f}", 
                     [{"text": c['text'][:100], "score": c.get('rerank_score', 0)} for c in reranked_chunks[:3]])
        
        if best_score < MIN_RERANK_SCORE:
            emit_thinking("low_score", f"Best score {best_score:.3f} below threshold {MIN_RERANK_SCORE}, retrying with new queries...")
            return self._retry_with_new_queries(original_query, db, thinking_steps, emit_thinking)
        
        # Load parent documents
        emit_thinking("loading_parents", "Loading parent documents...")
        parent_contexts, sources = self._load_parents_from_chunks(reranked_chunks, db)
        emit_thinking("complete", f"Retrieved {len(parent_contexts)} parent contexts")
        
        return parent_contexts, sources, thinking_steps

    def _retry_with_new_queries(
        self, 
        original_query: str, 
        db: Session, 
        thinking_steps: List[Dict[str, Any]],
        emit_thinking: Callable
    ) -> tuple[List[str], List[Dict[str, str]], List[Dict[str, Any]]]:
        """Retry retrieval with reformulated queries."""
        
        emit_thinking("retry_start", "Round 2: Generating alternative query formulations...")
        
        # Generate different queries with explicit instruction to rephrase
        messages = [
            SystemMessage(content=(
                "The previous search queries did not find good results. Generate 3 completely different "
                "formulations of the question using synonyms, related concepts, or breaking down the question "
                "into sub-questions. Be creative and try different approaches.\n\n"
                "Return ONLY the 3 queries, one per line, without numbering or bullets."
            )),
            HumanMessage(content=f"Original question: {original_query}")
        ]
        
        response = self.llm_sync.invoke(messages)
        new_variations = [q.strip() for q in response.content.strip().split('\n') if q.strip()][:3]
        emit_thinking("retry_queries_generated", "Generated alternative queries", new_variations)
        
        # Retrieve for new queries
        all_chunks: List[Dict[str, Any]] = []
        seen_chunk_keys = set()
        
        for i, query in enumerate(new_variations):
            emit_thinking("retry_searching", f"Searching with alternative query {i+1}")
            chunks = self.retrieve_for_query(query)
            for chunk in chunks:
                chunk_key = f"{chunk.get('doc_id')}_{chunk.get('chunk_id')}"
                if chunk_key not in seen_chunk_keys:
                    seen_chunk_keys.add(chunk_key)
                    all_chunks.append(chunk)
        
        emit_thinking("retry_deduplication", f"Total unique chunks from retry: {len(all_chunks)}")
        
        if not all_chunks:
            emit_thinking("retry_no_results", "Still no results after retry")
            return [], [], thinking_steps
        
        # Rerank
        emit_thinking("retry_reranking", f"Reranking {len(all_chunks)} chunks from retry...")
        reranked_chunks = self.reranker.rerank(original_query, all_chunks, top_k=settings.top_k_rerank)
        
        best_score = reranked_chunks[0].get('rerank_score', 0) if reranked_chunks else 0
        emit_thinking("retry_rerank_complete", f"Retry best rerank score: {best_score:.3f}")
        
        # Load parents regardless of score (best effort)
        emit_thinking("retry_loading_parents", "Loading parent documents from retry...")
        parent_contexts, sources = self._load_parents_from_chunks(reranked_chunks, db)
        emit_thinking("retry_complete", f"Retrieved {len(parent_contexts)} parent contexts from retry")
        
        return parent_contexts, sources, thinking_steps

    def _load_parents_from_chunks(
        self, 
        chunks: List[Dict[str, Any]], 
        db: Session
    ) -> tuple[List[str], List[Dict[str, str]]]:
        """Load parent documents from reranked chunks."""
        parent_contexts: List[str] = []
        sources: List[Dict[str, str]] = []
        seen_parents = set()
        
        for chunk in chunks:
            doc_id = chunk['doc_id']
            parent_id = chunk.get('parent_id')
            
            parent_key = f"{doc_id}_{parent_id}"
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)
            
            document = db.query(Document).filter(Document.id == doc_id).first()
            if not document or not document.pickle_path:
                continue
            
            parent_text = self.doc_processor.load_parent_document(
                document.pickle_path, 
                parent_id
            )
            
            if parent_text:
                parent_contexts.append(parent_text)
                sources.append({
                    "label": f"{document.filename} (chunk {parent_id})",
                    "content": parent_text.strip()
                })
        
        return parent_contexts, sources
    
    def retrieve_and_rerank(self, query: str, db: Session) -> tuple[List[str], List[Dict[str, str]]]:
        """
        Retrieve relevant chunks, rerank them, and return parent documents
        
        Returns:
            Tuple of (parent_contexts, source_descriptions)
        """
        # Step 1: Retrieve child chunks from vector store
        retrieved_chunks = self.vector_store.search(query, top_k=settings.top_k_retrieval)
        
        if not retrieved_chunks:
            return [], []
        
        # Step 2: Rerank chunks
        reranked_chunks = self.reranker.rerank(query, retrieved_chunks, top_k=settings.top_k_rerank)
        
        # Step 3: Load parent documents
        parent_contexts: List[str] = []
        sources: List[Dict[str, str]] = []
        seen_parents = set()
        
        for chunk in reranked_chunks:
            doc_id = chunk['doc_id']
            parent_id = chunk.get('parent_id')
            
            # Avoid duplicate parents
            parent_key = f"{doc_id}_{parent_id}"
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)
            
            # Get document from database
            document = db.query(Document).filter(Document.id == doc_id).first()
            if not document or not document.pickle_path:
                continue
            
            # Load parent document from pickle
            parent_text = self.doc_processor.load_parent_document(
                document.pickle_path, 
                parent_id
            )
            
            if parent_text:
                parent_contexts.append(parent_text)
                sources.append({
                    "label": f"{document.filename} (chunk {parent_id})",
                    "content": parent_text.strip()
                })
        
        return parent_contexts, sources
    
    def _build_messages(self, query: str, contexts: List[str], chat_history: List[Dict[str, str]] | None = None) -> List[Any]:
        """Build messages for the LLM including context and history."""
        context_str = "\n\n".join([f"Context {i+1}:\n{ctx}" for i, ctx in enumerate(contexts)])

        messages: List[Any] = [
            SystemMessage(content=(
                "You are a helpful assistant that answers questions based on the provided context. "
                "Use the context to answer the question accurately. If the context doesn't contain "
                "enough information to answer the question, say so."
            ))
        ]

        if chat_history:
            for msg in chat_history[-5:]:
                if msg['role'] == 'user':
                    messages.append(HumanMessage(content=msg['content']))
                elif msg['role'] == 'assistant':
                    messages.append(AIMessage(content=msg['content']))

        user_message = f"Context:\n{context_str}\n\nQuestion: {query}"
        messages.append(HumanMessage(content=user_message))
        return messages

    def generate_answer(self, query: str, contexts: List[str], chat_history: List[Dict[str, str]] = None) -> str:
        """
        Generate answer using LLM based on retrieved contexts
        
        Args:
            query: User question
            contexts: List of relevant context strings
            chat_history: Optional list of previous messages
            
        Returns:
            Generated answer
        """
        messages = self._build_messages(query, contexts, chat_history)
        response = self.llm.invoke(messages)
        return response.content

    def generate_answer_stream(
        self,
        query: str,
        contexts: List[str],
        chat_history: List[Dict[str, str]] | None = None
    ) -> Iterator[str]:
        """Stream answer tokens from the LLM."""
        messages = self._build_messages(query, contexts, chat_history)
        for chunk in self.llm.stream(messages):
            text = ""
            if hasattr(chunk, "message") and getattr(chunk.message, "content", None):
                text = chunk.message.content
            elif hasattr(chunk, "content") and chunk.content:
                text = chunk.content
            elif hasattr(chunk, "delta") and isinstance(chunk.delta, dict):
                text = chunk.delta.get("content", "")

            if text:
                yield text
    
    def query(self, query: str, db: Session, chat_history: List[Dict[str, str]] = None) -> tuple[str, List[str]]:
        """
        Main RAG query method
        
        Returns:
            Tuple of (answer, sources)
        """
        # Retrieve and rerank
        contexts, sources = self.retrieve_and_rerank(query, db)
        
        if not contexts:
            return "I couldn't find relevant information in the documents to answer your question.", []
        
        # Generate answer
        answer = self.generate_answer(query, contexts, chat_history)
        
        return answer, sources
