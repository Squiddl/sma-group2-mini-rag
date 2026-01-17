from __future__ import annotations

import json
from typing import Dict
from sqlalchemy.orm import Session
from persistence.models import Document

processing_status: Dict[int, Dict] = {}

currently_processing_doc_id: int | None = None


def get_active_doc_collection_map(db: Session) -> Dict[int, str]:
    from services.app_lifespan import get_vector_store_service

    vector_store = get_vector_store_service()
    active_documents = db.query(Document).filter(
        Document.processed == True,
        Document.query_enabled == True
    ).all()

    return vector_store.build_collection_map(active_documents)


def format_sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"