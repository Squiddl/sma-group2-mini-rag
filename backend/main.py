import asyncio
import json
import logging
import os
import queue
import threading
from typing import List, Dict, AsyncGenerator
from datetime import datetime

import uvicorn

# Configure logging at module level
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from services.document_pipeline import DocumentPipelineService
from models.schemas import (
    ChatCreate, ChatResponse, MessageResponse,
    QueryRequest, DocumentUploadResponse,
    DocumentPreferenceUpdate
)
from persistence.models import Chat, Message, Document
from persistence.session import get_db, SessionLocal
from services.app_lifespan import (
    lifespan,
    get_embedding_service,
    get_vector_store_service,
    get_reranker_service,
    get_rag_service,
    get_metadata_extractor
)
from services.file_handler import FileHandler
from services.settings import settings
from services.zotero_router import router as zotero_router
logger = logging.getLogger(__name__)

# Global processing status tracker
processing_status: Dict[int, Dict] = {}

# Track which document is currently being actively processed by the worker
currently_processing_doc_id: int | None = None


def _get_active_doc_collection_map(db: Session) -> Dict[int, str]:
    vector_store = get_vector_store_service()
    active_documents = db.query(Document).filter(
        Document.processed == True,
        Document.query_enabled == True
    ).all()
    return vector_store.build_collection_map(active_documents)


def _format_sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"



