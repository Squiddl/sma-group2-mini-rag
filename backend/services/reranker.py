from typing import List, Dict, Any
from FlagEmbedding import FlagReranker
from config.settings import settings


class RerankerService:
    """Service for reranking retrieved documents"""
    
    def __init__(self):
        self.model = FlagReranker(settings.reranker_model, use_fp16=False)
    
    def rerank(self, query: str, documents: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Rerank documents based on relevance to query
        
        Args:
            query: The search query
            documents: List of retrieved documents with 'text' field
            top_k: Number of top documents to return
            
        Returns:
            Reranked list of top_k documents with scores
        """
        if not documents:
            return []
        
        # Compute similarity scores using the bilingual reranker
        for doc in documents:
            score = self.model.compute_score([query, doc['text']], normalize=True)
            doc['rerank_score'] = float(score)
        
        # Sort by rerank score and return top_k
        reranked = sorted(documents, key=lambda x: x['rerank_score'], reverse=True)
        return reranked[:top_k]
