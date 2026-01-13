import logging
import os
from typing import Dict

from db.models import Document
from db.session import SessionLocal

from .document_processor import process_document
from .embeddings import EmbeddingService
from .file_handler import FileHandler
from .metadata_extractor import MetadataExtractor
from .settings import settings
from .vector_store import VectorStoreService
from .zotero_service import ZoteroService

logger = logging.getLogger(__name__)


class ZoteroSyncService:

    def __init__(self):
        self.zotero = ZoteroService.get_instance()
        self.metadata_extractor = MetadataExtractor()
        self.embedding_service = EmbeddingService.get_instance()
        self.vector_store = VectorStoreService(self.embedding_service)

        self.sync_state_file = os.path.join(settings.data_dir, 'zotero_sync_state.json')
        self.last_sync_items: Dict[str, str] = {}

    def sync_all_documents(self) -> Dict[str, any]:

        if not self.zotero.is_enabled():
            logger.warning("Zotero not configured")
            return {'synced': 0, 'skipped': 0, 'failed': 0}

        logger.info("Starting Zotero sync...")

        zotero_items = self.zotero.get_all_documents()
        logger.info(f"Found {len(zotero_items)} items in Zotero")

        results = {
            'synced': 0,
            'skipped': 0,
            'failed': 0,
            'details': []
        }

        db = SessionLocal()
        try:
            for item in zotero_items:
                try:
                    result = self._sync_single_item(item, db)

                    if result['status'] == 'synced':
                        results['synced'] += 1
                    elif result['status'] == 'skipped':
                        results['skipped'] += 1
                    else:
                        results['failed'] += 1

                    results['details'].append(result)

                except Exception as exc:
                    logger.error(f"Failed to sync item: {exc}")
                    results['failed'] += 1
                    results['details'].append({
                        'status': 'failed',
                        'error': str(exc)
                    })

            db.commit()

        finally:
            db.close()

        logger.info(f"Sync complete: {results['synced']} synced, "
                    f"{results['skipped']} skipped, {results['failed']} failed")

        return results

    def _sync_single_item(self, zotero_item: Dict, db) -> Dict:

        data = zotero_item.get('data', {})
        item_key = data.get('key')
        item_type = data.get('itemType')

        if item_type != 'attachment':
            return {
                'status': 'skipped',
                'reason': 'not_attachment',
                'item_key': item_key
            }

        filename = data.get('filename') or data.get('title', 'unknown.pdf')

        if not filename.lower().endswith('.pdf'):
            return {
                'status': 'skipped',
                'reason': 'not_pdf',
                'item_key': item_key,
                'filename': filename
            }

        existing = db.query(Document).filter(
            Document.filename == filename
        ).first()

        if existing and existing.processed:
            logger.debug(f"Document already synced: {filename}")
            return {
                'status': 'skipped',
                'reason': 'already_exists',
                'item_key': item_key,
                'filename': filename,
                'doc_id': existing.id
            }

        try:
            download_dir = os.path.join(settings.data_dir, 'zotero_downloads')
            os.makedirs(download_dir, exist_ok=True)

            file_path = self.zotero.download_document(item_key, download_dir)

            if not file_path or not os.path.exists(file_path):
                return {
                    'status': 'failed',
                    'reason': 'download_failed',
                    'item_key': item_key,
                    'filename': filename
                }

            logger.info(f"Processing Zotero document: {filename}")

            first_pages = FileHandler.extract_first_pages_text(file_path, num_pages=2)
            pdf_metadata = FileHandler.extract_pdf_metadata(file_path)

            extracted_metadata = self.metadata_extractor.extract_metadata_from_text(
                first_pages,
                filename,
                pdf_metadata
            )

            full_text = FileHandler.extract_text(file_path)

            if existing:
                doc = existing
            else:
                doc = Document(
                    filename=filename,
                    file_path=file_path,
                    query_enabled=True,
                    processed=False
                )
                db.add(doc)
                db.flush()

            pickle_path = os.path.join(settings.pickle_dir, f"doc_{doc.id}.pkl")
            collection_name = f"{settings.qdrant_collection_prefix}{doc.id}"

            metadata_chunk = None
            if extracted_metadata and extracted_metadata.get('title') != 'Not found':
                from .metadata_extractor import create_metadata_chunk
                metadata_chunk = create_metadata_chunk(extracted_metadata, filename)

            chunks = process_document(
                doc.id,
                full_text,
                pickle_path=pickle_path,
                document_name=filename,
                metadata_chunk=metadata_chunk
            )

            self.vector_store.ensure_collection(collection_name)

            texts = [chunk['text'] for chunk in chunks]
            embeddings = self.embedding_service.embed_texts(texts)
            sparse_embeddings = self.embedding_service.embed_sparse_batch(texts)

            self.vector_store.insert_chunks(
                collection_name,
                chunks,
                embeddings,
                sparse_embeddings
            )

            doc.processed = True
            doc.num_chunks = len(chunks)
            doc.pickle_path = pickle_path

            db.commit()

            logger.info(f"✓ Synced from Zotero: {filename} ({len(chunks)} chunks)")

            return {
                'status': 'synced',
                'item_key': item_key,
                'filename': filename,
                'doc_id': doc.id,
                'chunks': len(chunks)
            }

        except Exception as exc:
            logger.error(f"Failed to process {filename}: {exc}")
            db.rollback()
            return {
                'status': 'failed',
                'reason': str(exc),
                'item_key': item_key,
                'filename': filename
            }

    def sync_new_documents_only(self) -> Dict:

        if not self.zotero.is_enabled():
            return {'synced': 0, 'skipped': 0, 'failed': 0}

        logger.info("Checking for new Zotero documents...")

        db = SessionLocal()
        try:
            existing_filenames = {
                doc.filename for doc in db.query(Document).all()
            }

            zotero_items = self.zotero.get_all_documents()
            new_items = []

            for item in zotero_items:
                data = item.get('data', {})
                if data.get('itemType') != 'attachment':
                    continue

                filename = data.get('filename') or data.get('title', '')
                if filename and filename not in existing_filenames:
                    new_items.append(item)

            logger.info(f"Found {len(new_items)} new documents in Zotero")

            results = {
                'synced': 0,
                'skipped': 0,
                'failed': 0,
                'details': []
            }

            for item in new_items:
                try:
                    result = self._sync_single_item(item, db)

                    if result['status'] == 'synced':
                        results['synced'] += 1
                    elif result['status'] == 'skipped':
                        results['skipped'] += 1
                    else:
                        results['failed'] += 1

                    results['details'].append(result)

                except Exception as exc:
                    logger.error(f"Sync failed: {exc}")
                    results['failed'] += 1

            return results

        finally:
            db.close()


def run_zotero_sync():
    sync_service = ZoteroSyncService()
    results = sync_service.sync_all_documents()

    print("\n" + "=" * 60)
    print("ZOTERO SYNC RESULTS")
    print("=" * 60)
    print(f"✓ Synced:  {results['synced']}")
    print(f"⊘ Skipped: {results['skipped']}")
    print(f"✗ Failed:  {results['failed']}")
    print("=" * 60 + "\n")

    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    run_zotero_sync()