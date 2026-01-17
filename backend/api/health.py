# backend/api/health.py
from fastapi import APIRouter

from services.app_lifespan import (
    get_embedding_service,
    get_vector_store_service,
    get_reranker_service,
    get_rag_service
)

router = APIRouter(tags=["Health"])


@router.get("/")
async def root():
    return {
        "status": "ok",
        "message": "RAG System API",
        "version": "1.0.0"
    }


@router.get("/health")
async def health_check():
    from services.ingrest.poller import get_poller
    from services.ingrest.worker import get_worker
    from services.integrations.zotero import ZoteroService

    poller = get_poller()
    worker = get_worker()
    zotero = ZoteroService.get_instance()

    return {
        "status": "healthy",
        "services": {
            "embedding": get_embedding_service() is not None,
            "vector_store": get_vector_store_service() is not None,
            "reranker": get_reranker_service() is not None,
            "rag": get_rag_service() is not None,
            "zotero_poller": {
                "running": poller.running if poller else False,
                "interval_seconds": poller.poll_interval if poller else 0
            },
            "document_worker": {
                "running": worker.running if worker else False,
                "interval_seconds": worker.check_interval if worker else 0
            },
            "zotero_connection": {
                "enabled": zotero.is_enabled(),
                "configured": zotero.client is not None
            }
        }
    }