import json
import logging
import os
import queue
import threading
import time
import uvicorn
from typing import List, Dict
from fastapi import FastAPI, Depends, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import InstrumentedAttribute

from db.session import get_db
from db.models import Chat, Message, Document
from models.schemas import (
    ChatCreate, ChatResponse, MessageResponse,
    QueryRequest, DocumentUploadResponse,
    DocumentPreferenceUpdate
)
from services.settings import settings
from services.file_handler import FileHandler
from services.metadata_extractor import create_metadata_chunk

from services.app_lifespan import (
    lifespan,
    get_embedding_service,
    get_vector_store_service,
    get_reranker_service,
    get_rag_service,
    get_metadata_extractor
)
from services.zotero_router import router as zotero_router
from services.document_processor import process_document

logger = logging.getLogger(__name__)


def _get_active_doc_collection_map(db: Session) -> Dict[int, str]:
    """Erstellt Map von aktiven Dokumenten zu Collections"""
    vector_store = get_vector_store_service()
    active_documents = db.query(Document).filter(
        Document.processed == True,
        Document.query_enabled == True
    ).all()
    return vector_store.build_collection_map(active_documents)


def _format_sse_event(payload: dict) -> str:
    """Formatiert Server-Sent Event"""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _extract_metadata_for_document(file_path: str, filename: str) -> str:
    """Extrahiert Metadata aus Dokument"""
    try:
        logger.info(f"📋 [METADATA] Starting metadata extraction for: {filename}")
        start_time = time.time()

        logger.info(f"   → Reading first 2 pages for metadata...")
        first_pages_text = FileHandler.extract_first_pages_text(file_path, num_pages=2)
        logger.info(f"   → Extracted {len(first_pages_text)} characters from first pages")

        pdf_metadata = None
        if filename.lower().endswith('.pdf'):
            logger.info(f"   → Extracting PDF metadata...")
            pdf_metadata = FileHandler.extract_pdf_metadata(file_path)
            if pdf_metadata:
                logger.info(
                    f"   → PDF metadata: {pdf_metadata.get('num_pages', 0)} pages, "
                    f"title='{pdf_metadata.get('title', 'N/A')}'"
                )

        logger.info(f"   → Running LLM-based metadata extraction...")
        metadata_extractor = get_metadata_extractor()
        extracted_metadata = metadata_extractor.extract_metadata_from_text(
            first_pages_text,
            filename,
            pdf_metadata
        )

        metadata_chunk = create_metadata_chunk(extracted_metadata, filename)

        elapsed = time.time() - start_time
        logger.info(f"✅ [METADATA] Extraction complete in {elapsed:.1f}s")
        logger.info(f"   → Title: {extracted_metadata.get('title', 'N/A')}")
        logger.info(f"   → Author: {extracted_metadata.get('authors', 'N/A')}")
        logger.info(f"   → Type: {extracted_metadata.get('document_type', 'N/A')}")

        return metadata_chunk

    except Exception as exc:
        logger.warning(f"⚠️  [METADATA] Extraction failed for {filename}: {exc}")
        return None


