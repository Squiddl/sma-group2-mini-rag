import asyncio
import json
import logging
from datetime import datetime
from typing import List, AsyncGenerator

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from models.schemas import DocumentUploadResponse, DocumentPreferenceUpdate
from persistence.models import Document
from persistence.session import get_db, SessionLocal
from services.app_lifespan import get_vector_store_service
from services.ingest.file_handler import FileHandler
from core.settings import settings
from core.state import processing_status, currently_processing_doc_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.get("", response_model=List[DocumentUploadResponse])
async def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()

    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "file_path": doc.file_path,
            "uploaded_at": doc.uploaded_at,
            "processed": doc.processed,
            "num_chunks": doc.num_chunks,
            "collection_name": doc.collection_name,
            "query_enabled": doc.query_enabled,
            "pickle_path": doc.pickle_path,
            "is_actively_processing": currently_processing_doc_id == doc.id
        }
        for doc in docs
    ]


@router.get("/{doc_id}", response_model=DocumentUploadResponse)
async def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "file_path": doc.file_path,
        "uploaded_at": doc.uploaded_at,
        "processed": doc.processed,
        "num_chunks": doc.num_chunks,
        "collection_name": doc.collection_name,
        "query_enabled": doc.query_enabled,
        "pickle_path": doc.pickle_path,
        "is_actively_processing": currently_processing_doc_id == doc.id
    }


@router.post("", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    logger.info(f"📤 Upload: {file.filename}")

    try:
        file_path = FileHandler.save_upload(file.file, file.filename, settings.upload_dir)

        db_document = Document(
            filename=file.filename,
            file_path=file_path,
            processed=False
        )
        db.add(db_document)
        db.commit()
        db.refresh(db_document)

        logger.info(f"✅ Document {db_document.id} queued")

        from services.ingest.worker import get_worker
        get_worker().trigger_check()

        return db_document

    except Exception as exc:
        db.rollback()
        logger.error(f"Upload failed: {exc}", exc_info=True)
        raise HTTPException(500, f"Upload failed: {str(exc)}")


@router.get("/{doc_id}/processing-stream")
async def stream_processing_status(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    async def event_generator() -> AsyncGenerator:
        try:
            last_status = None
            for _ in range(120):
                current_status = processing_status.get(doc_id, {})

                db_session = SessionLocal()
                try:
                    doc = db_session.query(Document).filter(Document.id == doc_id).first()
                    if doc and doc.processed:
                        yield {
                            "event": "complete",
                            "data": json.dumps({
                                "doc_id": doc_id,
                                "stage": "complete",
                                "progress": 1.0,
                                "message": f"Complete - {doc.num_chunks} chunks",
                                "processed": True,
                                "num_chunks": doc.num_chunks,
                                "timestamp": datetime.now().isoformat()
                            })
                        }
                        break
                finally:
                    db_session.close()
                if current_status and current_status != last_status:
                    yield {"event": "progress", "data": json.dumps(current_status)}
                    last_status = current_status.copy()
                elif not current_status:
                    yield {
                        "event": "waiting",
                        "data": json.dumps({
                            "doc_id": doc_id,
                            "stage": "queued",
                            "progress": 0.0,
                            "message": "Queued",
                            "timestamp": datetime.now().isoformat()
                        })
                    }

                await asyncio.sleep(1.0)
            else:
                yield {
                    "event": "timeout",
                    "data": json.dumps({"doc_id": doc_id, "message": "Timeout"})
                }

        except Exception as exc:
            logger.error(f"SSE error: {exc}", exc_info=True)
            yield {"event": "error", "data": json.dumps({"message": str(exc)})}

    return EventSourceResponse(event_generator())


@router.post("/{doc_id}/reprocess", response_model=DocumentUploadResponse)
async def reprocess_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.file_path:
        raise HTTPException(400, "File not found")

    doc.processed = False
    db.commit()

    from services.ingest.worker import get_worker
    get_worker().trigger_check()

    db.refresh(doc)
    return doc


@router.patch("/{doc_id}/preferences", response_model=DocumentUploadResponse)
async def update_preferences(
        doc_id: int,
        preferences: DocumentPreferenceUpdate,
        db: Session = Depends(get_db)
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    doc.query_enabled = preferences.query_enabled
    db.commit()
    db.refresh(doc)
    return doc


@router.delete("/{doc_id}")
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    vector_store = get_vector_store_service()
    db.delete(doc)
    db.commit()
    try:
        vector_store.delete_document(doc.collection_name)
    except Exception as exc:
        logger.warning(f"Collection deletion failed: {exc}")

    try:
        FileHandler.delete_file(doc.pickle_path)
        FileHandler.delete_file(doc.file_path)
    except Exception as exc:
        logger.warning(f"File cleanup failed: {exc}")

    return {"status": "deleted"}