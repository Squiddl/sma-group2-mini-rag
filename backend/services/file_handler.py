import logging
import os
import shutil
from typing import BinaryIO, Dict, Any, Optional

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import VlmPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline
from docling.datamodel import vlm_model_specs
from pypdf import PdfReader
from docx import Document as DocxDocument

from .settings import settings

logger = logging.getLogger(__name__)


class FileProcessingError(Exception):
    pass


class UnsupportedFileTypeError(FileProcessingError):
    pass


class TextExtractionError(FileProcessingError):
    pass


class DoclingVLMConverter:
    _instance: Optional["DoclingVLMConverter"] = None
    _converter = None
    _disabled = False

    @classmethod
    def get_instance(cls) -> Optional["DoclingVLMConverter"]:
        if cls._disabled or not settings.use_docling_parser:
            return None
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if DoclingVLMConverter._disabled:
            return

        try:
            if settings.docling_use_vlm:
                pipeline_options = VlmPipelineOptions(
                    vlm_options=getattr(
                        vlm_model_specs,
                        settings.get_vlm_model_spec()
                    ),
                    generate_page_images=settings.docling_generate_images,
                )

                self._converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_cls=VlmPipeline,
                            pipeline_options=pipeline_options
                        )
                    }
                )
                logger.info("✅ Docling VLM converter initialized")
                logger.info(f"   - Model: {settings.docling_vlm_model}")
                logger.info(f"   - Backend: {settings.docling_vlm_backend}")
                logger.info("   - Tabellen: VLM-basiert (kein TableFormer)")
                logger.info("   - Transformers: neueste Version kompatibel")
            else:
                # Standard Pipeline (falls VLM deaktiviert)
                from docling.datamodel.pipeline_options import PdfPipelineOptions

                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_ocr = False
                pipeline_options.do_table_structure = True
                pipeline_options.do_code_enrichment = True
                pipeline_options.generate_page_images = False
                pipeline_options.generate_picture_images = False

                self._converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(
                            pipeline_options=pipeline_options
                        )
                    }
                )
                logger.info("Docling converter initialized (Standard Pipeline, OCR disabled)")

        except Exception as exc:
            logger.warning(f"⚠️  Docling initialization failed: {exc}")
            logger.info("   Falling back to PyPDF for all conversions")
            DoclingVLMConverter._disabled = True
            self._converter = None

    def convert(self, file_path: str) -> Optional[str]:
        if self._converter is None:
            return None

        try:
            filename = os.path.basename(file_path)
            logger.info(f"🔄 Converting with Docling: {filename}")

            result = self._converter.convert(file_path)
            document = result.document

            if document is None:
                return None

            markdown = document.export_to_markdown()

            if markdown:
                num_tables = len(document.tables)
                logger.info(
                    f"✅ Docling converted {filename}: "
                    f"{len(markdown)} chars, {num_tables} tables"
                )
                return markdown

            return None

        except Exception as exc:
            logger.warning(f"Docling conversion failed for {os.path.basename(file_path)}: {exc}")
            return None


