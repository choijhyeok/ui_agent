from typing import Any

from persistence import PostgresRepository


class PersistenceService:
    def __init__(self, repository: PostgresRepository) -> None:
        self.repository = repository

    def health(self) -> dict[str, Any]:
        return {"databaseReady": self.repository.ping()}

    def create_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.create_session(payload)

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self.repository.get_session(session_id)

    def create_message(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.create_message(session_id, payload)

    def list_messages(self, session_id: str) -> list[dict[str, Any]]:
        return self.repository.list_messages(session_id)

    def upsert_memory(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.upsert_memory(session_id, payload)

    def get_memory(self, session_id: str) -> dict[str, Any]:
        return self.repository.get_memory(session_id)

    def create_selected_element(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.create_selected_element(session_id, payload)

    def list_selected_elements(self, session_id: str) -> list[dict[str, Any]]:
        return self.repository.list_selected_elements(session_id)

    def create_patch_record(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.repository.create_patch_record(session_id, payload)

    def list_patch_records(self, session_id: str) -> list[dict[str, Any]]:
        return self.repository.list_patch_records(session_id)

    def restore_session(self, session_id: str) -> dict[str, Any]:
        return self.repository.restore_session(session_id)

    def create_snapshot(self, snapshot_id: str, session_id: str, label: str, archive: bytes, file_list: list[str], patch_record_id: str | None = None) -> None:
        return self.repository.create_snapshot(snapshot_id, session_id, label, archive, file_list, patch_record_id)

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return self.repository.get_snapshot(snapshot_id)

    def list_snapshots(self, session_id: str) -> list[dict[str, Any]]:
        return self.repository.list_snapshots(session_id)
