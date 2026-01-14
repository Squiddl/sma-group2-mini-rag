import asyncio
import logging
import os
from typing import Optional

from db.models import Document
from db.session import SessionLocal
from .embeddings import EmbeddingService
from .document_processor import process_document
from .file_handler import FileHandler
from .metadata_extractor import MetadataExtractor, create_metadata_chunk
from .settings import settings
from .vector_store import VectorStoreService
from .zotero_service import ZoteroService

logger = logging.getLogger(__name__)


class DocumentProcessingWorker:
    """Async Worker für Document Processing - verarbeitet Dokumente im Hintergrund"""

    def __init__(self):
        self.zotero = ZoteroService.get_instance()
        self.metadata_extractor = MetadataExtractor()
        self.embedding_service = EmbeddingService.get_instance()
        self.vector_store = VectorStoreService(self.embedding_service)
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.check_interval = 30  # Sekunden

    async def start(self):
        """Startet den Processing Worker"""
        if self.running:
            logger.warning("Document processing worker already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._processing_loop())
        logger.info(f"Document processing worker started (interval: {self.check_interval}s)")

    async def stop(self):
        """Stoppt den Processing Worker"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Document processing worker stopped")

    async def _processing_loop(self):
        """Haupt-Processing-Loop"""
        while self.running:
            try:
                await self._process_pending_documents()
            except Exception as exc:
                logger.error(f"Error in document processing: {exc}", exc_info=True)

            await asyncio.sleep(self.check_interval)

    async def _process_pending_documents(self):
        """Verarbeitet wartende Dokumente"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_process_documents)

    def _sync_process_documents(self):
        """Synchrone Methode zum Verarbeiten von Dokumenten"""
        db = SessionLocal()
        try:
            # Alle nicht-verarbeiteten Dokumente finden
            pending_docs = db.query(Document).filter(
                Document.processed == False
            ).limit(5).all()  # Max 5 gleichzeitig

            if not pending_docs:
                return

            logger.info(f"Processing {len(pending_docs)} pending documents...")

            for doc in pending_docs:
                try:
                    self._process_single_document(doc, db)
                    db.commit()
                except Exception as exc:
                    logger.error(f"Failed to process document {doc.filename}: {exc}")
                    db.rollback()

        finally:
            db.close()

    def _process_single_document(self, doc: Document, db):
        """Verarbeitet ein einzelnes Dokument"""
        if not self.zotero.is_enabled():
            logger.warning(f"Skipping {doc.filename}: Zotero not enabled")
            return

        # Finde Zotero item
        zotero_items = self.zotero.get_all_documents()
        item_key = None

        for item in zotero_items:
            data = item.get('data', {})
            filename = data.get('filename') or data.get('title', '')
            if filename == doc.filename:
                item_key = data.get('key')
                break

        if not item_key:
            logger.warning(f"Could not find Zotero item for {doc.filename}")
            return

        # Download
        download_dir = os.path.join(settings.data_dir, 'zotero_downloads')
        os.makedirs(download_dir, exist_ok=True)

        file_path = self.zotero.download_document(item_key, download_dir)

        if not file_path or not os.path.exists(file_path):
            logger.error(f"Download failed for {doc.filename}")
            return

        logger.info(f"Processing document: {doc.filename}")

        # Metadata extrahieren
        first_pages = FileHandler.extract_first_pages_text(file_path, num_pages=2)
        pdf_metadata = FileHandler.extract_pdf_metadata(file_path)

        extracted_metadata = self.metadata_extractor.extract_metadata_from_text(
            first_pages,
            doc.filename,
            pdf_metadata
        )

        # Volltext extrahieren
        full_text = FileHandler.extract_text(file_path)

        # Pickle path
        pickle_path = os.path.join(settings.pickle_dir, f"doc_{doc.id}.pkl")
        collection_name = f"{settings.qdrant_collection_prefix}{doc.id}"

        # Metadata chunk
        metadata_chunk = None
        if extracted_metadata and extracted_metadata.get('title') != 'Not found':
            metadata_chunk = create_metadata_chunk(extracted_metadata, doc.filename)

        # Chunks erstellen
        chunks = process_document(
            doc.id,
            full_text,
            pickle_path=pickle_path,
            document_name=doc.filename,
            metadata_chunk=metadata_chunk
        )

        # Vector store - add_documents erstellt Embeddings intern
        self.vector_store.add_documents(
            doc.id,
            chunks,
            collection_name,
            document_name=doc.filename
        )

        # Dokument aktualisieren
        doc.file_path = file_path
        doc.processed = True
        doc.num_chunks = len(chunks)
        doc.pickle_path = pickle_path
        doc.query_enabled = True

        logger.info(f"✓ Processed: {doc.filename} ({len(chunks)} chunks)")


# Globale Worker-Instanz
_worker: Optional[DocumentProcessingWorker] = None


def get_worker() -> DocumentProcessingWorker:
    """Gibt die globale Worker-Instanz zurück"""
    global _worker
    if _worker is None:
        _worker = DocumentProcessingWorker()
    return _worker