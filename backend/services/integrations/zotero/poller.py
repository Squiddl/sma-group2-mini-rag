import asyncio
import logging
from typing import Optional

from persistence.models import Document
from persistence.session import SessionLocal
from .client import ZoteroService

logger = logging.getLogger(__name__)


class ZoteroPoller:
    def __init__(self, auto_sync: bool = True):
        self.zotero = ZoteroService.get_instance()
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.poll_interval = 60
        self.auto_sync = auto_sync

        if self.auto_sync:
            logger.info("Zotero Poller: Auto-sync ENABLED (new docs will be downloaded automatically)")
        else:
            logger.info("Zotero Poller: Auto-sync DISABLED (manual sync required)")

    async def start(self):
        if self.running:
            logger.warning("Zotero poller already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"Zotero poller started (interval: {self.poll_interval}s)")

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Zotero poller stopped")

    async def _poll_loop(self):
        while self.running:
            try:
                await self._check_for_new_documents()
            except Exception as exc:
                logger.error(f"Error in Zotero polling: {exc}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _check_for_new_documents(self):
        if not self.zotero.is_enabled():
            return

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_check_documents)

    def _sync_check_documents(self):
        db = SessionLocal()
        try:
            existing_filenames = {
                doc.filename for doc in db.query(Document).all()
            }

            zotero_items = self.zotero.get_all_documents()

            new_count = 0
            for item in zotero_items:
                data = item.get('data', {})

                if data.get('itemType') != 'attachment':
                    continue

                filename = data.get('filename') or data.get('title', '')

                if not filename.lower().endswith('.pdf'):
                    continue

                if filename and filename not in existing_filenames:
                    logger.info(f"📋 New document found in Zotero: {filename}")
                    new_count += 1

            if new_count > 0:
                logger.info(f"✓ {new_count} new document(s) found in Zotero")

                if self.auto_sync:
                    logger.info(f"🔄 Auto-syncing {new_count} document(s)...")

                    try:
                        from .sync import ZoteroSyncService
                        sync_service = ZoteroSyncService()

                        result = sync_service.sync_new_documents_only

                        synced = result.get('synced', 0)
                        failed = result.get('failed', 0)
                        skipped = result.get('skipped', 0)

                        logger.info(f"✅ Auto-sync complete: {synced} queued, {skipped} skipped, {failed} failed")

                        if synced > 0:
                            logger.info(f"📢 {synced} document(s) queued for processing")
                            try:
                                from services.ingest.worker import get_worker
                                worker = get_worker()
                                worker.trigger_check()
                                logger.info(f"📢 Worker triggered: {synced} document(s) ready for processing")
                            except Exception as worker_exc:
                                logger.warning(f"Failed to trigger worker: {worker_exc}")

                    except Exception as sync_exc:
                        logger.error(f"❌ Auto-sync failed: {sync_exc}", exc_info=True)
                else:
                    logger.info(f"ℹ️  Use /zotero/sync/new to download (auto-sync disabled)")

        except Exception as exc:
            logger.error(f"Failed to check Zotero documents: {exc}")
            db.rollback()
        finally:
            db.close()


_poller: Optional[ZoteroPoller] = None


def get_poller() -> ZoteroPoller:
    global _poller
    if _poller is None:
        _poller = ZoteroPoller()
    return _poller