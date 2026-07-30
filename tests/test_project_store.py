import csv
import json
import tempfile
import unittest
from pathlib import Path

from surgui.project_store import (
    Annotation,
    ProjectStore,
    TemplateItem,
    format_timecode,
    interval_coverage_ms,
    parse_timecode,
    representative_frame_time,
)


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.media = self.root / "case.mp4"
        self.media.write_bytes(b"minimal video fingerprint")
        self.templates = [
            TemplateItem(
                id="phase_1",
                label="Phase A",
                kind="interval",
                category="phase",
            ),
            TemplateItem(
                id="task_1",
                label="Task A",
                kind="interval",
                category="task",
            ),
            TemplateItem(
                id="quality_1",
                label="Quality",
                kind="rating",
                category="assessment",
                score_options=[0, 1, 2],
            ),
            TemplateItem(
                id="alert_1",
                label="Alert",
                kind="point",
                category="assessment",
            ),
        ]

    def tearDown(self):
        self.temporary.cleanup()

    def test_timecode_round_trip(self):
        self.assertEqual(parse_timecode("1:02:03.4"), 3_723_400)
        self.assertEqual(parse_timecode("02:03"), 123_000)
        self.assertEqual(format_timecode(3_723_400), "01:02:03.400")
        with self.assertRaises(ValueError):
            parse_timecode("not a timestamp")

    def test_persist_export_and_undo(self):
        project = self.root / "project.surgui.json"
        store = ProjectStore.create(project, self.media, self.templates, duration_ms=12_000, fps=25)
        interval = store.add_annotation(self.templates[0], 1_000, 3_500, note="first pass")
        store.set_rating(self.templates[2], 2)
        store.add_annotation(self.templates[3], 5_000, frame=125, asset_path="images/frame.png")
        store.save()

        loaded = ProjectStore.load(project)
        self.assertEqual(len(loaded.annotations), 3)
        self.assertEqual(loaded.rating_for("quality_1"), 2)
        self.assertEqual(loaded.annotations[0].id, interval.id)

        loaded.delete_annotation(interval.id)
        self.assertEqual(len(loaded.annotations), 2)
        self.assertTrue(loaded.undo())
        self.assertEqual(len(loaded.annotations), 3)
        self.assertTrue(loaded.redo())
        self.assertEqual(len(loaded.annotations), 2)

        export = self.root / "export"
        loaded.export_csv(export / "annotations.csv")
        loaded.export_legacy(export)
        with (export / "annotations.csv").open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 2)
        self.assertTrue((export / "assessment_scores.txt").exists())

    def test_import_legacy_intervals_and_scores(self):
        legacy = self.root / "legacy"
        legacy.mkdir()
        (legacy / "phase.txt").write_text("Phase A : (0:00:01,0:00:03)\n", encoding="utf-8")
        (legacy / "assessment_scores.txt").write_text("Quality : 1\n", encoding="utf-8")

        store = ProjectStore.create(self.root / "new.surgui.json", self.media, self.templates)
        reports = store.import_legacy_annotations(legacy)
        self.assertFalse([report for report in reports if report.severity == "error"])
        self.assertEqual(len(store.annotations), 2)
        self.assertEqual(store.rating_for("quality_1"), 1)

    def test_invalid_update_and_missing_delete_do_not_damage_history(self):
        store = ProjectStore.create(
            self.root / "history.surgui.json", self.media, self.templates, duration_ms=1_000
        )
        annotation = store.add_annotation(self.templates[0], 100, 500)
        store.delete_annotation(annotation.id)
        self.assertTrue(store.undo())
        self.assertTrue(store.can_redo)

        with self.assertRaises(KeyError):
            store.delete_annotation("missing")
        self.assertTrue(store.can_redo)

        with self.assertRaises(ValueError):
            store.update_annotation(annotation.id, end_ms=1_500)
        restored = next(item for item in store.annotations if item.id == annotation.id)
        self.assertEqual(restored.end_ms, 500)

    def test_annotation_can_be_reassigned_only_within_the_same_kind(self):
        store = ProjectStore.create(
            self.root / "reassign.surgui.json", self.media, self.templates
        )
        annotation = store.add_annotation(self.templates[0], 100, 500)

        updated = store.update_annotation(
            annotation.id, template_id=self.templates[1].id
        )

        self.assertEqual(updated.template_id, self.templates[1].id)
        self.assertEqual(updated.label, self.templates[1].label)
        self.assertEqual(updated.category, self.templates[1].category)
        with self.assertRaises(ValueError):
            store.update_annotation(
                annotation.id, template_id=self.templates[2].id
            )
        self.assertTrue(store.undo())
        restored = next(item for item in store.annotations if item.id == annotation.id)
        self.assertEqual(restored.template_id, self.templates[0].id)

    def test_template_crud_updates_references_and_blocks_unsafe_delete(self):
        store = ProjectStore.create(
            self.root / "template-crud.surgui.json", self.media, self.templates
        )
        created = TemplateItem(
            id="phase_created",
            label="Created phase",
            kind="interval",
            category="phase",
            group="Custom",
        )
        store.append_templates([created])
        annotation = store.add_annotation(created, 100, 500)

        updated = store.update_template(
            created.id,
            label="Renamed phase",
            group="Revised",
            start_hint="start",
            end_hint="end",
            required=True,
        )

        self.assertEqual(updated.label, "Renamed phase")
        persisted = next(item for item in store.annotations if item.id == annotation.id)
        self.assertEqual(persisted.label, "Renamed phase")
        with self.assertRaises(ValueError):
            store.delete_template(created.id)

        store.delete_annotation(annotation.id)
        deleted = store.delete_template(created.id)
        self.assertEqual(deleted.label, "Renamed phase")
        self.assertFalse(any(item.id == created.id for item in store.templates))
        self.assertTrue(store.undo())
        self.assertTrue(any(item.id == created.id for item in store.templates))

    def test_default_export_sync_creates_folder_and_refreshes_files(self):
        store = ProjectStore.create(
            self.root / "live-export" / "project.surgui.json",
            self.media,
            self.templates,
        )
        phase = store.add_annotation(self.templates[0], 100, 500)

        csv_path, legacy_paths = store.sync_default_exports()

        export_directory = store.output_directory / "exports"
        self.assertEqual(csv_path, export_directory / "annotations.csv")
        self.assertTrue(csv_path.is_file())
        self.assertTrue((export_directory / "phase.txt").is_file())
        self.assertTrue((export_directory / "surgui_legacy_manifest.json").is_file())
        self.assertTrue(legacy_paths)
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 1)

        store.add_annotation(self.templates[1], 700, 900)
        store.sync_default_exports()
        with csv_path.open(encoding="utf-8-sig", newline="") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 2)
        self.assertTrue((export_directory / "task.txt").is_file())

        store.delete_annotation(phase.id)
        store.sync_default_exports()
        self.assertFalse((export_directory / "phase.txt").exists())

    def test_invalid_project_file_has_friendly_failure(self):
        invalid = self.root / "invalid.surgui.json"
        invalid.write_text("[]", encoding="utf-8")
        with self.assertRaises(ValueError):
            ProjectStore.load(invalid)

    def test_invalid_loaded_annotation_is_rejected_before_ui_rendering(self):
        project = self.root / "invalid-annotation.surgui.json"
        store = ProjectStore.create(project, self.media, self.templates)
        store.add_annotation(self.templates[0], 100, 500)
        store.save()
        payload = json.loads(project.read_text(encoding="utf-8"))
        payload["annotations"][0]["start_ms"] = "not-a-time"
        project.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(ValueError):
            ProjectStore.load(project)

    def test_load_recovers_from_previous_backup_when_primary_is_damaged(self):
        project = self.root / "recoverable.surgui.json"
        store = ProjectStore.create(project, self.media, self.templates)
        store.add_annotation(self.templates[0], 100, 500)
        store.save()
        store.add_annotation(self.templates[1], 600, 800)
        store.save()
        project.write_text("{broken json", encoding="utf-8")

        recovered = ProjectStore.load(project)

        self.assertTrue(recovered.recovered_from_backup)
        self.assertEqual(recovered.path, project)
        self.assertEqual(len(recovered.annotations), 1)
        self.assertTrue(recovered.is_dirty)

    def test_legacy_point_round_trip_preserves_none_end(self):
        source = ProjectStore.create(self.root / "source.surgui.json", self.media, self.templates)
        source.add_annotation(self.templates[3], 2_000, frame=50)
        export = self.root / "legacy-point"
        source.export_legacy(export)

        restored = ProjectStore.create(self.root / "restored.surgui.json", self.media, self.templates)
        restored.import_legacy_annotations(export)
        point = next(item for item in restored.annotations if item.kind == "point")
        self.assertIsNone(point.end_ms)

    def test_legacy_manifest_preserves_unsafe_and_ambiguous_categories(self):
        templates = [
            TemplateItem("unsafe", "Unsafe", "interval", "phase/a"),
            TemplateItem("suffix", "Suffix", "interval", "phase_scores"),
            TemplateItem("rating", "Rating", "rating", "phase", score_options=[0, 1]),
        ]
        source = ProjectStore.create(self.root / "unsafe-source.surgui.json", self.media, templates)
        source.add_annotation(templates[0], 100, 500)
        source.add_annotation(templates[1], 700, 900)
        source.set_rating(templates[2], 1)
        export = self.root / "legacy-unsafe"
        source.export_legacy(export)
        self.assertTrue((export / "surgui_legacy_manifest.json").exists())

        restored = ProjectStore.create(self.root / "unsafe-restored.surgui.json", self.media, templates)
        reports = restored.import_legacy_annotations(export)

        self.assertFalse([report for report in reports if report.severity == "warning"])
        self.assertEqual(len(restored.annotations), 3)
        self.assertEqual(restored.rating_for("rating"), 1)

    def test_representative_frame_time_and_interval_union(self):
        first = Annotation("a", "interval", "phase_1", "A", "phase", 0, 4_000)
        second = Annotation("b", "interval", "phase_1", "A", "phase", 3_000, 7_000)
        point = Annotation("c", "point", "alert_1", "Alert", "assessment", 5_500)

        self.assertEqual(representative_frame_time(first), 2_000)
        self.assertEqual(representative_frame_time(point), 5_500)
        self.assertEqual(interval_coverage_ms([first, second], 10_000), 7_000)

    def test_temporal_quality_checks_and_phase_coverage(self):
        store = ProjectStore.create(
            self.root / "quality.surgui.json",
            self.media,
            self.templates,
            duration_ms=10_000,
        )
        phase = self.templates[0]
        task = self.templates[1]
        store.add_annotation(phase, 0, 4_000)
        store.add_annotation(phase, 3_500, 7_000)
        store.add_annotation(task, 8_000, 9_000)

        issues = store.validate()

        self.assertTrue(any("发生重叠" in issue.message for issue in issues))
        self.assertTrue(any("没有完整落在任一阶段内" in issue.message for issue in issues))
        self.assertTrue(any("最后阶段结束后" in issue.message for issue in issues))
        self.assertAlmostEqual(store.phase_coverage_ratio(), 0.7)

    def test_batch_asset_link_is_atomic_and_missing_file_is_reported(self):
        store = ProjectStore.create(
            self.root / "assets.surgui.json", self.media, self.templates
        )
        phase = store.add_annotation(self.templates[0], 100, 500)
        point = store.add_annotation(self.templates[3], 700, frame=18)
        images = store.output_directory / "images"
        images.mkdir()
        existing = images / "phase.png"
        existing.write_bytes(b"image")

        changed = store.set_annotation_assets(
            {
                phase.id: "images/phase.png",
                point.id: "images/missing.png",
            }
        )

        self.assertEqual(changed, 2)
        self.assertTrue(store.can_undo)
        self.assertTrue(any("画面不存在" in issue.message for issue in store.validate()))
        self.assertTrue(store.undo())
        self.assertFalse(any(item.asset_path for item in store.annotations))


if __name__ == "__main__":
    unittest.main()
