import os
import unittest
import uuid

from persistence import PostgresRepository
from service import PersistenceService


class PersistenceIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise unittest.SkipTest("DATABASE_URL is required for persistence integration tests")
        cls.repository = PostgresRepository(database_url)
        cls.service = PersistenceService(cls.repository)
        cls.repository.ping()

    def test_session_crud_and_restore_snapshot(self) -> None:
        session_id = f"test-session-{uuid.uuid4().hex}"

        session = self.service.create_session(
            {
                "id": session_id,
                "provider": {
                    "provider": "openai",
                    "model": "gpt-4.1",
                    "providerReady": False,
                },
                "manifest": {
                    "projectId": "project-persistence",
                    "name": "Persistence Demo",
                    "framework": "react",
                    "runtimePackageManager": "pnpm",
                    "workspaceRoot": "workspace",
                    "runtimeEntry": "workspace/preview/index.html",
                    "files": [
                        {
                            "path": "workspace/preview/index.html",
                            "kind": "route",
                            "entry": True,
                        }
                    ],
                },
                "latestDesignIntent": {
                    "objective": "Preserve project state across turns",
                    "screenType": "editor",
                    "layout": {
                        "direction": "mixed",
                        "density": "comfortable",
                        "regions": ["chat", "preview"],
                    },
                    "tone": ["pragmatic"],
                    "styleReferences": [],
                    "lockedConstraints": ["selection-based editing"],
                },
            }
        )

        self.assertEqual(session["id"], session_id)

        selected_element = self.service.create_selected_element(
            session_id,
            {
                "id": f"selection-{uuid.uuid4().hex}",
                "kind": "element",
                "selector": "[data-testid='hero-card']",
                "domPath": ["html", "body", "main", "section[0]"],
                "textSnippet": "Refine this card",
                "bounds": {"x": 24, "y": 96, "width": 320, "height": 180},
                "note": "Preserve the CTA hierarchy.",
                "componentHint": "HeroCard",
                "sourceHint": {"filePath": "workspace/src/App.tsx", "exportName": "HeroCard", "line": 18},
                "capturedAt": "2026-03-19T12:00:00+00:00",
            },
        )

        message = self.service.create_message(
            session_id,
            {
                "id": f"message-{uuid.uuid4().hex}",
                "role": "user",
                "parts": [{"type": "text", "value": "Tighten the spacing in this part."}],
                "selectedElementId": selected_element["id"],
            },
        )

        memory = self.service.upsert_memory(
            session_id,
            {
                "summary": "User is iterating on the hero card spacing and density.",
                "structuredMemory": {
                    "lockedConstraints": ["keep CTA visible"],
                    "styleNotes": ["maintain compact density"],
                    "selectedElementId": selected_element["id"],
                },
            },
        )

        patch_record = self.service.create_patch_record(
            session_id,
            {
                "id": f"patch-{uuid.uuid4().hex}",
                "patchPlan": {
                    "id": f"plan-{uuid.uuid4().hex}",
                    "sessionId": session_id,
                    "strategy": "targeted-update",
                    "target": {
                        "selectedElementId": selected_element["id"],
                        "intentSummary": "Reduce padding on the selected card",
                        "files": ["workspace/src/App.tsx"],
                    },
                    "steps": ["inspect component", "reduce spacing tokens"],
                    "validation": ["runtime renders", "selection remains addressable"],
                },
                "status": "applied",
                "filesChanged": ["workspace/src/App.tsx"],
                "summary": "Reduced card padding and aligned CTA spacing.",
            },
        )

        restored = self.service.restore_session(session_id)

        self.assertEqual(restored["session"]["id"], session_id)
        self.assertEqual(restored["messages"][0]["id"], message["id"])
        self.assertEqual(restored["memory"]["summary"], memory["summary"])
        self.assertEqual(restored["memory"]["structuredMemory"]["selectedElementId"], selected_element["id"])
        self.assertEqual(restored["selectedElements"][0]["id"], selected_element["id"])
        self.assertEqual(restored["selectedElements"][0]["componentHint"], "HeroCard")
        self.assertEqual(restored["patchRecords"][0]["id"], patch_record["id"])


if __name__ == "__main__":
    unittest.main()
