import logging
import os
from typing import Dict

from persistence.models import Document
from persistence.session import SessionLocal

from core.embeddings import EmbeddingService
from services.ingest.metadata import MetadataExtractor
from core.settings import settings
from core.vector_store import VectorStoreService
from .client import ZoteroService

logger = logging.getLogger(__name__)


class ZoteroSyncService:

    def __init__(self):
        self.zotero = ZoteroService.get_instance()
        self.metadata_extractor = MetadataExtractor(use_llm=settings.use_llm_metadata_extraction)
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
        queued_count = 0
        try:
            for item in zotero_items:
                try:
                    result = self._sync_single_item(item, db)

                    if result['status'] == 'queued':
                        results['synced'] += 1
                        queued_count += 1
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

            # Note: Worker trigger is now handled by the router endpoint
            logger.info(f"✅ Sync committed to database: {queued_count} document(s) queued")

        finally:
            db.close()

        logger.info(f"Sync complete: {results['synced']} synced, "
                    f"{results['skipped']} skipped, {results['failed']} failed")

        return results

    # In backend/services/zotero_sync_service.py

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

            logger.info(f"📥 Downloading from Zotero: {filename}")
            file_path = self.zotero.download_document(item_key, download_dir)

            if not file_path or not os.path.exists(file_path):
                return {
                    'status': 'failed',
                    'reason': 'download_failed',
                    'item_key': item_key,
                    'filename': filename
                }

            logger.info(f"✅ Downloaded: {file_path}")

            # Create or update document entry
            if existing:
                doc = existing
                doc.file_path = file_path
                doc.processed = False
                doc.num_chunks = 0  # Reset chunks
                # Note: collection_name is a computed property based on doc.id
            else:
                doc = Document(
                    filename=filename,
                    file_path=file_path,
                    query_enabled=True,
                    processed=False,
                    num_chunks=0
                    # Note: collection_name is a computed property based on doc.id
                )
                db.add(doc)

            db.flush()  # Get doc.id before commit
            logger.info(f"💾 Document entry created/updated: ID={doc.id}, collection={doc.collection_name}")

            db.commit()
            db.refresh(doc)

            return {
                'status': 'queued',
                'item_key': item_key,
                'filename': filename,
                'doc_id': doc.id,
                'file_path': file_path,
                'collection_name': doc.collection_name
            }

        except Exception as exc:
            logger.error(f"Failed to sync {filename}: {exc}", exc_info=True)
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

            queued_count = 0
            for item in new_items:
                try:
                    result = self._sync_single_item(item, db)

                    if result['status'] == 'queued':  # Changed from 'synced'
                        results['synced'] += 1
                        queued_count += 1
                    elif result['status'] == 'skipped':
                        results['skipped'] += 1
                    else:
                        results['failed'] += 1

                    results['details'].append(result)

                except Exception as exc:
                    logger.error(f"Sync failed: {exc}")
                    results['failed'] += 1

            # Note: Worker trigger is now handled by the router endpoint
            logger.info(f"✅ Sync committed to database: {queued_count} document(s) queued")

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