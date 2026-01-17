import logging
from typing import Dict, Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage

from core.llm import create_llm

logger = logging.getLogger(__name__)

METADATA_EXTRACTION_PROMPT = """You are a precise document metadata extractor. Your task is to extract bibliographic information from academic papers and documents.

EXTRACTION RULES:
1. Extract ONLY information that is EXPLICITLY stated in the text
2. Do NOT infer, guess, or use external knowledge
3. If information is not found, write "Not found" for that field
4. For author names, extract ALL authors in the order they appear
5. Preserve original formatting and spelling

FIELDS TO EXTRACT:
- Title: The document's main title
- Author(s): All author names (comma-separated, in order)
- Institution(s): Universities, companies, or organizations affiliated with the work
- Date/Year: Publication or creation date
- Abstract: The document's abstract or summary (if present)
- Keywords: Key topics or terms explicitly listed
- Document Type: paper, thesis, report, article, manual, book, etc.

RESPONSE FORMAT (use exact field names):
Title: [extracted title or "Not found"]
Author(s): [all author names or "Not found"]
Institution(s): [institutions or "Not found"]
Date/Year: [date or "Not found"]
Abstract: [abstract text or "Not found"]
Keywords: [keywords or "Not found"]
Document Type: [type or "Not found"]"""

FIELD_MAPPING = {
    "title:": "title",
    "author(s):": "authors",
    "author:": "authors",
    "institution(s):": "institutions",
    "institution:": "institutions",
    "date/year:": "date",
    "date:": "date",
    "year:": "date",
    "abstract:": "abstract",
    "keywords:": "keywords",
    "document type:": "document_type",
    "type:": "document_type"
}


def _create_empty_metadata(filename: str) -> Dict[str, str]:
    return {
        "title": "Not found",
        "authors": "Not found",
        "institutions": "Not found",
        "date": "Not found",
        "abstract": "Not found",
        "keywords": "Not found",
        "document_type": "Not found",
        "filename": filename
    }


def _parse_metadata_response(response: str, filename: str) -> Dict[str, str]:
    metadata = _create_empty_metadata(filename)
    lines = response.strip().split('\n')
    current_field = None
    current_value: list[str] = []

    for line in lines:
        line_lower = line.lower().strip()

        matched_field = None
        for prefix, field_name in FIELD_MAPPING.items():
            if line_lower.startswith(prefix):
                if current_field and current_value:
                    metadata[current_field] = ' '.join(current_value).strip()

                current_field = field_name
                value_part = line[len(prefix):].strip()
                current_value = [value_part] if value_part else []
                matched_field = field_name
                break

        if not matched_field and current_field and line.strip():
            current_value.append(line.strip())

    if current_field and current_value:
        metadata[current_field] = ' '.join(current_value).strip()

    return metadata


def _create_fallback_metadata(
        filename: str,
        pdf_metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    metadata = _create_empty_metadata(filename)

    if pdf_metadata:
        if pdf_metadata.get("title"):
            metadata["title"] = pdf_metadata["title"]
        if pdf_metadata.get("author"):
            metadata["authors"] = pdf_metadata["author"]

    return metadata


def create_metadata_chunk(metadata: Dict[str, str], document_name: str) -> str:
    parts = [
        "=== DOCUMENT METADATA ===",
        f"Filename: {document_name}",
    ]

    if metadata.get("title") and metadata["title"] != "Not found":
        parts.append(f"Title: {metadata['title']}")

    if metadata.get("authors") and metadata["authors"] != "Not found":
        parts.append(f"Author(s): {metadata['authors']}")
        parts.append(f"This document was written by: {metadata['authors']}")
        parts.append(f"The author of this paper is: {metadata['authors']}")

    if metadata.get("institutions") and metadata["institutions"] != "Not found":
        parts.append(f"Institution(s): {metadata['institutions']}")
        parts.append(f"Affiliation: {metadata['institutions']}")

    if metadata.get("date") and metadata["date"] != "Not found":
        parts.append(f"Date/Year: {metadata['date']}")
        parts.append(f"Published: {metadata['date']}")

    if metadata.get("document_type") and metadata["document_type"] != "Not found":
        parts.append(f"Document Type: {metadata['document_type']}")

    if metadata.get("keywords") and metadata["keywords"] != "Not found":
        parts.append(f"Keywords: {metadata['keywords']}")

    if metadata.get("abstract") and metadata["abstract"] != "Not found":
        parts.append(f"\nAbstract:\n{metadata['abstract']}")

    parts.append("=== END METADATA ===")

    return "\n".join(parts)


class MetadataExtractor:
    def __init__(self, use_llm: bool = True):
        """
        Initialize metadata extractor.

        Args:
            use_llm: If False, skip LLM-based extraction and use only PDF metadata.
                    This speeds up processing significantly (~28s -> <1s).
        """
        self.use_llm = use_llm
        self.llm = create_llm(temperature=0.0, max_tokens=1024) if use_llm else None

        if not use_llm:
            logger.info("⚡ MetadataExtractor: LLM extraction DISABLED (fast mode)")
        else:
            logger.info("🔬 MetadataExtractor: LLM extraction ENABLED (slow but accurate)")

    def extract_metadata_from_text(
            self,
            first_pages_text: str,
            filename: str,
            pdf_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, str]:
        # Fast path: Use PDF metadata only if LLM is disabled
        if not self.use_llm:
            logger.info(f"⚡ [METADATA] Fast extraction (PDF metadata only)")
            return _create_fallback_metadata(filename, pdf_metadata)

        # Slow path: Use LLM for detailed extraction
        logger.info(f"🔬 [METADATA] LLM-based extraction (may take ~30s on CPU)")
        pdf_context = self._build_pdf_context(pdf_metadata)

        messages = [
            SystemMessage(content=METADATA_EXTRACTION_PROMPT),
            HumanMessage(
                content=f"Filename: {filename}{pdf_context}\n\nDocument text (first pages):\n\n{first_pages_text}"
            )
        ]

        try:
            response = self.llm.invoke(messages)
            return _parse_metadata_response(response.content, filename)
        except Exception as exc:
            logger.error(f"Failed to extract metadata via LLM: {exc}")
            return _create_fallback_metadata(filename, pdf_metadata)

    @staticmethod
    def _build_pdf_context(pdf_metadata: Optional[Dict[str, Any]]) -> str:
        if not pdf_metadata:
            return ""

        pdf_parts = []
        if pdf_metadata.get("title"):
            pdf_parts.append(f"PDF Title: {pdf_metadata['title']}")
        if pdf_metadata.get("author"):
            pdf_parts.append(f"PDF Author: {pdf_metadata['author']}")
        if pdf_metadata.get("subject"):
            pdf_parts.append(f"PDF Subject: {pdf_metadata['subject']}")
        if pdf_metadata.get("num_pages"):
            pdf_parts.append(f"Total Pages: {pdf_metadata['num_pages']}")

        if pdf_parts:
            return "\n\nPDF Metadata:\n" + "\n".join(pdf_parts)

        return ""