import asyncio
import logging
import os
from typing import Optional

from persistence.models import Document
from persistence.session import SessionLocal
from .pipeline import DocumentPipelineService
from core.embeddings import EmbeddingService
from .metadata import MetadataExtractor
from core.settings import settings
from core.vector_store import VectorStoreService
from services.integrations.zotero.client import ZoteroService

logger = logging.getLogger(__name__)


class DocumentProcessingWorker:
    def __init__(self):
        self.zotero = ZoteroService.get_instance()
        self.metadata_extractor = MetadataExtractor(use_llm=settings.use_llm_metadata_extraction)
        self.embedding_service = EmbeddingService.get_instance()
        self.vector_store = VectorStoreService(self.embedding_service)
        self.pipeline = DocumentPipelineService(
            self.vector_store,
            self.metadata_extractor
        )

        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.check_interval = 10

        self._check_event: Optional[asyncio.Event] = None

    async def start(self):
        if self.running:
            logger.warning("Document processing worker already running")
            return

        self.running = True
        self._check_event = asyncio.Event()
        self._task = asyncio.create_task(self._processing_loop())
        logger.info(f"Document processing worker started (interval: {self.check_interval}s)")
        logger.info(f"   Worker will respond immediately when new documents are uploaded")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Document processing worker stopped")

    def trigger_check(self):
        if not self._check_event or not self.running:
            logger.warning("⚠️  Worker not running, cannot trigger check")
            return

        try:
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self._check_event.set)
                logger.info("📢 Worker notified: immediate document check triggered (async context)")
            except RuntimeError:
                def _set_event():
                    try:
                        import threading
                        for thread in threading.enumerate():
                            if hasattr(thread, '_target') and 'lifespan' in str(thread._target):
                                break
                        self._check_event.set()
                        logger.info("📢 Worker notified: immediate document check triggered (sync context)")
                    except Exception as e:
                        logger.error(f"Failed to trigger worker check: {e}")

                _set_event()

        except Exception as exc:
            logger.error(f"❌ Failed to trigger worker check: {exc}")

    async def _processing_loop(self):
        logger.info("=" * 80)
        logger.info("🔄 [WORKER] Document processing loop started")
        logger.info(f"   → Check interval: {self.check_interval}s")
        logger.info(f"   → Immediate triggers: enabled via asyncio.Event")
        logger.info("=" * 80)

        try:
            logger.info("🚀 [WORKER] Initial startup check for existing unprocessed documents...")
            await self._process_pending_documents()
        except Exception as exc:
            logger.error(f"❌ [WORKER] Error in initial document check: {exc}", exc_info=True)

        while self.running:
            try:
                logger.debug("🔍 [WORKER] Checking for pending documents...")
                await self._process_pending_documents()
            except Exception as exc:
                logger.error(f"❌ [WORKER] Error in document processing loop: {exc}", exc_info=True)

            try:
                logger.debug(f"💤 [WORKER] Sleeping (max {self.check_interval}s or until triggered)...")
                await asyncio.wait_for(self._check_event.wait(), timeout=self.check_interval)
                logger.info("⚡ [WORKER] Immediate check triggered by upload/sync!")
                self._check_event.clear()
            except asyncio.TimeoutError:
                logger.debug("⏰ [WORKER] Periodic check (timeout reached)")
                pass

    async def _process_pending_documents(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.process_documents)

    def process_documents(self):
        import time
        from sqlalchemy import or_
        db = SessionLocal()

        processed_count = 0
        batch_start_time = time.time()

        try:
            while True:
                logger.debug("📊 [WORKER] Querying database for next pending document...")

                pending_doc = db.query(Document).filter(
                    Document.processed == False,
                    or_(Document.num_chunks is None, Document.num_chunks >= 0)
                ).first()

                if not pending_doc:
                    if processed_count > 0:
                        batch_elapsed = time.time() - batch_start_time
                        logger.info("=" * 80)
                        logger.info(f"✅ [WORKER BATCH COMPLETE]")
                        logger.info(f"   → Processed: {processed_count} document(s)")
                        logger.info(f"   → Total time: {batch_elapsed:.1f}s")
                        logger.info(f"   → Avg per doc: {batch_elapsed/processed_count:.1f}s")
                        logger.info("=" * 80)
                    else:
                        logger.debug("✅ [WORKER] No pending documents found")
                        total_docs = db.query(Document).count()
                        processed_docs = db.query(Document).filter(Document.processed == True).count()
                        logger.debug(f"   Total documents in DB: {total_docs}")
                        logger.debug(f"   Already processed: {processed_docs}")
                        logger.debug(f"   Pending (processed=False): {total_docs - processed_docs}")
                    break
                doc = pending_doc
                current_doc_id = doc.id
                current_doc_filename = doc.filename

                try:
                    doc_start_time = time.time()
                    processed_count += 1
                    db.refresh(doc)
                    if doc.processed:
                        logger.info(f"⏭️  [WORKER] Skipping Doc ID {doc.id}: Already processed")
                        continue
                    if doc.file_path:
                        if "zotero" in doc.file_path.lower():
                            source = "🔗 Zotero"
                        elif "uploads" in doc.file_path.lower():
                            source = "📤 Upload"
                        else:
                            source = "❓ Unknown"
                    else:
                        source = "⚠️ No file"

                    logger.info("")
                    logger.info("=" * 80)
                    logger.info(f"🔨 [WORKER] PROCESSING DOCUMENT")
                    logger.info(f"   → Doc ID: {doc.id}")
                    logger.info(f"   → Filename: {doc.filename}")
                    logger.info(f"   → Source: {source}")
                    logger.info(f"   → Collection: {doc.collection_name}")
                    logger.info("=" * 80)

                    if doc.file_path and os.path.exists(doc.file_path):
                        file_size = os.path.getsize(doc.file_path)
                        logger.info(f"📄 [WORKER] File found:")
                        logger.info(f"   → Path: {doc.file_path}")
                        logger.info(f"   → Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
                        try:
                            import sys
                            if 'main' in sys.modules:
                                from main import currently_processing_doc_id as _
                                import main
                                main.currently_processing_doc_id = doc.id
                                logger.debug(f"🎯 Set document {doc.id} as actively processing")
                        except Exception as e:
                            logger.debug(f"Could not set currently_processing_doc_id: {e}")

                        logger.info(f"🚀 [WORKER] Starting pipeline for Doc ID {doc.id}...")
                        self.pipeline.process_document(doc, doc.file_path, db)

                        try:
                            import sys
                            if 'main' in sys.modules:
                                import main
                                main.currently_processing_doc_id = None
                                logger.debug(f"✅ Cleared actively processing marker")
                        except Exception as e:
                            logger.debug(f"Could not clear currently_processing_doc_id: {e}")

                        db.commit()

                        db.refresh(doc)

                        doc_elapsed = time.time() - doc_start_time
                        logger.info("")
                        logger.info("=" * 80)
                        logger.info(f"✅ [WORKER] DOCUMENT {doc.id} COMPLETE")
                        logger.info(f"   → Filename: {doc.filename}")
                        logger.info(f"   → Chunks: {doc.num_chunks}")
                        logger.info(f"   → Processing time: {doc_elapsed:.1f}s")
                        logger.info("=" * 80)
                        logger.info("")

                        logger.info("🔄 [WORKER] Checking for next pending document...")
                        continue

                    else:
                        logger.warning(
                            f"⚠️  [WORKER] Cannot process Doc ID {doc.id} ({doc.filename}): "
                            f"File not found at {doc.file_path}"
                        )
                        doc.processed = True
                        doc.num_chunks = -1
                        db.commit()
                        logger.info(f"📝 Marked Doc ID {doc.id} as failed (file not found)")
                        continue

                except Exception as exc:
                    try:
                        import sys
                        if 'main' in sys.modules:
                            import main
                            main.currently_processing_doc_id = None
                    except Exception as e:
                        logger.error(str(e))
                        pass

                    logger.error(f"❌ Failed to process Doc ID {current_doc_id} ({current_doc_filename}): {exc}", exc_info=True)

                    try:
                        failed_doc = db.query(Document).filter(Document.id == current_doc_id).first()
                        if failed_doc:
                            failed_doc.processed = True
                            failed_doc.num_chunks = -1
                            db.commit()
                            logger.warning(f"⚠️  Marked Doc ID {current_doc_id} as failed to prevent retry loop")
                    except Exception as mark_exc:
                        logger.error(f"Failed to mark document as failed: {mark_exc}")
                        db.rollback()

                    continue

        except Exception as exc:
            logger.error(f"❌ Critical error in process_documents: {exc}", exc_info=True)
            db.rollback()
        finally:
            logger.debug("🔒 Closing database session")
            db.close()



_worker: Optional[DocumentProcessingWorker] = None


def get_worker() -> DocumentProcessingWorker:
    global _worker
    if _worker is None:
        _worker = DocumentProcessingWorker()
    return _worker