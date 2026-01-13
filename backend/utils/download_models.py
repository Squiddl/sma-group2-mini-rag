from sentence_transformers import SentenceTransformer

EMBEDDING_MODEL = 'mixedbread-ai/deepset-mxbai-embed-de-large-v1'
RERANKER_MODEL = 'cross-encoder/ms-marco-MiniLM-L-6-v2'

SentenceTransformer(EMBEDDING_MODEL)
SentenceTransformer(RERANKER_MODEL)