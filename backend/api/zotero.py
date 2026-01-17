from fastapi import APIRouter
from typing import Dict
import logging

from services.integrations.zotero.sync import ZoteroSyncService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/zotero", tags=["Zotero"])

zotero_sync_service = None


def init_zotero_router():
    global zotero_sync_service
    zotero_sync_service = ZoteroSyncService()


@router.post("/sync")
async def trigger_sync() -> Dict:
    """Synchronously sync all Zotero documents and trigger worker"""
    if not zotero_sync_service:
        init_zotero_router()

    if not zotero_sync_service.zotero.is_enabled():
        return {
            "status": "error",
            "message": "Zotero not configured"
        }

    logger.info("🔄 Starting synchronous Zotero sync (all documents)...")
    result = zotero_sync_service.sync_all_documents()

    # Trigger worker immediately after sync
    if result.get('synced', 0) > 0:
        try:
            from services.ingest.worker import get_worker
            worker = get_worker()
            worker.trigger_check()
            logger.info(f"📢 Worker triggered after sync: {result['synced']} document(s) ready")
        except Exception as exc:
            logger.warning(f"Failed to trigger worker: {exc}")

    return {
        "status": "completed",
        "message": f"Sync completed: {result['synced']} synced, {result['skipped']} skipped, {result['failed']} failed",
        "details": result
    }


@router.post("/sync/new")
async def sync_new_only() -> Dict:
    """Synchronously sync only new Zotero documents and trigger worker"""
    if not zotero_sync_service:
        init_zotero_router()

    if not zotero_sync_service.zotero.is_enabled():
        return {
            "status": "error",
            "message": "Zotero not configured"
        }

    logger.info("🔄 Starting synchronous Zotero sync (new documents only)...")
    result = zotero_sync_service.sync_new_documents_only()

    if result.get('synced', 0) > 0:
        try:
            from services.ingest.worker import get_worker
            worker = get_worker()
            worker.trigger_check()
            logger.info(f"📢 Worker triggered after sync: {result['synced']} new document(s) ready")
        except Exception as exc:
            logger.warning(f"Failed to trigger worker: {exc}")

    return {
        "status": "completed",
        "message": f"Sync completed: {result['synced']} synced, {result['skipped']} skipped, {result['failed']} failed",
        "details": result
    }


@router.get("/status")
async def get_sync_status() -> Dict:
    if not zotero_sync_service:
        init_zotero_router()

    enabled = zotero_sync_service.zotero.is_enabled()

    if not enabled:
        return {
            "enabled": False,
            "message": "Zotero not configured"
        }

    try:
        items = zotero_sync_service.zotero.get_all_documents()

        pdf_count = sum(
            1 for item in items
            if item.get('data', {}).get('itemType') == 'attachment'
        )

        return {
            "enabled": True,
            "total_items": len(items),
            "pdf_attachments": pdf_count
        }
    except Exception as exc:
        logger.error(f"Failed to get Zotero status: {exc}")
        return {
            "enabled": True,
            "error": str(exc)
        }