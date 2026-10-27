from __future__ import annotations

from dataclasses import dataclass
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

