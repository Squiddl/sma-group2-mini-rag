import logging
import queue
import threading
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from models.schemas import ChatCreate, ChatResponse, MessageResponse, QueryRequest
from persistence.models import Chat, Message
from persistence.session import get_db
from services.app_lifespan import get_rag_service
from core.state import get_active_doc_collection_map, format_sse_event

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])


@router.post("/chats", response_model=ChatResponse)
async def create_chat(chat: ChatCreate, db: Session = Depends(get_db)):
    db_chat = Chat(title=chat.title)
    db.add(db_chat)
    db.commit()
    db.refresh(db_chat)
    logger.info(f"💬 Created chat: {db_chat.id} - '{db_chat.title}'")
    return db_chat


@router.get("/chats", response_model=List[ChatResponse])
async def list_chats(db: Session = Depends(get_db)):
    chats = db.query(Chat).order_by(Chat.updated_at.desc()).all()
    logger.info(f"📋 Listed {len(chats)} chats")
    return chats


@router.get("/chats/{chat_id}", response_model=ChatResponse)
async def get_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(404, "Chat not found")
    return chat


@router.delete("/chats/{chat_id}")
async def delete_chat(chat_id: int, db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id).first()
    if not chat:
        raise HTTPException(404, "Chat not found")
    db.delete(chat)
    db.commit()
    logger.info(f"🗑️ Deleted chat: {chat_id}")
    return {"status": "deleted"}


@router.get("/chats/{chat_id}/messages", response_model=List[MessageResponse])
async def get_messages(chat_id: int, db: Session = Depends(get_db)):
    messages = (
        db.query(Message)
        .filter(Message.chat_id == chat_id)
        .order_by(Message.created_at)
        .all()
    )
    return messages


@router.post("/query/stream")
async def query_documents_stream(request: QueryRequest, db: Session = Depends(get_db)):
    logger.info(f"🔍 Query: '{request.query[:100]}...' (chat: {request.chat_id})")

    try:
        chat = db.query(Chat).filter(Chat.id == request.chat_id).first()
        if not chat:
            raise HTTPException(404, "Chat not found")

        messages = (
            db.query(Message)
            .filter(Message.chat_id == request.chat_id)
            .order_by(Message.created_at)
            .all()
        )
        chat_history = [{"role": msg.role, "content": msg.content} for msg in messages]

        doc_collection_map = get_active_doc_collection_map(db)
        if not doc_collection_map:
            raise HTTPException(400, "No active documents")

        user_message = Message(chat_id=request.chat_id, content=request.query, role="user")
        db.add(user_message)
        db.commit()

    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(500, f"Query prep failed: {str(exc)}")

    thinking_queue = queue.Queue()
    retrieval_result = {"contexts": [], "sources": [], "error": None}
    retrieval_done = threading.Event()

    def run_retrieval():
        try:
            def on_thinking(step):
                thinking_queue.put(("thinking", step))

            rag = get_rag_service()
            contexts, sources, _ = rag.multi_query_retrieve_and_rerank(
                request.query, db, doc_collection_map, on_thinking=on_thinking
            )
            retrieval_result["contexts"] = contexts
            retrieval_result["sources"] = sources
        except Exception as e:
            logger.exception(f"Retrieval failed: {e}")
            retrieval_result["error"] = str(e)
        finally:
            retrieval_done.set()
            thinking_queue.put(("done", None))

    threading.Thread(target=run_retrieval, daemon=True).start()

    def event_generator():
        accumulated_answer = ""
        try:
            while True:
                try:
                    event_type, data = thinking_queue.get(timeout=0.1)
                    if event_type == "done":
                        break
                    elif event_type == "thinking":
                        yield format_sse_event({"type": "thinking", "step": data})
                except queue.Empty:
                    if retrieval_done.is_set():
                        break

            if retrieval_result["error"]:
                raise Exception(retrieval_result["error"])

            contexts = retrieval_result["contexts"]
            sources = retrieval_result["sources"]

            if not contexts:
                answer_text = "No relevant information found."
                assistant_message = Message(
                    chat_id=request.chat_id, content=answer_text, role="assistant"
                )
                db.add(assistant_message)
                db.commit()
                db.refresh(assistant_message)
                yield format_sse_event({
                    "type": "end",
                    "content": answer_text,
                    "sources": [],
                    "message_id": assistant_message.id
                })
                return

            rag = get_rag_service()
            for token in rag.generate_answer_stream(request.query, contexts, chat_history):
                if token:
                    accumulated_answer += token
                    yield format_sse_event({"type": "chunk", "content": token})

            assistant_message = Message(
                chat_id=request.chat_id, content=accumulated_answer, role="assistant"
            )
            db.add(assistant_message)
            db.commit()
            db.refresh(assistant_message)

            yield format_sse_event({
                "type": "end",
                "content": accumulated_answer,
                "sources": sources,
                "message_id": assistant_message.id
            })

        except Exception as e:
            db.rollback()
            logger.exception(f"Streaming failed: {e}")
            yield format_sse_event({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )