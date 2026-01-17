import logging
import os
import pickle
from typing import List, Dict, Any, Optional

from docling_core.transforms.chunker.hierarchical_chunker import ChunkingDocSerializer, ChunkingSerializerProvider
from docling_core.transforms.chunker.hybrid_chunker import HybridChunker
from docling_core.transforms.serializer.markdown import MarkdownTableSerializer
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer
from .settings import settings

logger = logging.getLogger(__name__)


class MarkdownTableSerializerProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc):
        return ChunkingDocSerializer(
            doc=doc,
            table_serializer=MarkdownTableSerializer(),
        )


def load_parent_document(pickle_path: Optional[str], parent_id: int) -> str:
    if not pickle_path:
        return ""

    try:
        with open(pickle_path, 'rb') as f:
            parent_docs = pickle.load(f)

        if parent_id < len(parent_docs):
            return parent_docs[parent_id]
        return ""

    except FileNotFoundError:
        logger.error(f"Parent document file not found: {pickle_path}")
        return ""
    except Exception as exc:
        logger.error(f"Error loading parent document from {pickle_path}: {exc}")
        return ""


def process_document(
        doc_id: int,
        text: str,
        pickle_path: str,
        document_name: str = "",
        metadata_chunk: Optional[str] = None
) -> List[Dict[str, Any]]:
    logger.info(f"📋 [CHUNKER] Starting chunking for document {doc_id}: {document_name}")
    logger.info(f"   → Input text length: {len(text):,} characters")

    parent_size = settings.parent_chunk_size
    parent_overlap = settings.parent_chunk_overlap or settings.chunk_overlap

    logger.info(f"   → Parent chunk config: size={parent_size}, overlap={parent_overlap}")

    parent_docs = []
    for start in range(0, len(text), parent_size - parent_overlap):
        parent_chunk = text[start:start + parent_size]
        if parent_chunk.strip():
            parent_docs.append(parent_chunk)

    logger.info(f"   → Created {len(parent_docs)} parent chunks")

    if metadata_chunk:
        parent_docs_with_meta = [metadata_chunk] + parent_docs
        logger.info(f"   → Added metadata chunk (total parents: {len(parent_docs_with_meta)})")
    else:
        parent_docs_with_meta = parent_docs
        logger.info(f"   → No metadata chunk added")

    os.makedirs(os.path.dirname(pickle_path), exist_ok=True)
    with open(pickle_path, 'wb') as f:
        pickle.dump(parent_docs_with_meta, f)
    logger.info(f"   → Saved parent documents to: {pickle_path}")

    chunks = []
    chunk_counter = 0

    if metadata_chunk:
        chunks.append({
            'text': metadata_chunk,
            'parent_id': 0,
            'doc_id': doc_id,
            'document_name': document_name,
            'section': 'Document Metadata',
            'position': 'metadata',
            'chunk_index': chunk_counter,
            'is_metadata': True
        })
        parent_offset = 1
        chunk_counter += 1
        logger.info(f"   → Created metadata child chunk")
    else:
        parent_offset = 0

    child_size = settings.child_chunk_size or settings.chunk_size
    child_overlap = settings.child_chunk_overlap or settings.chunk_overlap

    logger.info(f"   → Child chunk config: size={child_size}, overlap={child_overlap}")
    logger.info(f"   → Creating child chunks from {len(parent_docs)} parent chunks...")

    for parent_id, parent_text in enumerate(parent_docs):
        for start in range(0, len(parent_text), child_size - child_overlap):
            child_text = parent_text[start:start + child_size]

            if child_text.strip():
                chunks.append({
                    'text': child_text,
                    'parent_id': parent_id + parent_offset,
                    'doc_id': doc_id,
                    'document_name': document_name,
                    'section': 'Body',
                    'position': 'middle',
                    'chunk_index': chunk_counter,
                    'is_metadata': False
                })
                chunk_counter += 1

    # Log summary
    content_chunks = sum(1 for c in chunks if not c.get('is_metadata'))
    meta_chunks = sum(1 for c in chunks if c.get('is_metadata'))
    avg_chunk_len = sum(len(c['text']) for c in chunks) / len(chunks) if chunks else 0

    logger.info(f"✅ [CHUNKER] Chunking complete for document {doc_id}")
    logger.info(f"   → Total chunks: {len(chunks)}")
    logger.info(f"   → Content chunks: {content_chunks}")
    logger.info(f"   → Metadata chunks: {meta_chunks}")
    logger.info(f"   → Avg chunk length: {avg_chunk_len:.0f} chars")
    logger.info(
        f"📊 Processed document {document_name}: "
        f"{len(parent_docs)} parent chunks, {len(chunks)} child chunks"
        f"{' (with metadata)' if metadata_chunk else ''}"
    )

    return chunks


class DocumentProcessor:
    def __init__(self):
        embed_model = settings.embedding_model

        self.tokenizer = HuggingFaceTokenizer(
            tokenizer=AutoTokenizer.from_pretrained(embed_model),
            max_tokens=settings.chunk_size,
        )

        self.chunker = HybridChunker(
            tokenizer=self.tokenizer,
            serializer_provider=MarkdownTableSerializerProvider(),
        )

        logger.info(
            f"DocumentProcessor initialized with HybridChunker "
            f"(max_tokens={settings.chunk_size}, markdown_tables=True)"
        )
