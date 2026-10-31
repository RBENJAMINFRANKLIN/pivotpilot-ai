"""Protected file storage for original resume files. Files are never served publicly;
only the owner's API requests can read them back."""

from pathlib import Path

import httpx

from app.config import get_settings


class Storage:
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage(Storage):
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:
            raise ValueError("invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class SupabaseStorage(Storage):
    """Private bucket accessed with the service-role key from the backend only."""

    def __init__(self, url: str, service_key: str, bucket: str) -> None:
        self.base = f"{url.rstrip('/')}/storage/v1/object/{bucket}"
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        r = httpx.post(f"{self.base}/{key}", content=data, headers={**self.headers, "Content-Type": content_type, "x-upsert": "true"}, timeout=30)
        r.raise_for_status()

    def get(self, key: str) -> bytes:
        r = httpx.get(f"{self.base}/{key}", headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.content

    def delete(self, key: str) -> None:
        # Supabase bulk-delete endpoint: DELETE /object/{bucket} with the keys to remove.
        httpx.request("DELETE", self.base, json={"prefixes": [key]}, headers=self.headers, timeout=30).raise_for_status()


def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "supabase":
        return SupabaseStorage(s.supabase_url, s.supabase_service_role_key, s.supabase_storage_bucket)
    return LocalStorage(s.storage_local_dir)
