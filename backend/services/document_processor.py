import logging
import os
import pickle
from typing import List, Dict, Any, Tuple, Optional

# TODO
from langchain.text_splitter import (  # type: ignore[import-not-found]
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from settings import settings

logger = logging.getLogger(__name__)

HEADING_LEVELS = ["h1", "h2", "h3", "h4", "h5", "h6"]


class DocumentProcessingError(Exception):
    pass


class ParentDocumentLoadError(DocumentProcessingError):
    pass


def _determine_position(chunk_index: int, total_chunks: int) -> str:
    if total_chunks <= 1:
        return "full"

    relative_pos = chunk_index / total_chunks

    if relative_pos < 0.2:
        return "beginning"
    elif relative_pos > 0.8:
        return "end"
    else:
        return "middle"


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


class DocumentProcessor:
    def __init__(self):
        parent_overlap = settings.parent_chunk_overlap or settings.chunk_overlap
        child_overlap = settings.child_chunk_overlap or settings.chunk_overlap

        self.header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "h1"),
                ("##", "h2"),
                ("###", "h3"),
                ("####", "h4"),
                ("#####", "h5"),
                ("######", "h6"),
            ]
        )

        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.parent_chunk_size,
            chunk_overlap=parent_overlap,
            length_function=len,
        )

        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=child_overlap,
            length_function=len,
        )

    def _segment_sections(self, text: str) -> List[Dict[str, str]]:
        documents = self.header_splitter.split_text(text)
        sections: List[Dict[str, str]] = []

        for doc in documents:
            content = doc.page_content.strip()
            if not content:
                continue

            metadata = doc.metadata or {}
            heading_parts = [
                metadata.get(level)
                for level in HEADING_LEVELS
                if metadata.get(level)
            ]
            heading_path = " / ".join(heading_parts) if heading_parts else "Body"

            sections.append({
                "heading": heading_path,
                "content": content,
            })

        if not sections:
            sections.append({"heading": "Body", "content": text.strip()})

        return sections

    def _build_parent_chunks(
            self,
            sections: List[Dict[str, str]]
    ) -> Tuple[List[str], List[str]]:
        parent_docs: List[str] = []
        parent_sections: List[str] = []

        for section in sections:
            content = section.get("content", "").strip()
            heading_path = section.get("heading", "Body")

            if not content:
                continue

            splits = self.parent_splitter.split_text(content)

            for split in splits:
                chunk_text = (
                    f"{heading_path}\n\n{split}".strip()
                    if heading_path != "Body"
                    else split.strip()
                )
                parent_docs.append(chunk_text)
                parent_sections.append(heading_path)

        return parent_docs, parent_sections

    def process_document(
            self,
            doc_id: int,
            text: str,
            pickle_path: str,
            document_name: str = "",
            metadata_chunk: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        sections = self._segment_sections(text)
        parent_docs, parent_sections = self._build_parent_chunks(sections)

        if metadata_chunk:
            parent_docs_with_meta = [metadata_chunk] + parent_docs
        else:
            parent_docs_with_meta = parent_docs

        os.makedirs(os.path.dirname(pickle_path), exist_ok=True)
        with open(pickle_path, 'wb') as f:
            pickle.dump(parent_docs_with_meta, f)  # type: ignore[arg-type]

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
                'chunk_id': -1,
                'is_metadata': True
            })
            parent_offset = 1
            chunk_counter += 1
        else:
            parent_offset = 0

        total_parent_docs = len(parent_docs)

        for parent_id, parent_text in enumerate(parent_docs):
            child_texts = self.child_splitter.split_text(parent_text)

            section = (
                parent_sections[parent_id]
                if parent_id < len(parent_sections)
                else "Body"
            )
            position = _determine_position(parent_id, total_parent_docs)

            for child_text in child_texts:
                chunks.append({
                    'text': child_text,
                    'parent_id': parent_id + parent_offset,
                    'doc_id': doc_id,
                    'document_name': document_name,
                    'section': section,
                    'position': position,
                    'chunk_index': chunk_counter,
                    'is_metadata': False
                })
                chunk_counter += 1

        logger.info(
            f"Processed document {document_name}: "
            f"{len(parent_docs)} parent chunks, {len(chunks)} child chunks"
            f"{' (with metadata)' if metadata_chunk else ''}"
        )

        return chunks
