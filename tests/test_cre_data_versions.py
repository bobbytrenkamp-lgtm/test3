import json
from pathlib import Path
import tempfile
import unittest

from test3.cre_data.versions import verification_reports
from test3.warehouse.storage import WarehousePaths


class VerificationVersionTests(unittest.TestCase):
    def _path(self, paths: WarehousePaths, version: str) -> Path:
        path = paths.contained(Path(f"verification/cre/dataset=fixture/version={version}/verification.json"))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def test_active_selection_deserializes_only_latest_report(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            # The retained historical body is corrupt, but its bounded selection
            # header remains readable. It must not take down active-data status.
            self._path(paths, "old").write_text(
                '{"dataset_id":"fixture","created_at":"2025-01-01T00:00:00Z","findings":[',
                encoding="utf-8",
            )
            self._path(paths, "new").write_text(json.dumps({
                "schema_version": "test3-cre-verification/1.0.0",
                "dataset_id": "fixture",
                "source_version": "new",
                "created_at": "2026-01-01T00:00:00Z",
                "findings": [],
                "observations": [],
            }), encoding="utf-8")

            reports = verification_reports(paths)
            self.assertEqual([item["source_version"] for item in reports], ["new"])
            with self.assertRaisesRegex(ValueError, "unreadable CRE verification report"):
                verification_reports(paths, active_only=False)

    def test_active_report_still_fails_closed_when_corrupt(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            self._path(paths, "new").write_text(
                '{"dataset_id":"fixture","created_at":"2026-01-01T00:00:00Z","findings":[',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "unreadable CRE verification report"):
                verification_reports(paths)

    def test_legacy_report_without_header_metadata_remains_supported(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            self._path(paths, "legacy").write_text(json.dumps({
                "observations": [],
                "dataset_id": "fixture",
                "source_version": "legacy",
            }), encoding="utf-8")
            reports = verification_reports(paths)
            self.assertEqual(reports[0]["source_version"], "legacy")

    def test_nested_fields_cannot_impersonate_report_header(self):
        with tempfile.TemporaryDirectory() as root:
            paths = WarehousePaths.from_data_root(root)
            self._path(paths, "legacy").write_text(json.dumps({
                "observations": [{"dataset_id": "impostor", "created_at": "2099-01-01T00:00:00Z"}],
                "dataset_id": "fixture",
                "created_at": "2026-01-01T00:00:00Z",
                "source_version": "legacy",
            }), encoding="utf-8")
            self._path(paths, "older").write_text(json.dumps({
                "dataset_id": "fixture",
                "created_at": "2025-01-01T00:00:00Z",
                "source_version": "older",
                "observations": [],
            }), encoding="utf-8")
            reports = verification_reports(paths)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]["dataset_id"], "fixture")
            self.assertEqual(reports[0]["source_version"], "legacy")


if __name__ == "__main__":
    unittest.main()
