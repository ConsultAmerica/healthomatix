from pathlib import Path

import pytest

from app.storage import (
    LocalDirectoryPrivateStorage,
    StorageUnavailable,
    UnconfiguredPrivateStorage,
)


@pytest.mark.parametrize(
    ("operation", "arguments"),
    [
        ("put", {"tenant_id": "tenant", "document_id": "document", "content": b"synthetic"}),
        ("get", {"tenant_id": "tenant", "document_id": "document", "key": "object-key"}),
        ("delete", {"tenant_id": "tenant", "document_id": "document", "key": "object-key"}),
    ],
)
def test_unconfigured_private_storage_fails_closed(
    operation: str,
    arguments: dict[str, object],
) -> None:
    storage = UnconfiguredPrivateStorage()

    with pytest.raises(StorageUnavailable, match="not configured"):
        getattr(storage, operation)(**arguments)


def test_local_directory_private_storage_round_trip(tmp_path: Path) -> None:
    storage = LocalDirectoryPrivateStorage(tmp_path)
    stored = storage.put(tenant_id="tenant-a", document_id="doc-1", content=b"hello-care")
    assert stored.size_bytes == 10
    assert storage.get(tenant_id="tenant-a", document_id="doc-1", key=stored.key) == b"hello-care"
    storage.delete(tenant_id="tenant-a", document_id="doc-1", key=stored.key)
    with pytest.raises(StorageUnavailable):
        storage.get(tenant_id="tenant-a", document_id="doc-1", key=stored.key)
