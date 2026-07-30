import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtTest import QTest

from surgui.project_store import ProjectStore, case_directory
from surgui.theme import load_theme
from surgui.vidPlayer_working import AnnotationWindow, EditAnnotationDialog


class WorkbenchInteractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # AnnotationWindow persists theme/output choices with QSettings.  Keep
        # the suite from writing into the developer's real user profile.
        cls.settings_directory = tempfile.TemporaryDirectory()
        cls.previous_settings_format = QtCore.QSettings.defaultFormat()
        QtCore.QSettings.setDefaultFormat(QtCore.QSettings.IniFormat)
        QtCore.QSettings.setPath(
            QtCore.QSettings.IniFormat,
            QtCore.QSettings.UserScope,
            cls.settings_directory.name,
        )
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        cls.window = AnnotationWindow()
        cls.window.show()
        cls.app.processEvents()

    @classmethod
    def tearDownClass(cls):
        cls.window.store = None
        cls.window.close()
        cls.app.processEvents()
        cls.app.quit()
        QtCore.QSettings.setDefaultFormat(cls.previous_settings_format)
        cls.settings_directory.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.window = self.__class__.window
        self.window.output_root = self.root
        self.window.store = None
        self.window.video_path = None
        self.window.pending_interval = None
        self.window._last_position = 0
        self.window._closing = False
        self.window.record_filter.clear()
        self.window.workspace_tabs.setCurrentIndex(0)
        self.window._refresh_project_views()
        self.app.processEvents()

    def tearDown(self):
        self.window.store = None
        self.app.processEvents()
        self.temporary.cleanup()

    def _attach_project(self):
        media = self.root / "case.mp4"
        media.write_bytes(b"workbench test video")
        store = ProjectStore.create(
            self.root / "project.surgui.json", media, self.window.templates, duration_ms=10_000
        )
        self.window.store = store
        self.window.video_path = media
        self.window.templates = store.templates
        return store

    def test_delete_selected_annotation_uses_safe_confirmation_path(self):
        store = self._attach_project()
        template = next(item for item in self.window.templates if item.kind == "interval")
        store.add_annotation(template, 1_000, 2_000)
        self.window._refresh_project_views()
        self.window.annotation_table.selectRow(0)
        self.window._confirm_annotation_delete = lambda annotation: True

        self.window.delete_selected_annotation()

        self.assertEqual(self.window.store.annotations, [])
        self.assertTrue(self.window.store.can_undo)

    def test_point_editor_updates_frame_and_respects_video_duration(self):
        store = self._attach_project()
        template = next(item for item in self.window.templates if item.kind == "point")
        annotation = store.add_annotation(
            template, 1_000, frame=25, asset_path="images/original.png"
        )
        dialog = EditAnnotationDialog(
            annotation,
            template,
            self.window,
            duration_ms=10_000,
            fps=25.0,
            templates=self.window.templates,
            current_position_ms=4_200,
        )
        dialog.use_current_start_button.click()
        self.assertEqual(dialog.start.text(), "00:00:04.200")
        dialog.start.setText("00:00:03.000")
        values = dialog.values()
        self.assertEqual(values["frame"], 75)
        self.assertNotIn("asset_path", values)

        dialog.start.setText("00:00:11.000")
        dialog._validate()
        self.assertTrue(dialog.error.text())
        dialog.close()

    def test_template_tree_keeps_navigation_but_allows_marking_shortcut(self):
        tree = self.window.phase_page.tree
        tree.setFocus()
        self.app.processEvents()

        with patch.object(self.window, "mark_start") as mark_start, patch.object(
            self.window, "toggle_playback"
        ) as toggle_playback, patch.object(self.window.backend, "step_frames") as step_frames:
            QTest.keyClick(tree, QtCore.Qt.Key_I)
            QTest.keyClick(tree, QtCore.Qt.Key_Right)
            QTest.keyClick(tree, QtCore.Qt.Key_Space)
            self.app.processEvents()

        mark_start.assert_called_once_with()
        toggle_playback.assert_called_once_with()
        step_frames.assert_not_called()

    def test_edit_action_accepts_return_and_keypad_enter_from_annotation_table(self):
        store = self._attach_project()
        template = next(item for item in self.window.templates if item.kind == "interval")
        store.add_annotation(template, 1_000, 2_000)
        self.window._refresh_project_views()
        self.window.annotation_table.selectRow(0)
        self.window.annotation_table.setFocus()
        self.app.processEvents()

        action = self.window.edit_annotation_action
        expected = {
            QtGui.QKeySequence(QtCore.Qt.Key_Return),
            QtGui.QKeySequence(QtCore.Qt.Key_Enter),
        }
        self.assertTrue(expected.issubset(set(action.shortcuts())))
        self.assertTrue(action.isEnabled())

        calls = []
        action.triggered.disconnect()
        action.triggered.connect(lambda _checked=False: calls.append(True))
        try:
            QTest.keyClick(self.window.annotation_table, QtCore.Qt.Key_Return)
            self.app.processEvents()
            self.assertEqual(calls, [True])

            calls.clear()
            QTest.keyClick(self.window.annotation_table, QtCore.Qt.Key_Enter)
            self.app.processEvents()
            self.assertEqual(calls, [True])
        finally:
            action.triggered.disconnect()
            action.triggered.connect(self.window.edit_selected_annotation)

    def test_record_edit_shortcuts_do_not_fire_from_template_tree(self):
        store = self._attach_project()
        template = next(item for item in self.window.templates if item.kind == "interval")
        store.add_annotation(template, 1_000, 2_000)
        self.window._refresh_project_views()
        self.window.annotation_table.selectRow(0)
        tree = self.window.phase_page.tree
        tree.setFocus()
        self.app.processEvents()

        calls = []
        actions = (self.window.edit_annotation_action, self.window.delete_annotation_action)
        try:
            for action in actions:
                action.triggered.disconnect()
                action.triggered.connect(lambda _checked=False, item=action: calls.append(item.text()))
            QTest.keyClick(tree, QtCore.Qt.Key_Return)
            QTest.keyClick(tree, QtCore.Qt.Key_Delete)
            self.app.processEvents()
            self.assertEqual(calls, [])
        finally:
            self.window.edit_annotation_action.triggered.disconnect()
            self.window.edit_annotation_action.triggered.connect(
                self.window.edit_selected_annotation
            )
            self.window.delete_annotation_action.triggered.disconnect()
            self.window.delete_annotation_action.triggered.connect(
                self.window.delete_selected_annotation
            )

    def test_context_menu_selects_the_row_under_the_pointer(self):
        store = self._attach_project()
        template = next(item for item in self.window.templates if item.kind == "interval")
        first = store.add_annotation(template, 1_000, 2_000)
        second = store.add_annotation(template, 3_000, 4_000)
        self.window._refresh_project_views()
        target_row = next(
            row
            for row in range(self.window.annotation_table.rowCount())
            if self.window.annotation_table.item(row, 0).data(QtCore.Qt.UserRole)
            == second.id
        )
        self.window.annotation_table.selectRow(
            next(
                row
                for row in range(self.window.annotation_table.rowCount())
                if self.window.annotation_table.item(row, 0).data(QtCore.Qt.UserRole)
                == first.id
            )
        )
        target_item = self.window.annotation_table.item(target_row, 0)
        position = self.window.annotation_table.visualItemRect(target_item).center()

        with patch.object(QtWidgets.QMenu, "exec_", return_value=None):
            self.window._show_annotation_context_menu(position)

        self.assertEqual(self.window._selected_annotation_id(), second.id)

    def test_multitrack_timeline_selects_and_reveals_annotation_record(self):
        store = self._attach_project()
        phase = next(
            item
            for item in self.window.templates
            if item.kind == "interval" and item.category.lower() == "phase"
        )
        task = next(
            item
            for item in self.window.templates
            if item.kind == "interval" and item.category.lower() != "phase"
        )
        point = next(item for item in self.window.templates if item.kind == "point")
        phase_annotation = store.add_annotation(phase, 1_000, 2_000)
        store.add_annotation(task, 4_000, 5_000)
        store.add_annotation(point, 7_000, frame=175)
        self.window._refresh_project_views()
        self.window.timeline.set_duration(10_000)
        self.window.record_filter.setText("hidden-by-filter")
        self.app.processEvents()
        self.assertEqual(self.window.annotation_table.rowCount(), 0)

        groove = self.window.timeline._groove_rect()
        lanes = self.window.timeline._lane_rects(groove)
        self.assertLess(lanes["phase"].top(), lanes["task"].top())
        self.assertLess(lanes["task"].top(), lanes["keyframe"].top())
        click_position = QtCore.QPoint(
            round(self.window.timeline._x_for_time(1_500, groove)),
            round(lanes["phase"].center().y()),
        )
        QTest.mouseClick(
            self.window.timeline,
            QtCore.Qt.LeftButton,
            QtCore.Qt.NoModifier,
            click_position,
        )
        self.app.processEvents()

        self.assertFalse(self.window.record_filter.text())
        self.assertEqual(
            self.window._selected_annotation_id(), phase_annotation.id
        )
        self.assertEqual(
            self.window.timeline._selected_annotation_id, phase_annotation.id
        )
        self.assertEqual(self.window.workspace_tabs.currentIndex(), 1)

    def test_close_ignores_event_when_pending_interval_discard_is_rejected(self):
        self.window.pending_interval = ("pending-template", 1_000)
        event = QtGui.QCloseEvent()
        try:
            with patch.object(
                self.window, "_confirm_discard_pending_interval", return_value=False
            ) as confirm:
                self.window.closeEvent(event)
            confirm.assert_called_once_with("放弃并退出")
            self.assertFalse(event.isAccepted())
        finally:
            self.window.pending_interval = None

    def test_close_uses_non_blocking_backend_shutdown(self):
        event = QtGui.QCloseEvent()
        try:
            with patch.object(self.window.backend, "shutdown_for_exit") as shutdown:
                self.window.closeEvent(event)

            shutdown.assert_called_once_with()
            self.assertTrue(event.isAccepted())
            self.assertTrue(self.window._closing)
        finally:
            self.window._closing = False
            self.app.installEventFilter(self.window)

    def test_theme_switch_rebuilds_the_application_style(self):
        self.window.apply_theme("clinical-dark")
        self.assertEqual(self.window.theme_id, "clinical-dark")
        self.assertIn(load_theme("clinical-dark").colours["canvas"], self.app.styleSheet())
        self.window.apply_theme("theatre-dim")
        self.assertEqual(self.window.theme_id, "theatre-dim")
        self.assertIn(load_theme("theatre-dim").colours["canvas"], self.app.styleSheet())
        self.window.apply_theme("clinical-light")

    def test_pending_interval_exposes_only_one_primary_completion_action(self):
        self._attach_project()
        template = next(item for item in self.window.templates if item.kind == "interval")
        self.window.active_template_id = template.id
        self.window.pending_interval = (template.id, 1_000)

        self.window._refresh_annotation_controls()

        self.assertTrue(self.window.start_button.isEnabled())
        self.assertFalse(bool(self.window.start_button.property("accent")))
        self.assertTrue(self.window.end_button.isEnabled())
        self.assertTrue(bool(self.window.end_button.property("success")))
        self.assertIn("完成", self.window.end_button.text())

    def test_timeline_zoom_and_pan_keep_real_video_time_range(self):
        timeline = self.window.timeline
        timeline.set_duration(16_000)
        timeline.set_playhead(8_000)

        timeline.zoom_in()

        self.assertEqual(timeline.zoom_factor, 2)
        self.assertEqual(timeline.maximum() - timeline.minimum(), 8_000)
        previous_start = timeline.minimum()
        timeline.pan(1)
        self.assertGreater(timeline.minimum(), previous_start)
        timeline.reset_zoom()
        self.assertEqual((timeline.minimum(), timeline.maximum()), (0, 16_000))

    def test_default_layout_reserves_a_substantial_annotation_workspace(self):
        sizes = self.window.main_splitter.sizes()
        total = sum(sizes)

        self.assertGreater(total, 0)
        self.assertGreaterEqual(
            self.window.main_splitter.widget(1).minimumWidth(), 500
        )
        self.assertGreaterEqual(sizes[1] / total, 0.40)

    def test_transport_controls_use_icons_and_separate_workspace_pages(self):
        self.assertTrue(self.window.back_frame_button.text() == "")
        self.assertTrue(self.window.forward_frame_button.text() == "")
        self.assertFalse(self.window.back_frame_button.icon().isNull())
        self.assertFalse(self.window.forward_frame_button.icon().isNull())
        self.assertEqual(self.window.workspace_tabs.count(), 2)
        self.assertIs(self.window.workspace_tabs.widget(0), self.window.template_tabs)
        self.assertIn("标注记录", self.window.workspace_tabs.tabText(1))

    def test_save_refreshes_default_exports_without_manual_export(self):
        store = self._attach_project()
        template = next(item for item in self.window.templates if item.kind == "interval")
        store.add_annotation(template, 1_000, 2_000)

        self.assertTrue(self.window._save_project())

        exports = store.output_directory / "exports"
        self.assertTrue((exports / "annotations.csv").is_file())
        self.assertTrue((exports / f"{template.category}.txt").is_file())
        self.assertIn("已保存并同步", self.window.save_state.text())

    def test_phase_and_task_pages_expose_template_crud_controls(self):
        for page in (self.window.phase_page, self.window.task_page):
            self.assertEqual(page.import_button.text(), "导入")
            self.assertEqual(page.add_button.text(), "新增")
            self.assertEqual(page.edit_button.text(), "编辑")
            self.assertEqual(page.delete_button.text(), "删除")

    def test_cancelled_video_switch_preserves_existing_case_state(self):
        old_store = self._attach_project()
        old_video = self.window.video_path
        new_video = self.root / "new.mp4"
        new_video.write_bytes(b"new workbench test video")
        destination = case_directory(self.root, new_video)
        existing = ProjectStore.create(
            destination / "project.surgui.json", new_video, self.window.templates
        )
        existing.save()

        with patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.Cancel,
        ):
            self.window._open_video_path(new_video)

        self.assertIs(self.window.store, old_store)
        self.assertEqual(self.window.video_path, old_video)


if __name__ == "__main__":
    unittest.main()
