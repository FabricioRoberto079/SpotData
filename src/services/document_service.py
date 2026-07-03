import logging

from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.data.postgres_client import get_session
from src.enums.content_type import ContentType
from src.enums.document_category import DocumentCategory
from src.enums.vectorization_status import VectorizationStatus
from src.exceptions import NotFoundError, ValidationError
from src.interfaces.document_service import IDocumentService
from src.interfaces.qa_cache import IQaCache
from src.interfaces.text_extractor import ITextExtractor
from src.interfaces.vector_index_service import IVectorIndexService
from src.models.category import Category
from src.models.document_version import DocumentVersion
from src.models.knowledge_document import KnowledgeDocument
from src.services.qa_cache import get_qa_cache
from src.services.text_extractor import get_text_extractor
from src.services.vector_index_service import get_vector_index_service

logger = logging.getLogger(__name__)


class DocumentService(IDocumentService):
    def __init__(
        self,
        session: Session,
        text_extractor: ITextExtractor,
        vector_index: IVectorIndexService,
        cache: IQaCache,
    ) -> None:
        self._session = session
        self._text_extractor = text_extractor
        self._vector_index = vector_index
        self._cache = cache

    def _next_version_number(self, document_id: str) -> int:
        stmt = select(DocumentVersion.version_number).where(
            DocumentVersion.document_id == document_id
        )
        existing = self._session.execute(stmt).scalars().all()
        return (max(existing) + 1) if existing else 1

    def _demote_previous_versions(self, document_id: str) -> None:
        self._vector_index.demote_latest(document_id)

    def _load(self, document_id: str) -> KnowledgeDocument:
        """Load a document or raise NotFoundError."""
        doc = self._session.get(KnowledgeDocument, document_id)
        if doc is None:
            raise NotFoundError(f"Document not found: {document_id}")
        return doc

    def _assert_category_exists(self, category_id: str) -> None:
        """Validate a target category for upload: it must exist. Every user may use
        any existing category."""
        if self._session.get(Category, category_id) is None:
            raise ValidationError(f"Unknown category: {category_id}")

    @staticmethod
    def _serialize_document(doc: KnowledgeDocument) -> dict:
        latest = (
            max(doc.versions, key=lambda v: v.version_number) if doc.versions else None
        )
        return {
            "id": doc.id,
            "file_name": doc.file_name,
            "category": doc.category,
            "category_id": doc.category_id,
            "uploaded_by": doc.uploaded_by,
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
            "versions_count": len(doc.versions),
            "latest_version": latest.version_number if latest else None,
            "latest_status": latest.vectorization_status if latest else None,
        }

    def create_document(
        self,
        file_name: str,
        category: DocumentCategory,
        uploaded_by: str | None = None,
        category_id: str | None = None,
    ) -> str:
        try:
            doc = KnowledgeDocument(
                file_name=file_name,
                category=category.value,
                category_id=category_id,
                uploaded_by=uploaded_by,
            )
            self._session.add(doc)
            self._session.commit()
            self._session.refresh(doc)
            return doc.id
        except Exception:
            self._session.rollback()
            raise

    def add_version(
        self,
        document_id: str,
        file_data: bytes,
        content_type: ContentType,
    ) -> dict:
        text = self._text_extractor.extract_from_bytes(file_data, content_type)
        if not text:
            raise ValidationError("No text extracted from uploaded content.")

        pages = self._text_extractor.extract_pages_from_bytes(file_data, content_type)
        if pages:
            chunks, embeddings, pages_per_chunk = self._vector_index.prepare_paged(
                pages
            )
        else:
            chunks, embeddings = self._vector_index.prepare(text)
            pages_per_chunk = None

        try:
            doc = self._session.get(KnowledgeDocument, document_id)
            if doc is None:
                raise NotFoundError(f"Document not found: {document_id}")

            version_number = self._next_version_number(document_id)
            version = DocumentVersion(
                document_id=document_id,
                version_number=version_number,
                content_type=content_type.value,
                file_data=file_data,
                extracted_text=text,
                vectorization_status=VectorizationStatus.COMPLETED.value,
            )
            self._session.add(version)
            self._session.flush()

            if version_number > 1:
                self._demote_previous_versions(document_id)
            chunk_count = self._vector_index.commit(
                document_id=document_id,
                version_number=version_number,
                file_name=doc.file_name,
                content_type=content_type.value,
                chunks=chunks,
                embeddings=embeddings,
                pages_per_chunk=pages_per_chunk,
                category_id=doc.category_id,
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        self._cache.invalidate_category(doc.category_id)
        logger.info(
            "indexed document=%s version=%d chunks=%d",
            document_id,
            version_number,
            chunk_count,
        )
        return {
            "id": version.id,
            "document_id": document_id,
            "version_number": version_number,
            "vectorization_status": version.vectorization_status,
            "content_type": version.content_type,
            "chunk_count": chunk_count,
        }

    def _find_existing_document(
        self, file_name: str, uploaded_by: str | None
    ) -> KnowledgeDocument | None:
        stmt = select(KnowledgeDocument).where(
            KnowledgeDocument.file_name == file_name,
            KnowledgeDocument.uploaded_by.is_(uploaded_by)
            if uploaded_by is None
            else KnowledgeDocument.uploaded_by == uploaded_by,
        )
        return self._session.execute(stmt).scalars().first()

    def upload_new_document(
        self,
        file_data: bytes,
        content_type: ContentType,
        file_name: str,
        category: DocumentCategory,
        uploaded_by: str | None = None,
        category_id: str | None = None,
    ) -> dict:
        # No category means the document is shared ("de todos"); only validate
        # when one was actually chosen.
        if category_id is not None:
            self._assert_category_exists(category_id)

        # Extraction/embedding happen inside add_version; calling them here just to
        # validate would double the cost (the embedding API runs twice).
        existing = self._find_existing_document(file_name, uploaded_by)
        if existing is not None:
            version = self.add_version(existing.id, file_data, content_type)
            return {
                "document_id": existing.id,
                "file_name": existing.file_name,
                "category": existing.category,
                "created": False,
                "version": version,
            }

        document_id = self.create_document(
            file_name, category, uploaded_by, category_id=category_id
        )
        try:
            version = self.add_version(document_id, file_data, content_type)
        except Exception:
            try:
                doc = self._session.get(KnowledgeDocument, document_id)
                if doc is not None:
                    self._session.delete(doc)
                    self._session.commit()
            except Exception:
                self._session.rollback()
                logger.exception(
                    "failed to clean up orphan document=%s after indexing failure",
                    document_id,
                )
            raise
        return {
            "document_id": document_id,
            "file_name": file_name,
            "category": category.value,
            "created": True,
            "version": version,
        }

    def get_version_file(
        self,
        document_id: str,
        version_number: int | None = None,
    ) -> tuple[bytes, str, str, int]:
        doc = self._load(document_id)
        if not doc.versions:
            raise NotFoundError(f"Document {document_id} has no versions.")

        version: DocumentVersion
        if version_number is None:
            version = max(doc.versions, key=lambda v: v.version_number)
        else:
            found = next(
                (v for v in doc.versions if v.version_number == version_number), None
            )
            if found is None:
                raise NotFoundError(
                    f"Version {version_number} does not exist for document {document_id}."
                )
            version = found
        return (
            version.file_data,
            version.content_type,
            doc.file_name,
            version.version_number,
        )

    def list_documents(
        self,
        category_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        filters = []
        if category_id is not None:
            filters.append(KnowledgeDocument.category_id == category_id)

        count_stmt = select(func.count()).select_from(KnowledgeDocument)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = self._session.execute(count_stmt).scalar_one()

        page_stmt = select(KnowledgeDocument).options(
            selectinload(KnowledgeDocument.versions)
        )
        if filters:
            page_stmt = page_stmt.where(*filters)
        page_stmt = (
            page_stmt.order_by(KnowledgeDocument.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        docs = self._session.execute(page_stmt).scalars().all()
        return {
            "items": [self._serialize_document(d) for d in docs],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_document(self, document_id: str) -> dict:
        doc = self._load(document_id)
        return self._serialize_document(doc)

    def delete_document(self, document_id: str) -> None:
        try:
            doc = self._load(document_id)
            category_id = doc.category_id
            self._vector_index.purge_document(document_id)
            self._session.delete(doc)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._cache.invalidate_category(category_id)


def get_document_service(
    session: Session = Depends(get_session),
    text_extractor: ITextExtractor = Depends(get_text_extractor),
    vector_index: IVectorIndexService = Depends(get_vector_index_service),
    cache: IQaCache = Depends(get_qa_cache),
) -> IDocumentService:
    return DocumentService(session, text_extractor, vector_index, cache)
