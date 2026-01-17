from fastapi import APIRouter, UploadFile, File, HTTPException
from models.schemas import IngestResponse

router = APIRouter()


@router.post("/document", response_model=IngestResponse)
async def ingest_document(file: UploadFile = File(...)):
    # TODO: Inject ingest service
    # TODO: Save file, extract text, chunk, embed, store
    if file.content_type not in ["application/pdf", "text/plain"]:
        raise HTTPException(400, "Unsupported file type")

    return IngestResponse(
        document_id="placeholder-id",
        filename=file.filename,
        chunks_created=0,
        status="pending"
    )


@router.delete("/document/{document_id}")
async def delete_document(document_id: str):
    return {"message": f"Document {document_id} deleted"}