from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class StorageUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    version: str
    sha256: str
    size_bytes: int


class PrivateDocumentStorage(Protocol):
    def put(self, *, tenant_id: str, document_id: str, content: bytes) -> StoredObject: ...

    def get(self, *, tenant_id: str, document_id: str, key: str) -> bytes: ...

    def delete(self, *, tenant_id: str, document_id: str, key: str) -> None: ...


class UnconfiguredPrivateStorage:
    def put(self, *, tenant_id: str, document_id: str, content: bytes) -> StoredObject:
        raise StorageUnavailable("Private document storage is not configured.")

    def get(self, *, tenant_id: str, document_id: str, key: str) -> bytes:
        raise StorageUnavailable("Private document storage is not configured.")

    def delete(self, *, tenant_id: str, document_id: str, key: str) -> None:
        raise StorageUnavailable("Private document storage is not configured.")


class LocalDirectoryPrivateStorage:
    """Synthetic/demo private store. Never use as a production PHI backend."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, *, tenant_id: str, document_id: str) -> Path:
        # Tenant and document IDs are UUIDs from the app — keep them path-safe.
        safe_tenant = "".join(ch for ch in tenant_id if ch.isalnum() or ch in "-_")
        safe_document = "".join(ch for ch in document_id if ch.isalnum() or ch in "-_")
        if not safe_tenant or not safe_document:
            raise StorageUnavailable("Invalid storage key.")
        directory = self.root / safe_tenant
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{safe_document}.bin"

    def put(self, *, tenant_id: str, document_id: str, content: bytes) -> StoredObject:
        path = self._path(tenant_id=tenant_id, document_id=document_id)
        digest = hashlib.sha256(content).hexdigest()
        path.write_bytes(content)
        key = f"{tenant_id}/{document_id}"
        return StoredObject(key=key, version="1", sha256=digest, size_bytes=len(content))

    def get(self, *, tenant_id: str, document_id: str, key: str) -> bytes:
        expected = f"{tenant_id}/{document_id}"
        if key != expected:
            raise StorageUnavailable("Document key mismatch.")
        path = self._path(tenant_id=tenant_id, document_id=document_id)
        if not path.is_file():
            raise StorageUnavailable("Document object is unavailable.")
        return path.read_bytes()

    def delete(self, *, tenant_id: str, document_id: str, key: str) -> None:
        expected = f"{tenant_id}/{document_id}"
        if key != expected:
            raise StorageUnavailable("Document key mismatch.")
        path = self._path(tenant_id=tenant_id, document_id=document_id)
        if path.is_file():
            path.unlink()


def build_private_storage(path: str) -> PrivateDocumentStorage:
    configured = path.strip()
    if not configured:
        return UnconfiguredPrivateStorage()
    return LocalDirectoryPrivateStorage(configured)


# Convenience for unit tests that import the module-level helper.
def storage_from_env() -> PrivateDocumentStorage:
    return build_private_storage(os.getenv("DOCUMENT_STORAGE_PATH", ""))
