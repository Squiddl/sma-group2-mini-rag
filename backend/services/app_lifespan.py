"""
Kombinierter Lifespan Manager für RAG System + Zotero Background Services

Startet beim App-Start:
- RAG System Services (Embeddings, Vector Store, Reranker, etc.)
- Zotero Poller (alle 15s)
- Document Processing Worker (alle 30s)
"""
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI

from db.session import init_db, SessionLocal
from services.settings import settings
from db.models import Document

logger = logging.getLogger(__name__)

# Globale Service-Instanzen
embedding_service: Optional['EmbeddingService'] = None
vector_store_service: Optional['VectorStoreService'] = None
reranker_service: Optional['RerankerService'] = None
doc_processor: Optional['DocumentProcessor'] = None
rag_service: Optional['RAGService'] = None
metadata_extractor: Optional['MetadataExtractor'] = None


def _sync_documents_with_qdrant(vector_store) -> None:
    """Synchronisiert Dokumente zwischen PostgreSQL und Qdrant"""
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global embedding_service, vector_store_service, reranker_service
    global doc_processor, rag_service, metadata_extractor

    logger.info("=" * 80)
    logger.info("🚀 Starting RAG System Initialization")
    logger.info("=" * 80)

    # Datenbank initialisieren
    logger.info("📊 Initializing database...")
    init_db()
    settings.ensure_directories()
    logger.info("✅ Database initialized")

    # Services initialisieren
    logger.info("🔧 Initializing core services...")

    from services.embeddings import EmbeddingService
    from services.vector_store import VectorStoreService
    from services.reranker import RerankerService
    from services.document_processor import DocumentProcessor
    from services.rag_service import RAGService
    from services.metadata_extractor import MetadataExtractor

    embedding_service = EmbeddingService.get_instance()
    logger.info(f"   ✅ Embedding service ready (model: {settings.embedding_model})")

    vector_store_service = VectorStoreService(embedding_service)
    logger.info(f"   ✅ Vector store connected (Qdrant: {settings.qdrant_host})")

    reranker_service = RerankerService.get_instance()
    logger.info(f"   ✅ Reranker service ready (model: {settings.reranker_model})")

    doc_processor = DocumentProcessor()
    logger.info(f"   ✅ Document processor ready")

    rag_service = RAGService(vector_store_service, reranker_service, doc_processor)
    logger.info(f"   ✅ RAG service ready")

    metadata_extractor = MetadataExtractor()
    logger.info(f"   ✅ Metadata extractor ready")

    # Dokument-Synchronisation
    logger.info("🔄 Syncing documents with Qdrant...")
    _sync_documents_with_qdrant(vector_store_service)

    logger.info("✅ RAG System initialization complete")

    logger.info("=" * 80)
    logger.info("🔄 Starting Zotero Background Services")
    logger.info("=" * 80)

    from services.zotero_poller import get_poller
    from services.document_processing_worker import get_worker

    poller = get_poller()
    worker = get_worker()

    await poller.start()
    logger.info(f"   ✅ Zotero poller started (interval: {poller.poll_interval}s)")

    await worker.start()
    logger.info(f"   ✅ Document worker started (interval: {worker.check_interval}s)")

    logger.info("=" * 80)
    logger.info("✅ All services initialized successfully")
    logger.info("=" * 80)

    # ========================================
    # APP RUNNING
    # ========================================
    yield

    # ========================================
    # SHUTDOWN
    # ========================================
    logger.info("=" * 80)
    logger.info("👋 Shutting down services...")
    logger.info("=" * 80)

    # Zotero Background Services stoppen
    logger.info("🛑 Stopping Zotero background services...")
    await poller.stop()
    logger.info("   ✅ Zotero poller stopped")

    await worker.stop()
    logger.info("   ✅ Document worker stopped")

    logger.info("=" * 80)
    logger.info("✅ Shutdown complete")
    logger.info("=" * 80)


# Export für andere Module
def get_embedding_service():
    """Getter für Embedding Service"""
    return embedding_service


def get_vector_store_service():
    """Getter für Vector Store Service"""
    return vector_store_service


def get_reranker_service():
    """Getter für Reranker Service"""
    return reranker_service


def get_rag_service():
    """Getter für RAG Service"""
    return rag_service


def get_metadata_extractor():
    """Getter für Metadata Extractor"""
    return metadata_extractor