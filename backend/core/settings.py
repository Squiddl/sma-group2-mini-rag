import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://raguser:ragpass@postgres:5432/ragdb"

    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_grpc_port: int = 6334
    qdrant_prefer_grpc: bool = True
    qdrant_collection_prefix: str = "doc_"

    llm_provider: str = "ollama"  # Options: "anthropic", "openai", "ollama"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://ollama:11434"
    llm_model: str = "llama2"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096
    llm_timeout: float = 30.0

    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_batch_size: int = 32
    embedding_cache_size: int = 10000
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    reranker_batch_size: int = 16

    use_docling_parser: bool = True
    use_llm_metadata_extraction: bool = False

    docling_use_vlm: bool = False
    docling_vlm_backend: str = "transformers"
    docling_vlm_model: str = "granite"
    docling_generate_images: bool = False
    docling_batch_size: int = 1
    docling_timeout: float = 120.0
    docling_max_pages: int = 0

    use_markdown_tables: bool = True

    ocr_engine: str = "rapidocr"
    use_gpu_for_ocr: bool = False

    chunk_size: int = 1000
    chunk_overlap: int = 180
    parent_chunk_size: int = 2000
    parent_chunk_overlap: int = 400
    child_chunk_size: int = 400
    child_chunk_overlap: int = 80

    enable_neighbor_expansion: bool = True
    neighbor_expansion_window: int = 4
    top_k_retrieval: int = 20
    top_k_rerank: int = 6

    query_expansion_cache_size: int = 1000
    query_expansion_cache_ttl: int = 3600

    zotero_library_id: str = ""
    zotero_library_type: str = "user"
    zotero_api_key: str = ""

    data_dir: str = "/app/data"
    models_cache_dir: str = "/app/models"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"
        protected_namespaces = ()

    @property
    def upload_dir(self) -> str:
        return os.path.join(self.data_dir, "uploads")

    @property
    def pickle_dir(self) -> str:
        return os.path.join(self.data_dir, "pickles")

    def get_active_provider(self) -> str:
        if self.llm_provider and self.llm_provider.lower() in ["anthropic", "openai", "ollama"]:
            return self.llm_provider.lower()

        if self.anthropic_api_key:
            return "anthropic"
        elif self.openai_api_key:
            return "openai"
        else:
            return "ollama"

    def get_vlm_model_spec(self) -> str:
        if self.docling_vlm_backend == "mlx":
            return "GRANITEDOCLING_MLX"
        return "GRANITEDOCLING_TRANSFORMERS"

    def ensure_directories(self) -> None:
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.pickle_dir, exist_ok=True)
        os.makedirs(self.models_cache_dir, exist_ok=True)


settings = Settings()