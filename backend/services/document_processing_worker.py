import asyncio
import logging
import os
from typing import Optional

from persistence.models import Document
from persistence.session import SessionLocal
from .document_pipeline import DocumentPipelineService
from .embeddings import EmbeddingService
from .metadata_extractor import MetadataExtractor
from .settings import settings
from .vector_store import VectorStoreService
from .zotero_service import ZoteroService

logger = logging.getLogger(__name__)


class DocumentProcessingWorker:
    def __init__(self):
        self.zotero = ZoteroService.get_instance()

        # Initialize services for pipeline
        self.metadata_extractor = MetadataExtractor()
        self.embedding_service = EmbeddingService.get_instance()
        self.vector_store = VectorStoreService(self.embedding_service)

        # Create pipeline service
        self.pipeline = DocumentPipelineService(
            self.vector_store,
            self.metadata_extractor
        )

        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.check_interval = 30

        # Event for immediate notification (thread-safe)
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
        """
        Trigger an immediate check for pending documents.
        Thread-safe: Can be called from any thread or async context.
        """
        if not self._check_event or not self.running:
            logger.warning("⚠️  Worker not running, cannot trigger check")
            return

        try:
            # Try to get the running event loop
            try:
                loop = asyncio.get_running_loop()
                # We're in async context - schedule directly
                loop.call_soon_threadsafe(self._check_event.set)
                logger.info("📢 Worker notified: immediate document check triggered (async context)")
            except RuntimeError:
                # No running loop - we're in sync context (e.g. FastAPI endpoint)
                # Create a task to set the event in the worker's loop
                def _set_event():
                    try:
                        # Find the worker's event loop and schedule the event
                        import threading
                        for thread in threading.enumerate():
                            if hasattr(thread, '_target') and 'lifespan' in str(thread._target):
                                # This is likely the uvicorn/FastAPI main loop
                                break
                        # Fallback: just set the event directly (thread-safe)
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

        # INITIAL CHECK: Process any existing unprocessed documents on startup
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

            # Wait for either timeout OR immediate trigger
            try:
                logger.debug(f"💤 [WORKER] Sleeping (max {self.check_interval}s or until triggered)...")
                await asyncio.wait_for(self._check_event.wait(), timeout=self.check_interval)
                logger.info("⚡ [WORKER] Immediate check triggered by upload/sync!")
                self._check_event.clear()
            except asyncio.TimeoutError:
                # Normal periodic check
                logger.debug("⏰ [WORKER] Periodic check (timeout reached)")
                pass

    async def _process_pending_documents(self):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.process_documents)

    def process_documents(self):
        """Process all pending documents (both uploaded and Zotero-synced)."""
        import time
        from sqlalchemy import or_
        db = SessionLocal()
        try:
            logger.debug("📊 [WORKER] Querying database for pending documents...")
            # Exclude documents that failed (num_chunks = -1) to avoid infinite retry loops
            pending_docs = db.query(Document).filter(
                Document.processed == False,
                or_(Document.num_chunks == None, Document.num_chunks >= 0)
            ).limit(5).all()

            if not pending_docs:
                logger.debug("✅ [WORKER] No pending documents found")
                # Log total documents for debugging
                total_docs = db.query(Document).count()
                processed_docs = db.query(Document).filter(Document.processed == True).count()
                logger.debug(f"   Total documents in DB: {total_docs}")
                logger.debug(f"   Already processed: {processed_docs}")
                logger.debug(f"   Pending (processed=False): {total_docs - processed_docs}")
                return

            logger.info("=" * 80)
            logger.info(f"📋 [WORKER] Found {len(pending_docs)} pending document(s) to process")
            for doc in pending_docs:
                # Determine source based on file path
                if doc.file_path:
                    if "zotero" in doc.file_path.lower():
                        source = "🔗 Zotero"
                    elif "uploads" in doc.file_path.lower():
                        source = "📤 Upload"
                    else:
                        source = "❓ Unknown"
                else:
                    source = "⚠️ No file"
                logger.info(f"   • Doc ID {doc.id}: {doc.filename} [{source}]")
            logger.info("=" * 80)

            for doc in pending_docs:
                # Capture doc info at start for error reporting (survives session rollback)
                current_doc_id = doc.id
                current_doc_filename = doc.filename
                try:
                    doc_start_time = time.time()

                    # Refresh document from DB to get latest state
                    db.refresh(doc)

                    # Skip if already processed (could have been processed by another worker/process)
                    if doc.processed:
                        logger.info(f"⏭️  [WORKER] Skipping Doc ID {doc.id}: Already processed")
                        continue

                    # Determine source for logging
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
                    logger.info(f"🔨 [WORKER] PROCESSING DOCUMENT {doc.id}")
                    logger.info(f"   → Filename: {doc.filename}")
                    logger.info(f"   → Source: {source}")
                    logger.info(f"   → Collection: {doc.collection_name}")
                    logger.info("=" * 80)

                    # Check if document has a file_path (both uploads and Zotero should have this)
                    if doc.file_path and os.path.exists(doc.file_path):
                        file_size = os.path.getsize(doc.file_path)
                        logger.info(f"📄 [WORKER] File found:")
                        logger.info(f"   → Path: {doc.file_path}")
                        logger.info(f"   → Size: {file_size:,} bytes ({file_size/1024:.1f} KB)")

                        # Mark this document as currently processing
                        try:
                            import sys
                            if 'main' in sys.modules:
                                from main import currently_processing_doc_id as _
                                import main
                                main.currently_processing_doc_id = doc.id
                                logger.debug(f"🎯 Set document {doc.id} as actively processing")
                        except Exception as e:
                            logger.debug(f"Could not set currently_processing_doc_id: {e}")

                        # Process through pipeline
                        logger.info(f"🚀 [WORKER] Starting pipeline for Doc ID {doc.id}...")
                        self.pipeline.process_document(doc, doc.file_path, db)

                        # Clear currently processing marker
                        try:
                            import sys
                            if 'main' in sys.modules:
                                import main
                                main.currently_processing_doc_id = None
                                logger.debug(f"✅ Cleared actively processing marker")
                        except Exception as e:
                            logger.debug(f"Could not clear currently_processing_doc_id: {e}")

                        # Commit after each successful processing
                        db.commit()

                        # Refresh to see the committed changes
                        db.refresh(doc)

                        doc_elapsed = time.time() - doc_start_time
                        logger.info("")
                        logger.info("=" * 80)
                        logger.info(f"✅ [WORKER] DOCUMENT {doc.id} COMPLETE")
                        logger.info(f"   → Filename: {doc.filename}")
                        logger.info(f"   → Chunks: {doc.num_chunks}")
                        logger.info(f"   → Total time: {doc_elapsed:.1f}s")
                        logger.info("=" * 80)
                        logger.info("")

                    else:
                        logger.warning(
                            f"⚠️  [WORKER] Cannot process Doc ID {doc.id} ({doc.filename}): "
                            f"File not found at {doc.file_path}"
                        )
                        # Mark document as failed so it doesn't keep retrying forever
                        doc.processed = False
                        doc.num_chunks = -1  # Use -1 to indicate processing failed
                        db.commit()
                        logger.info(f"📝 Marked Doc ID {doc.id} as failed (file not found)")

                except Exception as exc:
                    # Clear currently processing marker on error
                    try:
                        import sys
                        if 'main' in sys.modules:
                            import main
                            main.currently_processing_doc_id = None
                    except:
                        pass

                    logger.error(f"❌ Failed to process Doc ID {current_doc_id} ({current_doc_filename}): {exc}", exc_info=True)
                    db.rollback()
                    # Continue with next document instead of breaking
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