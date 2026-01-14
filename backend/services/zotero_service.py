import logging
import os
from typing import List, Dict, Any, Optional
from pyzotero import zotero

from .settings import settings

logger = logging.getLogger(__name__)


logger.info("=" * 80)
logger.info("ZOTERO SERVICE MODULE LOADED")
logger.info(f"Raw env ZOTERO_LIBRARY_ID: '{os.environ.get('ZOTERO_LIBRARY_ID', 'NOT SET')}'")
logger.info(f"Raw env ZOTERO_API_KEY: '{os.environ.get('ZOTERO_API_KEY', 'NOT SET')[:10]}...'")
logger.info(f"Settings library_id: '{settings.zotero_library_id}'")
logger.info(f"Settings api_key: '{settings.zotero_api_key[:10] if settings.zotero_api_key else 'EMPTY'}...'")
logger.info("=" * 80)

class ZoteroService:
    _instance = None

    @classmethod
    def get_instance(cls) -> "ZoteroService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if not all([settings.zotero_library_id, settings.zotero_library_type, settings.zotero_api_key]):
            logger.warning("Zotero credentials not configured, service disabled")
            self.client = None
            return

        self.client = zotero.Zotero(
            settings.zotero_library_id,
            settings.zotero_library_type,
            settings.zotero_api_key
        )
        logger.info(f"Zotero service initialized (library: {settings.zotero_library_id})")

    def is_enabled(self) -> bool:
        return self.client is not None

    def get_all_documents(self) -> List[Dict[str, Any]]:
        if not self.client:
            return []

        try:
            items = self.client.everything(self.client.top())
            logger.info(f"Retrieved {len(items)} documents from Zotero")
            return items
        except Exception as exc:
            logger.error(f"Failed to retrieve documents from Zotero: {exc}")
            return []

    def get_document_by_key(self, item_key: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None

        try:
            item = self.client.item(item_key)
            return item
        except Exception as exc:
            logger.error(f"Failed to retrieve document {item_key}: {exc}")
            return None

    def upload_document(self, file_path: str, filename: str, parent_id: Optional[str] = None) -> Optional[str]:
        if not self.client or not os.path.exists(file_path):
            return None

        try:
            result = self.client.attachment_simple([file_path], parentid=parent_id)

            if result.get('success'):
                logger.info(f"Uploaded {filename} to Zotero")
                return result['success'][0] if result['success'] else None
            elif result.get('failure'):
                logger.error(f"Failed to upload {filename}: {result['failure']}")
                return None
            else:
                logger.warning(f"Document {filename} unchanged in Zotero")
                return None
        except Exception as exc:
            logger.error(f"Upload failed for {filename}: {exc}")
            return None

    def download_document(self, item_key: str, output_dir: str) -> Optional[str]:
        if not self.client:
            return None

        try:
            item = self.client.item(item_key)
            if not item:
                return None

            file_path = self.client.dump(item_key, path=output_dir)
            logger.info(f"Downloaded document {item_key} to {file_path}")
            return file_path
        except Exception as exc:
            logger.error(f"Download failed for {item_key}: {exc}")
            return None

    def create_bibliography_item(self, metadata: Dict[str, str]) -> Optional[str]:
        if not self.client:
            return None

        try:
            item_type = metadata.get('document_type', 'document').lower()
            if item_type == 'paper':
                item_type = 'journalArticle'
            elif item_type not in ['book', 'thesis', 'report', 'article']:
                item_type = 'document'

            template = self.client.item_template(item_type)

            if metadata.get('title'):
                template['title'] = metadata['title']
            if metadata.get('authors'):
                authors = metadata['authors'].split(',')
                template['creators'] = []
                for author in authors[:5]:
                    parts = author.strip().split(' ', 1)
                    creator = {
                        'creatorType': 'author',
                        'firstName': parts[0] if len(parts) == 2 else '',
                        'lastName': parts[1] if len(parts) == 2 else parts[0]
                    }
                    template['creators'].append(creator)

            if metadata.get('date'):
                template['date'] = metadata['date']
            if metadata.get('abstract'):
                template['abstractNote'] = metadata['abstract']

            resp = self.client.create_items([template])
            if resp.get('success'):
                logger.info(f"Created bibliography item: {metadata.get('title', 'Untitled')}")
                return resp['success']['0']
            return None
        except Exception as exc:
            logger.error(f"Failed to create bibliography item: {exc}")
            return None

    def search_documents(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not self.client:
            return []

        try:
            items = self.client.everything(self.client.top())
            results = []

            for item in items:
                data = item.get('data', {})
                title = data.get('title', '').lower()
                abstract = data.get('abstractNote', '').lower()

                if query.lower() in title or query.lower() in abstract:
                    results.append(item)
                    if len(results) >= limit:
                        break

            logger.info(f"Found {len(results)} matching documents in Zotero")
            return results
        except Exception as exc:
            logger.error(f"Search failed: {exc}")
            return []