def _process_document_pipeline(document: Document, file_path: str) -> Document:
    """
    Vollständige Document-Processing-Pipeline

    Steps:
    1. Text Extraction
    2. Metadata Extraction
    3. Chunking
    4. Vectorization
    5. Database Update
    """
    pipeline_start = time.time()
    vector_store = get_vector_store_service()

    logger.info("=" * 80)
    logger.info(f"📄 [PIPELINE START] Processing document")
    logger.info(f"   • Document ID: {document.id}")
    logger.info(f"   • Filename: {document.filename}")
    logger.info(f"   • Collection: {document.collection_name}")
    logger.info("=" * 80)

    try:
        # STEP 1: Text Extraction
        logger.info(f"🔤 [STEP 1/5] Text Extraction")
        text_start = time.time()

        text = FileHandler.extract_text(file_path)

        text_elapsed = time.time() - text_start
        logger.info(f"✅ [STEP 1/5] Text extracted in {text_elapsed:.1f}s")
        logger.info(f"   → Characters: {len(text):,}")
        logger.info(f"   → Words: ~{len(text.split()):,}")
        logger.info(f"   → Lines: ~{text.count(chr(10)):,}")

        # STEP 2: Metadata Extraction
        logger.info(f"📋 [STEP 2/5] Metadata Extraction")
        metadata_start = time.time()

        metadata_chunk = _extract_metadata_for_document(file_path, document.filename)

        metadata_elapsed = time.time() - metadata_start
        if metadata_chunk:
            logger.info(f"✅ [STEP 2/5] Metadata extracted in {metadata_elapsed:.1f}s")
        else:
            logger.info(f"⚠️  [STEP 2/5] No metadata extracted ({metadata_elapsed:.1f}s)")

        # STEP 3: Document Chunking
        logger.info(f"✂️  [STEP 3/5] Document Chunking")
        chunk_start = time.time()

        pickle_path = os.path.join(settings.pickle_dir, f"doc_{document.id}.pkl")
        collection_name = document.collection_name

        if not collection_name:
            raise ValueError(f"Invalid collection_name for document {document.id}: {collection_name}")

        logger.info(f"   → Chunking with parent-child strategy...")
        logger.info(f"   → Parent size: {settings.parent_chunk_size} tokens")
        logger.info(f"   → Child size: {settings.child_chunk_size or settings.chunk_size} tokens")

        chunks = process_document(
            document.id,
            text,
            pickle_path=pickle_path,
            document_name=document.filename,
            metadata_chunk=metadata_chunk
        )

        chunk_elapsed = time.time() - chunk_start
        logger.info(f"✅ [STEP 3/5] Chunking complete in {chunk_elapsed:.1f}s")
        logger.info(f"   → Total chunks: {len(chunks)}")
        logger.info(f"   → Metadata chunks: {sum(1 for c in chunks if c.get('is_metadata'))}")
        logger.info(f"   → Content chunks: {sum(1 for c in chunks if not c.get('is_metadata'))}")
        logger.info(f"   → Pickle saved: {pickle_path}")

        # STEP 4: Vector Embedding & Storage
        logger.info(f"🔢 [STEP 4/5] Vector Embedding & Storage")
        vector_start = time.time()

        logger.info(f"   → Resetting collection '{collection_name}'...")
        vector_store.reset_collection(collection_name)

        logger.info(f"   → Generating embeddings for {len(chunks)} chunks...")
        logger.info(f"   → Embedding model: {settings.embedding_model}")

        vector_store.add_documents(
            document.id,
            chunks,
            collection_name,
            document_name=document.filename
        )

        vector_elapsed = time.time() - vector_start
        logger.info(f"✅ [STEP 4/5] Vectors stored in {vector_elapsed:.1f}s")
        logger.info(f"   → Collection: {collection_name}")
        logger.info(f"   → Vectors: {len(chunks)} embeddings")

        # STEP 5: Database Update
        logger.info(f"💾 [STEP 5/5] Database Update")

        document.pickle_path = pickle_path
        document.processed = True
        document.num_chunks = len(chunks)

        # Pipeline-Statistik
        pipeline_elapsed = time.time() - pipeline_start

        logger.info("=" * 80)
        logger.info(f"✅ [PIPELINE COMPLETE] Document processing successful!")
        logger.info(f"   • Total time: {pipeline_elapsed:.1f}s")
        logger.info(f"   • Text extraction: {text_elapsed:.1f}s ({text_elapsed / pipeline_elapsed * 100:.0f}%)")
        logger.info(f"   • Metadata: {metadata_elapsed:.1f}s ({metadata_elapsed / pipeline_elapsed * 100:.0f}%)")
        logger.info(f"   • Chunking: {chunk_elapsed:.1f}s ({chunk_elapsed / pipeline_elapsed * 100:.0f}%)")
        logger.info(
            f"   • Vectorization: {vector_elapsed:.1f}s ({vector_elapsed / pipeline_elapsed * 100:.0f}%)"
        )
        logger.info(f"   • Document ID: {document.id}")
        logger.info(f"   • Chunks created: {len(chunks)}")
        logger.info(f"   • Ready for queries: YES")
        logger.info("=" * 80)

        return document

    except Exception as exc:
        pipeline_elapsed = time.time() - pipeline_start
        logger.error("=" * 80)
        logger.error(f"❌ [PIPELINE FAILED] Document processing failed after {pipeline_elapsed:.1f}s")
        logger.error(f"   • Document ID: {document.id}")
        logger.error(f"   • Filename: {document.filename}")
        logger.error(f"   • Error: {type(exc).__name__}: {exc}")
        logger.error("=" * 80)
        logger.exception("Full traceback:")
        raise


# ========================================
# FastAPI Application
# ========================================

