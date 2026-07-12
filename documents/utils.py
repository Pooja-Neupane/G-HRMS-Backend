import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class UploadedFileMetadata:
    original_file_name:str
    content_type:str
    file_size_bytes:int
    file_hash_sha256:str

def document_version_upload_path(instance,filename):
    extension = Path(filename).suffix.lower()
    generated_name = f"{uuid4().hex}{extension}"

    return (
        f"employee-documents/"
        f"{instance.document_id}/"
        f"{generated_name}"
    )


def inspect_uploaded_file(uploaded_file):
    """calculate trusted metadata by reading the uploaded content."""
    hasher = hashlib.sha256()
    file_size_bytes = 0

    for chunk in uploaded_file.chunks():
        hasher.update(chunk)
        file_size_bytes += len(chunk)

    uploaded_file.seek(0)

    return UploadedFileMetadata(
        original_file_name=Path(uploaded_file.name).name,
        content_type=(
            getattr(uploaded_file,"content_type",None)
            or "application/octet-stream"
        ),
        file_size_bytes=file_size_bytes,
        file_hash_sha256=hasher.hexdigest(),
    )