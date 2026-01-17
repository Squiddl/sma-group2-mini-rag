import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from persistence.session import init_db, SessionLocal

from services.ingest.pipeline import DocumentPipelineService
from services.ingest.processor import DocumentProcessor
from core.embeddings import EmbeddingService
from services.ingest.metadata import MetadataExtractor
from services.rag.service import RAGService
from core.reranker import RerankerService
from core.settings import settings
from persistence.models import Document

from core.vector_store import VectorStoreService

logger = logging.getLogger(__name__)

def _sync_documents_with_qdrant(vector_store) -> None:
    db = SessionLocal()
    try:
        documents = db.query(Document).all()
        synced_count = 0
        valid_collections: set[str] = set()

        logger.info(f"🔄 Syncing {len(documents)} documents with Qdrant...")

        for doc in documents:
            collection_name = doc.collection_name
            if collection_name:
                valid_collections.add(collection_name)

            if doc.processed and not vector_store.document_exists(collection_name):
                logger.warning(
                    f"⚠️  Document {doc.id} ({doc.filename}) missing in Qdrant, marking as unprocessed"
                )
                doc.processed = False
                doc.num_chunks = 0
                synced_count += 1

        if synced_count > 0:
            db.commit()
            logger.info(f"🔄 Synced {synced_count} documents with Qdrant")

        vector_store.cleanup_orphaned_collections(valid_collections)
        logger.info(
            f"✅ Document sync complete ({len(documents)} documents, {len(valid_collections)} collections)"
        )

    except Exception as exc:
        logger.exception(f"❌ Failed to sync documents with Qdrant: {exc}")
        db.rollback()
    finally:
        db.close()

embedding_service: Optional['EmbeddingService'] = None
vector_store_service: Optional['VectorStoreService'] = None
reranker_service: Optional['RerankerService'] = None
doc_processor: Optional['DocumentProcessor'] = None
rag_service: Optional['RAGService'] = None
metadata_extractor: Optional['MetadataExtractor'] = None
document_pipeline: Optional['DocumentPipelineService'] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global embedding_service, vector_store_service, reranker_service
    global doc_processor, rag_service, metadata_extractor, document_pipeline

    logging.getLogger('services').setLevel(logging.INFO)
    logging.getLogger('document_processing_worker').setLevel(logging.INFO)
    logging.getLogger('document_pipeline').setLevel(logging.INFO)
    logging.getLogger('file_handler').setLevel(logging.INFO)
    logging.getLogger('document_processor').setLevel(logging.INFO)
    logging.getLogger('zotero_poller').setLevel(logging.INFO)

    logger.info("=" * 80)
    logger.info("🚀 Starting RAG System Initialization")
    logger.info("=" * 80)

    logger.info("📊 Initializing database...")
    init_db()
    settings.ensure_directories()
    logger.info("✅ Database initialized")

    logger.info("🔧 Initializing core ...")

    from core.embeddings import EmbeddingService
    from core.vector_store import VectorStoreService
    from core.reranker import RerankerService
    from services.rag.service import RAGService
    from services.ingest.metadata import MetadataExtractor
    from services.ingest.pipeline import DocumentPipelineService

    embedding_service = EmbeddingService.get_instance()
    logger.info(f"   ✅ Embedding service ready (model: {settings.embedding_model})")

    # Warmup the embedding model to ensure it's fully loaded
    embedding_service.warmup()
    logger.info(f"   ✅ Embedding model warmed up and ready for use")

    vector_store_service = VectorStoreService(embedding_service)
    logger.info(f"   ✅ Vector store connected (Qdrant: {settings.qdrant_host})")

    reranker_service = RerankerService.get_instance()
    logger.info(f"   ✅ Reranker service ready (model: {settings.reranker_model})")

    # Warmup the reranker model to ensure it's fully loaded
    reranker_service.warmup()
    logger.info(f"   ✅ Reranker model warmed up and ready for use")

    doc_processor = DocumentProcessor()
    logger.info(f"   ✅ Document processor ready")

    rag_service = RAGService(vector_store_service, reranker_service, doc_processor)
    logger.info(f"   ✅ RAG service ready")

    metadata_extractor = MetadataExtractor(use_llm=settings.use_llm_metadata_extraction)
    logger.info(f"   ✅ Metadata extractor ready")

    document_pipeline = DocumentPipelineService(vector_store_service, metadata_extractor)
    logger.info(f"   ✅ Document pipeline ready")

    logger.info("🔄 Syncing documents with Qdrant...")
    _sync_documents_with_qdrant(vector_store_service)

    logger.info("✅ RAG System initialization complete")

    logger.info("=" * 80)
    logger.info("🔄 Starting Background Services")
    logger.info("=" * 80)

    from services.integrations.zotero.poller import get_poller
    from services.ingest.worker import get_worker

    logger.info("🔧 Initializing Zotero poller...")
    poller = get_poller()
    await poller.start()
    logger.info(f"   ✅ Zotero poller started (interval: {poller.poll_interval}s)")

    logger.info("🔧 Initializing Document processing worker...")
    worker = get_worker()
    await worker.start()
    logger.info(f"   ✅ Document worker started (interval: {worker.check_interval}s)")
    logger.info(f"   ℹ️  Worker will check for pending documents every {worker.check_interval}s")

    logger.info("=" * 80)
    logger.info("✅ All services initialized successfully")
    logger.info("=" * 80)

    yield

    logger.info("=" * 80)
    logger.info("👋 Shutting down ...")
    logger.info("=" * 80)

    logger.info("🛑 Stopping Zotero background ...")
    await poller.stop()
    logger.info("   ✅ Zotero poller stopped")

    await worker.stop()
    logger.info("   ✅ Document worker stopped")

    logger.info("=" * 80)
    logger.info("✅ Shutdown complete")
    logger.info("=" * 80)


def get_embedding_service():
    return embedding_service


def get_vector_store_service():
    return vector_store_service


def get_reranker_service():
    return reranker_service


def get_rag_service():
    return rag_service


def get_metadata_extractor():
    return metadata_extractor


def get_document_pipeline():
    return document_pipeline
