import logging
import time
import os
from typing import Optional, TYPE_CHECKING
from datetime import datetime

from sqlalchemy.orm import Session

from persistence.models import Document
from persistence.session import SessionLocal
from .file_handler import FileHandler
from .metadata import MetadataExtractor, create_metadata_chunk
from .processor import process_document as create_chunks
from core.settings import settings

if TYPE_CHECKING:
    from core.vector_store import VectorStoreService

logger = logging.getLogger(__name__)


class DocumentPipelineService:

    def __init__(
        self,
        vector_store: "VectorStoreService",
        metadata_extractor: MetadataExtractor
    ):
        self.vector_store = vector_store
        self.metadata_extractor = metadata_extractor

    def _report_progress(self, doc_id: int, stage: str, progress: float, message: str):
        try:
            import sys
            if 'main' in sys.modules:
                from main import processing_status
                processing_status[doc_id] = {
                    "doc_id": doc_id,
                    "stage": stage,
                    "progress": progress,
                    "message": message,
                    "timestamp": datetime.now().isoformat()
                }
            logger.info(f"📊 Progress: [{int(progress*100)}%] {stage} - {message}")
        except Exception as e:
            logger.debug(f"Progress reporting skipped: {e}")
            logger.info(f"📊 Progress: [{int(progress*100)}%] {stage} - {message}")

    def process_document(
        self,
        document: Document,
        file_path: str,
        db: Session
    ) -> Document:
        pipeline_start = time.time()
        doc_id = document.id
        doc_filename = document.filename
        doc_collection = document.collection_name

        logger.info("=" * 80)
        logger.info(f"📄 [PIPELINE START] Processing document")
        logger.info(f"   • Document ID: {doc_id}")
        logger.info(f"   • Filename: {doc_filename}")
        logger.info(f"   • Collection: {doc_collection}")
        logger.info("=" * 80)

        try:
            self._report_progress(doc_id, "starting", 0.05, "Starting document processing...")
            logger.info(f"🔤 [STEP 1/5] Text Extraction")
            self._report_progress(doc_id, "extraction", 0.1, "Extracting text from document...")
            text_start = time.time()

            text = FileHandler.extract_text(file_path)

            text_elapsed = time.time() - text_start
            logger.info(f"✅ [STEP 1/5] Text extracted in {text_elapsed:.1f}s")
            logger.info(f"   → Characters: {len(text):,}")
            logger.info(f"   → Words: ~{len(text.split()):,}")
            logger.info(f"   → Lines: ~{text.count(chr(10)):,}")
            self._report_progress(doc_id, "extraction", 0.2, f"Text extracted ({len(text):,} chars)")
            logger.info(f"📋 [STEP 2/5] Metadata Extraction")
            self._report_progress(doc_id, "metadata", 0.25, "Extracting metadata...")
            metadata_start = time.time()

            metadata_chunk = self._extract_metadata(file_path, doc_filename)

            metadata_elapsed = time.time() - metadata_start
            if metadata_chunk:
                logger.info(f"✅ [STEP 2/5] Metadata extracted in {metadata_elapsed:.1f}s")
                self._report_progress(doc_id, "metadata", 0.3, "Metadata extracted")
            else:
                logger.info(f"⚠️  [STEP 2/5] No metadata extracted ({metadata_elapsed:.1f}s)")
                self._report_progress(doc_id, "metadata", 0.3, "No metadata found")
            logger.info(f"✂️  [STEP 3/5] Document Chunking")
            self._report_progress(doc_id, "chunking", 0.35, "Splitting document into chunks...")
            chunk_start = time.time()

            pickle_path = os.path.join(settings.pickle_dir, f"doc_{doc_id}.pkl")
            collection_name = document.collection_name

            if not collection_name:
                raise ValueError(f"Invalid collection_name for document {doc_id}")

            logger.info(f"   → Chunking with parent-child strategy...")
            logger.info(f"   → Parent size: {settings.parent_chunk_size} tokens")
            logger.info(f"   → Child size: {settings.child_chunk_size or settings.chunk_size} tokens")

            chunks = create_chunks(
                doc_id,
                text,
                pickle_path=pickle_path,
                document_name=doc_filename,
                metadata_chunk=metadata_chunk
            )

            chunk_elapsed = time.time() - chunk_start
            logger.info(f"✅ [STEP 3/5] Chunking complete in {chunk_elapsed:.1f}s")
            logger.info(f"   → Total chunks: {len(chunks)}")
            logger.info(f"   → Metadata chunks: {sum(1 for c in chunks if c.get('is_metadata'))}")
            logger.info(f"   → Content chunks: {sum(1 for c in chunks if not c.get('is_metadata'))}")
            self._report_progress(doc_id, "chunking", 0.45, f"Created {len(chunks)} chunks")
            logger.info(f"🔢 [STEP 4/5] Vector Embedding & Storage")
            self._report_progress(doc_id, "embedding", 0.5, "Preparing vector store...")
            vector_start = time.time()

            logger.info(f"   → Resetting collection '{collection_name}'...")
            self.vector_store.reset_collection(collection_name)
            self._report_progress(doc_id, "embedding", 0.55, "Embedding chunks...")
            total_chunks = len(chunks)
            for idx, chunk in enumerate(chunks, 1):
                progress = 0.55 + (0.30 * (idx / total_chunks))
                if idx % 10 == 0 or idx == total_chunks:  # Report every 10 chunks or at end
                    self._report_progress(
                        doc_id,
                        "embedding",
                        progress,
                        f"Embedding chunk {idx}/{total_chunks}"
                    )

            logger.info(f"   → Generating embeddings for {len(chunks)} chunks...")
            self.vector_store.add_documents(
                doc_id,
                chunks,
                collection_name,
                document_name=doc_filename
            )

            vector_elapsed = time.time() - vector_start
            logger.info(f"✅ [STEP 4/5] Vectors stored in {vector_elapsed:.1f}s")
            self._report_progress(doc_id, "storing", 0.9, "Storing vectors complete")

            logger.info(f"💾 [STEP 5/5] Database Update")
            self._report_progress(doc_id, "finalizing", 0.95, "Updating database...")

            try:
                db.refresh(document)
            except Exception as refresh_exc:
                logger.warning(f"Could not refresh document {doc_id}, re-fetching: {refresh_exc}")
                from persistence.models import Document
                document = db.query(Document).filter(Document.id == doc_id).first()
                if not document:
                    raise ValueError(f"Document {doc_id} no longer exists in database")

            document.pickle_path = pickle_path
            document.processed = True
            document.num_chunks = len(chunks)
            db.commit()

            pipeline_elapsed = time.time() - pipeline_start

            # Report completion
            self._report_progress(
                doc_id,
                "complete",
                1.0,
                f"Processing complete - {len(chunks)} chunks created"
            )

            logger.info("=" * 80)
            logger.info(f"✅ [PIPELINE COMPLETE] Document processing successful!")
            logger.info(f"   • Total time: {pipeline_elapsed:.1f}s")
            logger.info(f"   • Chunks created: {len(chunks)}")
            logger.info("=" * 80)

            return document

        except Exception as exc:
            pipeline_elapsed = time.time() - pipeline_start

            # Report error using captured doc_id (survives session rollback)
            self._report_progress(
                doc_id,
                "error",
                0.0,
                f"Processing failed: {str(exc)}"
            )

            logger.error("=" * 80)
            logger.error(f"❌ [PIPELINE FAILED] after {pipeline_elapsed:.1f}s")
            logger.error(f"   • Document ID: {doc_id}")
            logger.error(f"   • Filename: {doc_filename}")
            logger.error(f"   • Error: {type(exc).__name__}: {exc}")
            logger.error("=" * 80)
            logger.exception("Full traceback:")
            db.rollback()
            raise

    def _extract_metadata(self, file_path: str, filename: str) -> Optional[str]:
        try:
            logger.info(f"   → Reading first 2 pages for metadata...")
            first_pages_text = FileHandler.extract_first_pages_text(file_path, num_pages=2)

            pdf_metadata = None
            if filename.lower().endswith('.pdf'):
                pdf_metadata = FileHandler.extract_pdf_metadata(file_path)

            extracted_metadata = self.metadata_extractor.extract_metadata_from_text(
                first_pages_text,
                filename,
                pdf_metadata
            )

            metadata_chunk = create_metadata_chunk(extracted_metadata, filename)

            logger.info(f"   → Title: {extracted_metadata.get('title', 'N/A')}")
            logger.info(f"   → Author: {extracted_metadata.get('authors', 'N/A')}")

            return metadata_chunk

        except Exception as exc:
            logger.warning(f"⚠️  Metadata extraction failed: {exc}")
            return None