app = FastAPI(
    title="RAG System API with Zotero Auto-Sync",
    description="RAG System API with automatic Zotero document synchronization",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(zotero_router)

@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "ok",
        "message": "RAG System API with Zotero Auto-Sync",
        "version": "1.0.0",
        "features": [
            "Document upload & processing",
            "Multi-query RAG with reranking",
            "Automatic Zotero polling (15s)",
            "Async document processing (30s)",
            "Parent-child chunking strategy",
            "Hybrid search (dense + sparse)"
        ]
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health-Check für alle Services"""
    # Import at endpoint scope to avoid issues during app initialization
    from services.zotero_poller import get_poller
    from services.document_processing_worker import get_worker
    from services.zotero_service import ZoteroService

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


@app.post("/chats", response_model=ChatResponse, tags=["Chats"])
async def create_chat(chat: ChatCreate, db: Session = Depends(get_db)):
    db_chat = Chat(title=chat.title)
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    logger.info(f"💬 Created new chat: {db_chat.id} - '{db_chat.title}'")
    return db_chat


@app.get("/chats", response_model=List[ChatResponse], tags=["Chats"])
async def list_chats(db: Session = Depends(get_db)):
    chats = db.query(Chat).order_by(Chat.updated_at.desc()).all()
    logger.info(f"📋 Listed {len(chats)} chats")
    return chats


@app.get("/chats/{chat_id}", response_model=ChatResponse, tags=["Chats"])
async def get_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        logger.warning(f"⚠️  Chat {chat_id} not found")
        raise HTTPException(status_code=404, detail="Chat not found")
    logger.info(f"📖 Retrieved chat: {chat_id}")
    return chat


@app.delete("/chats/{chat_id}", tags=["Chats"])
async def delete_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    db.delete(chat)
    db.commit()
    logger.info(f"🗑️  Deleted chat: {chat_id}")
    return {"status": "deleted"}


@app.get("/chats/{chat_id}/messages", response_model=List[MessageResponse], tags=["Messages"])
async def get_messages(chat_id: int, db: Session = Depends(get_db)):
    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )
    logger.info(f"💬 Retrieved {len(messages)} messages for chat {chat_id}")
    return messages


@app.get("/documents", response_model=List[DocumentUploadResponse], tags=["Documents"])
async def list_documents(db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    logger.info(f"📚 Listed {len(docs)} documents")

    # Add is_actively_processing flag to each document
    result = []
    for doc in docs:
        doc_dict = {
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
        result.append(doc_dict)

    return result

@app.get("/documents/{doc_id}", response_model=DocumentUploadResponse, tags=["Documents"])
async def get_document(doc_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Add is_actively_processing flag
    doc_dict = {
        "id": document.id,
        "filename": document.filename,
        "file_path": document.file_path,
        "uploaded_at": document.uploaded_at,
        "processed": document.processed,
        "num_chunks": document.num_chunks,
        "collection_name": document.collection_name,
        "query_enabled": document.query_enabled,
        "pickle_path": document.pickle_path,
        "is_actively_processing": currently_processing_doc_id == doc_id
    }

    return doc_dict


@app.post("/documents", response_model=DocumentUploadResponse, tags=["Documents"])
async def upload_document(
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    logger.info(f"📤 Upload request received: {file.filename} ({file.content_type})")

    try:
        logger.info(f"💾 Saving file to disk...")
        file_path = FileHandler.save_upload(file.file, file.filename, settings.upload_dir)
        file_size = os.path.getsize(file_path)
        logger.info(f"✅ File saved: {file_path} ({file_size:,} bytes)")

        logger.info(f"💾 Creating database entry...")
        db_document = Document(
            filename=file.filename,
            file_path=file_path,
            processed=False
        )
        db.add(db_document)
        db.commit()
        db.refresh(db_document)
        logger.info(f"✅ Document entry created in database:")
        logger.info(f"   • ID: {db_document.id}")
        logger.info(f"   • Filename: {db_document.filename}")
        logger.info(f"   • Collection: {db_document.collection_name}")

        # Trigger worker to check for pending documents immediately
        from services.document_processing_worker import get_worker
        worker = get_worker()
        worker.trigger_check()

        logger.info(f"✅ Document {db_document.id} queued for async processing (worker notified)")
        return db_document

    except Exception as exc:
        db.rollback()
        logger.error(f"❌ Upload failed for {file.filename}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing document: {str(exc)}")


@app.get("/documents/{doc_id}/processing-stream", tags=["Documents"])
async def stream_processing_status(doc_id: int, db: Session = Depends(get_db)):
    """Stream real-time processing status updates via Server-Sent Events"""

    # Verify document exists
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    async def event_generator() -> AsyncGenerator:
        try:
            last_status = None
            retry_count = 0
            max_retries = 120  # 2 minutes max (1s interval)

            while retry_count < max_retries:
                # Get current status from global tracker
                current_status = processing_status.get(doc_id, {})

                # Check if document is now processed (from DB)
                db_session = SessionLocal()
                try:
                    doc = db_session.query(Document).filter(Document.id == doc_id).first()
                    if doc and doc.processed:
                        # Send final completion event
                        yield {
                            "event": "complete",
                            "data": json.dumps({
                                "doc_id": doc_id,
                                "stage": "complete",
                                "progress": 1.0,
                                "message": f"Processing complete - {doc.num_chunks} chunks created",
                                "processed": True,
                                "num_chunks": doc.num_chunks,
                                "timestamp": datetime.now().isoformat()
                            })
                        }
                        break
                finally:
                    db_session.close()

                # Send progress update if status changed
                if current_status and current_status != last_status:
                    yield {
                        "event": "progress",
                        "data": json.dumps(current_status)
                    }
                    last_status = current_status.copy()
                elif not current_status:
                    # No status yet, send waiting event
                    yield {
                        "event": "waiting",
                        "data": json.dumps({
                            "doc_id": doc_id,
                            "stage": "queued",
                            "progress": 0.0,
                            "message": "Waiting for worker to start processing...",
                            "timestamp": datetime.now().isoformat()
                        })
                    }

                await asyncio.sleep(1.0)  # 1 second updates
                retry_count += 1

            # Timeout reached
            if retry_count >= max_retries:
                yield {
                    "event": "timeout",
                    "data": json.dumps({
                        "doc_id": doc_id,
                        "message": "Processing timeout - document may still be processing",
                        "timestamp": datetime.now().isoformat()
                    })
                }

        except asyncio.CancelledError:
            logger.info(f"SSE stream cancelled for document {doc_id}")
        except Exception as exc:
            logger.error(f"SSE stream error for document {doc_id}: {exc}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({
                    "doc_id": doc_id,
                    "message": str(exc),
                    "timestamp": datetime.now().isoformat()
                })
            }

    return EventSourceResponse(event_generator())


@app.post("/documents/{doc_id}/reprocess", response_model=DocumentUploadResponse, tags=["Documents"])
async def reprocess_document(
        doc_id: int,
        db: Session = Depends(get_db)
):
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.file_path:
        raise HTTPException(status_code=400, detail="Document file not found on disk")

    logger.info(f"🔄 Reprocessing document {doc_id}: {document.filename}")

    try:
        document.processed = False
        db.commit()

        # Trigger worker to check for pending documents immediately
        from services.document_processing_worker import get_worker
        worker = get_worker()
        worker.trigger_check()

        logger.info(f"✅ Document {doc_id} queued for async reprocessing (worker notified)")

        db.refresh(document)
        return document

    except Exception as exc:
        db.rollback()
        logger.error(f"❌ Reprocessing failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error reprocessing document: {str(exc)}")



@app.patch("/documents/{doc_id}/preferences", response_model=DocumentUploadResponse, tags=["Documents"])
async def update_document_preferences(
        doc_id: int,
        preferences: DocumentPreferenceUpdate,
        db: Session = Depends(get_db)
):
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    old_status = document.query_enabled
    document.query_enabled = preferences.query_enabled
    db.commit()
    db.refresh(document)

    status_text = "enabled" if preferences.query_enabled else "disabled"
    logger.info(f"⚙️  Document {doc_id} query {status_text} (was: {old_status})")

    return document


@app.delete("/documents/{doc_id}", tags=["Documents"])
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(f"🗑️  Deleting document {doc_id}: {document.filename}")

    collection_name = document.collection_name
    pickle_path = document.pickle_path
    file_path = document.file_path
    vector_store = get_vector_store_service()

    try:
        db.delete(document)
        db.commit()
        logger.info(f"   ✅ Deleted from database")
    except Exception as exc:
        db.rollback()
        logger.exception(f"   ❌ Database deletion failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting document from database: {str(exc)}"
        )

    try:
        vector_store.delete_document(collection_name)
        logger.info(f"   ✅ Deleted collection: {collection_name}")
    except Exception as exc:
        logger.warning(f"   ⚠️  Collection deletion failed: {exc}")

    try:
        FileHandler.delete_file(pickle_path)
        logger.info(f"   ✅ Deleted pickle file")
    except Exception as exc:
        logger.warning(f"   ⚠️  Pickle deletion failed: {exc}")

    try:
        FileHandler.delete_file(file_path)
        logger.info(f"   ✅ Deleted source file")
    except Exception as exc:
        logger.warning(f"   ⚠️  File deletion failed: {exc}")

    logger.info(f"✅ Document {doc_id} deletion complete")
    return {"status": "deleted"}


@app.post("/query/stream", tags=["Query"])
async def query_documents_stream(request: QueryRequest, db: Session = Depends(get_db)):
    logger.info(f"🔍 Query received: '{request.query[:100]}...' (chat_id: {request.chat_id})")

    try:
        chat = db.query(Chat).filter(Chat.id == request.chat_id).first()
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        messages = (
            db.query(Message)
            .filter(Message.chat_id == request.chat_id)
            .order_by(Message.created_at)
            .all()
        )
        chat_history: list[dict[str, InstrumentedAttribute[str]]] = [
            {"role": msg.role, "content": msg.content} for msg in messages
        ]
        logger.info(f"   → Chat history: {len(messages)} messages")

        doc_collection_map = _get_active_doc_collection_map(db)
        if not doc_collection_map:
            logger.warning(f"   ⚠️  No active documents for query")
            raise HTTPException(
                status_code=400,
                detail="No active documents selected for querying."
            )

        logger.info(f"   → Active documents: {len(doc_collection_map)}")

        user_message = Message(
            chat_id=request.chat_id,
            content=request.query,
            role="user"
        )
        db.add(user_message)
        db.commit()

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception(f"❌ Query preparation failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing query: {str(exc)}"
        )

    thinking_queue: queue.Queue = queue.Queue()
    retrieval_result = {
        "contexts": [],
        "sources": [],
        "thinking_steps": [],
        "error": None
    }
    retrieval_done = threading.Event()

    def run_retrieval():
        """Background-Thread für Retrieval"""
        try:
            logger.info(f"🔄 Starting retrieval thread...")

            def on_thinking(step):
                thinking_queue.put(("thinking", step))

            rag = get_rag_service()
            contexts, sources, thinking_steps = rag.multi_query_retrieve_and_rerank(
                request.query,
                db,
                doc_collection_map,
                on_thinking=on_thinking
            )

            retrieval_result["contexts"] = contexts
            retrieval_result["sources"] = sources
            retrieval_result["thinking_steps"] = thinking_steps

            logger.info(f"✅ Retrieval complete: {len(contexts)} contexts, {len(sources)} sources")

        except Exception as exception:
            logger.exception(f"❌ Retrieval failed: {exception}")
            retrieval_result["error"] = str(exception)
        finally:
            retrieval_done.set()
            thinking_queue.put(("done", None))

    retrieval_thread = threading.Thread(target=run_retrieval, daemon=True)
    retrieval_thread.start()

    def event_generator():
        accumulated_answer = ""
        try:
            while True:
                try:
                    event_type, data = thinking_queue.get(timeout=0.1)
                    if event_type == "done":
                        break
                    elif event_type == "thinking":
                        yield _format_sse_event({"type": "thinking", "step": data})
                except queue.Empty:
                    if retrieval_done.is_set():
                        while not thinking_queue.empty():
                            try:
                                event_type, data = thinking_queue.get_nowait()
                                if event_type == "thinking":
                                    yield _format_sse_event({"type": "thinking", "step": data})
                            except queue.Empty:
                                break
                        break

            retrieval_thread.join(timeout=60)

            if retrieval_result["error"]:
                raise Exception(retrieval_result["error"])

            contexts = retrieval_result["contexts"]
            sources = retrieval_result["sources"]

            if not contexts:
                logger.warning(f"⚠️  No contexts found for query")
                answer_text = "I couldn't find relevant information in the documents to answer your question."
                assistant_message = Message(
                    chat_id=request.chat_id,
                    content=answer_text,
                    role="assistant"
                )
                db.add(assistant_message)
                db.commit()
                db.refresh(assistant_message)

                yield _format_sse_event({
                    "type": "end",
                    "content": answer_text,
                    "sources": [],
                    "message_id": assistant_message.id
                })
                return

            logger.info(f"🤖 Generating answer with {len(contexts)} contexts...")

            rag = get_rag_service()
            for token in rag.generate_answer_stream(request.query, contexts, chat_history):
                if not token:
                    continue
                accumulated_answer += token
                yield _format_sse_event({"type": "chunk", "content": token})

            assistant_message = Message(
                chat_id=request.chat_id,
                content=accumulated_answer,
                role="assistant"
            )
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            logger.info(f"✅ Answer generated: {len(accumulated_answer)} chars")

            yield _format_sse_event({
                "type": "end",
                "content": accumulated_answer,
                "sources": sources,
                "message_id": assistant_message.id
            })

        except Exception as stream_error:
            db.rollback()
            logger.exception(f"❌ Streaming failed: {stream_error}")
            yield _format_sse_event({"type": "error", "message": "Error processing query"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