class PDFExtractor:
    """PDF Text-Extraktion mit Docling VLM + PyPDF Fallback"""

    @staticmethod
    def extract_text(file_path: str) -> str:
        filename = os.path.basename(file_path)

        if settings.use_docling_parser:
            logger.info(f"📄 Trying Docling parser for: {filename}")
            docling = DoclingVLMConverter.get_instance()

            if docling:
                docling_text = docling.convert(file_path)
                if docling_text:
                    logger.info(
                        f"✅ Docling successfully parsed: {filename} "
                        f"({len(docling_text)} chars)"
                    )
                    return docling_text
                else:
                    logger.warning(
                        f"⚠️  Docling returned empty, falling back to PyPDF: {filename}"
                    )
            else:
                logger.info(f"ℹ️  Docling unavailable, using PyPDF: {filename}")
        else:
            logger.info(f"ℹ️  Docling disabled in settings, using PyPDF: {filename}")

        try:
            logger.info(f"📖 Using PyPDF parser for: {filename}")
            reader = PdfReader(file_path)
            text_parts = []

            for page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

            extracted = "\n".join(text_parts)
            logger.info(
                f"✅ PyPDF extracted: {filename} "
                f"({len(extracted)} chars from {len(reader.pages)} pages)"
            )
            return extracted

        except Exception as exc:
            logger.error(f"❌ PyPDF extraction failed for {filename}: {exc}")
            raise TextExtractionError(f"Failed to extract text from PDF: {exc}")

    @staticmethod
    def extract_metadata(file_path: str) -> Dict[str, Any]:
        """Extrahiert PDF-Metadaten"""
        try:
            reader = PdfReader(file_path)
            metadata = reader.metadata

            if metadata:
                return {
                    "title": metadata.get("/Title", "") or "",
                    "author": metadata.get("/Author", "") or "",
                    "subject": metadata.get("/Subject", "") or "",
                    "creator": metadata.get("/Creator", "") or "",
                    "producer": metadata.get("/Producer", "") or "",
                    "creation_date": str(metadata.get("/CreationDate", "")) or "",
                    "num_pages": len(reader.pages)
                }
        except Exception as exc:
            logger.warning(f"Failed to extract PDF metadata: {exc}")

        return {"num_pages": 0}

    @staticmethod
    def extract_first_pages(
            file_path: str,
            num_pages: int = 2,
            max_chars: int = 3000
    ) -> str:
        docling = DoclingVLMConverter.get_instance()
        if docling:
            docling_text = docling.convert(file_path)
            if docling_text:
                return docling_text[:max_chars]

        try:
            reader = PdfReader(file_path)
            text_parts = []
            total_chars = 0

            for page in reader.pages[:num_pages]:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
                    total_chars += len(page_text)
                    if total_chars > max_chars:
                        break

            return "".join(text_parts)[:max_chars]
        except Exception as exc:
            logger.warning(f"Failed to extract first pages: {exc}")
            return ""


class DOCXExtractor:
    @staticmethod
    def extract_text(file_path: str) -> str:
        """Extrahiert Text aus DOCX"""
        try:
            doc = DocxDocument(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text]
            return "\n".join(paragraphs)
        except Exception as exc:
            raise TextExtractionError(f"Failed to extract text from DOCX: {exc}")


class PlainTextExtractor:
    @staticmethod
    def extract_text(file_path: str) -> str:
        """Liest Text-Dateien"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as exc:
            raise TextExtractionError(f"Failed to read text file: {exc}")


class FileHandler:
    SUPPORTED_EXTENSIONS = {'.pdf', '.docx', '.txt', '.md'}

    @staticmethod
    def extract_text(file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.pdf':
            return PDFExtractor.extract_text(file_path)
        elif ext == '.docx':
            return DOCXExtractor.extract_text(file_path)
        elif ext in ['.txt', '.md']:
            return PlainTextExtractor.extract_text(file_path)
        else:
            raise UnsupportedFileTypeError(f"Unsupported file type: {ext}")

    @staticmethod
    def extract_pdf_metadata(file_path: str) -> Dict[str, Any]:
        return PDFExtractor.extract_metadata(file_path)

    @staticmethod
    def extract_first_pages_text(
            file_path: str,
            num_pages: int = 2,
            max_chars: int = 3000
    ) -> str:
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.pdf':
            return PDFExtractor.extract_first_pages(file_path, num_pages, max_chars)
        else:
            # Für nicht-PDF: Ganzen Text extrahieren und begrenzen
            full_text = FileHandler.extract_text(file_path)
            return full_text[:max_chars]

    @staticmethod
    def save_upload(file: BinaryIO, filename: str, upload_dir: str) -> str:
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, filename)

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file, buffer)  # type: ignore[arg-type]
            return file_path
        except Exception as exc:
            raise FileProcessingError(f"Failed to save uploaded file: {exc}")

    @staticmethod
    def is_supported(filename: str) -> bool:
        """Prüft ob Dateityp unterstützt wird"""
        ext = os.path.splitext(filename)[1].lower()
        return ext in FileHandler.SUPPORTED_EXTENSIONS

    @staticmethod
    def delete_file(file_path: str) -> bool:
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception as exc:
            logger.warning(f"Failed to delete file {file_path}: {exc}")
            return False