app = FastAPI(
    title="RAG System API with Zotero Auto-Sync",
    description="RAG System mit automatischem Zotero-Polling und Document-Processing",
    version="1.0.0",
    lifespan=lifespan  # Kombinierter Lifespan Manager
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Zotero-Router einbinden
app.include_router(zotero_router)


# ========================================
# API Endpoints
# ========================================

@app.get("/", tags=["Health"])
async def root():
    """Root-Endpunkt mit System-Info"""
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


# ========================================
# Chat Endpoints
# ========================================

@app.post("/chats", response_model=ChatResponse, tags=["Chats"])
async def create_chat(chat: ChatCreate, db: Session = Depends(get_db)):
    """Erstellt einen neuen Chat"""
    db_chat = Chat(title=chat.title)
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    logger.info(f"💬 Created new chat: {db_chat.id} - '{db_chat.title}'")
    return db_chat


@app.get("/chats", response_model=List[ChatResponse], tags=["Chats"])
async def list_chats(db: Session = Depends(get_db)):
    """Listet alle Chats"""
    chats = db.query(Chat).order_by(Chat.updated_at.desc()).all()
    logger.info(f"📋 Listed {len(chats)} chats")
    return chats


@app.get("/chats/{chat_id}", response_model=ChatResponse, tags=["Chats"])
async def get_chat(chat_id: int, db: Session = Depends(get_db)):
    """Holt einen spezifischen Chat"""
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        logger.warning(f"⚠️  Chat {chat_id} not found")
        raise HTTPException(status_code=404, detail="Chat not found")
    logger.info(f"📖 Retrieved chat: {chat_id}")
    return chat


@app.delete("/chats/{chat_id}", tags=["Chats"])
async def delete_chat(chat_id: int, db: Session = Depends(get_db)):
    """Löscht einen Chat"""
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    db.delete(chat)
    db.commit()
    logger.info(f"🗑️  Deleted chat: {chat_id}")
    return {"status": "deleted"}


@app.get("/chats/{chat_id}/messages", response_model=List[MessageResponse], tags=["Messages"])
async def get_messages(chat_id: int, db: Session = Depends(get_db)):
    """Holt alle Messages eines Chats"""
    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )
    logger.info(f"💬 Retrieved {len(messages)} messages for chat {chat_id}")
    return messages


# ========================================
# Document Endpoints
# ========================================

@app.post("/documents", response_model=DocumentUploadResponse, tags=["Documents"])
async def upload_document(
        file: UploadFile = File(...),
        db: Session = Depends(get_db)
):
    """Lädt ein Dokument hoch und verarbeitet es"""
    logger.info(f"📤 Upload request received: {file.filename} ({file.content_type})")

    try:
        # File speichern
        logger.info(f"💾 Saving file to disk...")
        file_path = FileHandler.save_upload(file.file, file.filename, settings.upload_dir)
        file_size = os.path.getsize(file_path)
        logger.info(f"✅ File saved: {file_path} ({file_size:,} bytes)")

        # DB Eintrag erstellen
        logger.info(f"💾 Creating database entry...")
        db_document = Document(
            filename=file.filename,
            file_path=file_path,
            processed=False
        )
        db.add(db_document)
        db.commit()
        db.refresh(db_document)

        logger.info(f"✅ Document entry created:")
        logger.info(f"   • ID: {db_document.id}")
        logger.info(f"   • Collection: {db_document.collection_name}")

        # Processing-Pipeline
        db_document = _process_document_pipeline(db_document, file_path)

        db.commit()
        db.refresh(db_document)

        logger.info(f"🎉 Document upload complete: {file.filename} (ID: {db_document.id})")

        return db_document

    except Exception as exc:
        db.rollback()
        logger.error(f"❌ Upload failed for {file.filename}: {type(exc).__name__}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error processing document: {str(exc)}"
        )


@app.get("/documents", response_model=List[DocumentUploadResponse], tags=["Documents"])
async def list_documents(db: Session = Depends(get_db)):
    """Listet alle Dokumente"""
    docs = db.query(Document).order_by(Document.uploaded_at.desc()).all()
    logger.info(f"📚 Listed {len(docs)} documents")
    return docs


@app.post("/documents/{doc_id}/reprocess", response_model=DocumentUploadResponse, tags=["Documents"])
async def reprocess_document(doc_id: int, db: Session = Depends(get_db)):
    """Verarbeitet ein Dokument neu"""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not document.file_path or not os.path.exists(document.file_path):
        raise HTTPException(status_code=400, detail="Document file not found on disk")

    logger.info(f"🔄 Reprocessing document {doc_id}: {document.filename}")

    try:
        document = _process_document_pipeline(document, document.file_path)
        db.commit()
        db.refresh(document)
        logger.info(f"✅ Reprocessing complete for doc {doc_id}")
        return document

    except Exception as exc:
        db.rollback()
        logger.exception(f"❌ Reprocessing failed for document {document.filename}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Error reprocessing document: {str(exc)}"
        )


@app.patch("/documents/{doc_id}/preferences", response_model=DocumentUploadResponse, tags=["Documents"])
async def update_document_preferences(
        doc_id: int,
        preferences: DocumentPreferenceUpdate,
        db: Session = Depends(get_db)
):
    """Aktualisiert Dokument-Präferenzen (query_enabled)"""
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
    """Löscht ein Dokument komplett"""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    logger.info(f"🗑️  Deleting document {doc_id}: {document.filename}")

    collection_name = document.collection_name
    pickle_path = document.pickle_path
    file_path = document.file_path
    vector_store = get_vector_store_service()

    # DB-Eintrag löschen
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

    # Cleanup (Fehler nicht kritisch)
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
    """
    Query-Endpunkt mit Streaming-Response

    Verwendet Multi-Query RAG mit Reranking und Parent-Document-Retrieval
    """
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

        # Aktive Dokumente holen
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
        """Generator für Server-Sent Events"""
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