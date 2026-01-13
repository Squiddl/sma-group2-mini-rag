from fastapi import APIRouter, BackgroundTasks
from typing import Dict
import logging

from .zotero_sync_service import ZoteroSyncService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/zotero", tags=["Zotero"])

zotero_sync_service = None


def init_zotero_router():
    global zotero_sync_service
    zotero_sync_service = ZoteroSyncService()


@router.post("/sync")
async def trigger_sync(background_tasks: BackgroundTasks) -> Dict:
    if not zotero_sync_service:
        init_zotero_router()

    if not zotero_sync_service.zotero.is_enabled():
        return {
            "status": "error",
            "message": "Zotero not configured"
        }

    background_tasks.add_task(zotero_sync_service.sync_all_documents)

    return {
        "status": "started",
        "message": "Zotero sync started in background"
    }


@router.post("/sync/new")
async def sync_new_only(background_tasks: BackgroundTasks) -> Dict:
    if not zotero_sync_service:
        init_zotero_router()

    if not zotero_sync_service.zotero.is_enabled():
        return {
            "status": "error",
            "message": "Zotero not configured"
        }

    background_tasks.add_task(zotero_sync_service.sync_new_documents_only)

    return {
        "status": "started",
        "message": "Syncing new Zotero documents in background"
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