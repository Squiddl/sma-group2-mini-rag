import asyncio
import logging
from typing import Optional

from db.models import Document
from db.session import SessionLocal
from .zotero_service import ZoteroService

logger = logging.getLogger(__name__)


class ZoteroPoller:
    """Async Poller für Zotero - checkt alle 15 Sekunden nach neuen Dokumenten"""

    def __init__(self):
        self.zotero = ZoteroService.get_instance()
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.poll_interval = 15  # Sekunden

    async def start(self):
        """Startet den Polling-Loop"""
        if self.running:
            logger.warning("Zotero poller already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"Zotero poller started (interval: {self.poll_interval}s)")

    async def stop(self):
        """Stoppt den Polling-Loop"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Zotero poller stopped")

    async def _poll_loop(self):
        """Haupt-Polling-Loop"""
        while self.running:
            try:
                await self._check_for_new_documents()
            except Exception as exc:
                logger.error(f"Error in Zotero polling: {exc}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    async def _check_for_new_documents(self):
        """Prüft auf neue Dokumente in Zotero"""
        if not self.zotero.is_enabled():
            return

        # Asyncio-kompatible DB-Operation in executor ausführen
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._sync_check_documents)

    def _sync_check_documents(self):
        """Synchrone Methode zum Prüfen und Hinzufügen neuer Dokumente"""
        db = SessionLocal()
        try:
            # Alle existierenden Dateinamen
            existing_filenames = {
                doc.filename for doc in db.query(Document).all()
            }

            # Alle Zotero Items
            zotero_items = self.zotero.get_all_documents()

            new_count = 0
            for item in zotero_items:
                data = item.get('data', {})

                # Nur Attachments
                if data.get('itemType') != 'attachment':
                    continue

                filename = data.get('filename') or data.get('title', '')

                # Nur PDFs
                if not filename.lower().endswith('.pdf'):
                    continue

                # Prüfen ob neu
                if filename and filename not in existing_filenames:
                    # Neues Dokument zur DB hinzufügen (OHNE Processing)
                    doc = Document(
                        filename=filename,
                        file_path=None,  # Wird beim Processing gesetzt
                        query_enabled=False,  # Erst nach Processing aktivieren
                        processed=False
                    )
                    db.add(doc)
                    new_count += 1

            if new_count > 0:
                db.commit()
                logger.info(f"✓ {new_count} neue Dokumente aus Zotero hinzugefügt (wartend auf Processing)")

        except Exception as exc:
            logger.error(f"Failed to check Zotero documents: {exc}")
            db.rollback()
        finally:
            db.close()


# Globale Poller-Instanz
_poller: Optional[ZoteroPoller] = None


def get_poller() -> ZoteroPoller:
    """Gibt die globale Poller-Instanz zurück"""
    global _poller
    if _poller is None:
        _poller = ZoteroPoller()
    return _poller