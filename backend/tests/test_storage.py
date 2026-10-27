import pytest

from app.storage import StorageUnavailable, UnconfiguredPrivateStorage


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
