"""SurgiAnnotate: a focused, local-first surgical video annotation workbench.

This module intentionally replaces the old widget-array prototype. The main
workflow is concise: choose a label, mark its in/out point, and continue
watching. Project recovery, validation, exports, ratings and key frames are
kept in supporting panels instead of competing with the video.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import cv2
from PyQt5 import QtCore, QtGui, QtMultimedia, QtMultimediaWidgets, QtWidgets


_VLC_DLL_DIRECTORY_HANDLES: List[object] = []


def _configure_bundled_vlc() -> Optional[Path]:
    """Make a colocated VLC runtime discoverable before importing python-vlc."""
    if platform.system() != "Windows":
        return None

    frozen_root = getattr(sys, "_MEIPASS", "")
    candidates = [
        Path(frozen_root) if frozen_root else None,
        Path(sys.executable).resolve().parent,
        Path(__file__).resolve().parent.parent,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        runtime = candidate.resolve()
        if not (runtime / "libvlc.dll").is_file():
            continue
        plugin_directory = runtime / "plugins"
        if plugin_directory.is_dir():
            os.environ["VLC_PLUGIN_PATH"] = str(plugin_directory)
            os.environ["PYTHON_VLC_MODULE_PATH"] = str(plugin_directory)
        os.environ["PYTHON_VLC_LIB_PATH"] = str(runtime / "libvlc.dll")
        os.environ["PATH"] = str(runtime) + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            # The returned handle must stay alive while LibVLC is in use.
            _VLC_DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(runtime)))
        return runtime
    return None


VLC_RUNTIME_DIRECTORY = _configure_bundled_vlc()
VLC_IMPORT_ERROR = ""

try:
    import vlc  # type: ignore

    VLC_AVAILABLE = True
except (ImportError, OSError, SystemExit) as error:
    vlc = None
    VLC_AVAILABLE = False
    VLC_IMPORT_ERROR = str(error)

try:
    from .project_store import (
        Annotation,
        ProjectStore,
        TemplateItem,
        ValidationIssue,
        case_directory,
        default_templates,
        format_timecode,
        make_id,
        media_fingerprint,
        parse_interval_template,
        parse_rating_template,
        parse_timecode,
        representative_frame_time,
    )
    from .theme import (
        COLOURS,
        DEFAULT_THEME,
        THEME_LABELS,
        activate_theme,
        annotation_colour,
        build_palette,
        build_stylesheet,
        resource_root,
        spacing_pixels,
    )
except ImportError:
    # Supports running this file directly as well as python -m surgui.
    from project_store import (  # type: ignore
        Annotation,
        ProjectStore,
        TemplateItem,
        ValidationIssue,
        case_directory,
        default_templates,
        format_timecode,
        make_id,
        media_fingerprint,
        parse_interval_template,
        parse_rating_template,
        parse_timecode,
        representative_frame_time,
    )
    from theme import (  # type: ignore
        COLOURS,
        DEFAULT_THEME,
        THEME_LABELS,
        activate_theme,
        annotation_colour,
        build_palette,
        build_stylesheet,
        resource_root,
        spacing_pixels,
    )


APP_NAME = "SurgiAnnotate"
ROOT_DIRECTORY = resource_root()
PROJECT_FILENAME = "project.surgui.json"


def human_kind(kind: str) -> str:
    return {
        "interval": "区间",
        "point": "关键帧",
        "rating": "评分",
    }.get(kind, kind)


def human_status(status: str) -> str:
    return {
        "draft": "草稿",
        "ready": "待审核",
        "reviewed": "已审核",
    }.get(status, status)


class VideoBackend(QtCore.QObject):
    """A small playback facade that prefers VLC and falls back to Qt Media."""

    position_changed = QtCore.pyqtSignal(int)
    duration_changed = QtCore.pyqtSignal(int)
    playback_changed = QtCore.pyqtSignal(bool)
    error_occurred = QtCore.pyqtSignal(str)

    def __init__(self, video_widget: QtWidgets.QWidget, parent: Optional[QtCore.QObject] = None):
        super().__init__(parent)
        self.video_widget = video_widget
        self.path: Optional[Path] = None
        self._duration_ms = 0
        self._position_ms = 0
        self._playing = False
        self._fps = 0.0
        self._using_vlc = False
        self._vlc_error = VLC_IMPORT_ERROR
        self._vlc_instance = None
        self._vlc_player = None
        self._qt_player: Optional[QtMultimedia.QMediaPlayer] = None

        if VLC_AVAILABLE:
            try:
                self._vlc_instance = vlc.Instance("--no-video-title-show", "--quiet")
                self._vlc_player = self._vlc_instance.media_player_new()
                self._using_vlc = True
            except Exception as error:
                self._vlc_error = str(error)
                self._vlc_instance = None
                self._vlc_player = None

        self._poll_timer = QtCore.QTimer(self)
        self._poll_timer.setInterval(80)
        self._poll_timer.timeout.connect(self._poll_vlc)

        if not self._using_vlc:
            self._qt_player = QtMultimedia.QMediaPlayer(
                None, QtMultimedia.QMediaPlayer.VideoSurface
            )
            self._qt_player.setVideoOutput(video_widget)
            self._qt_player.positionChanged.connect(self._on_qt_position)
            self._qt_player.durationChanged.connect(self._on_qt_duration)
            self._qt_player.stateChanged.connect(self._on_qt_state)
            self._qt_player.error.connect(self._on_qt_error)

    @property
    def backend_name(self) -> str:
        return "VLC" if self._using_vlc else "Qt Media"

    @property
    def duration_ms(self) -> int:
        return max(0, self._duration_ms)

    @property
    def position_ms(self) -> int:
        return max(0, self._position_ms)

    @property
    def fps(self) -> float:
        return self._fps if self._fps > 0 else 25.0

    @property
    def is_playing(self) -> bool:
        return self._playing

    def open(self, media_path: Path) -> None:
        self.stop()
        self.path = Path(media_path)
        self._duration_ms = 0
        self._position_ms = 0
        self._fps = self._read_fps(self.path)
        if self._using_vlc:
            try:
                media = self._vlc_instance.media_new(str(self.path))
                self._vlc_player.set_media(media)
                self._set_vlc_window()
                self._poll_timer.start()
            except Exception as error:
                self.error_occurred.emit(f"VLC 无法打开视频：{error}")
        else:
            self._qt_player.setMedia(
                QtMultimedia.QMediaContent(QtCore.QUrl.fromLocalFile(str(self.path)))
            )
        self.position_changed.emit(0)
        self.duration_changed.emit(0)

    def play(self) -> None:
        if not self.path:
            return
        if self._using_vlc:
            try:
                self._set_vlc_window()
                result = self._vlc_player.play()
                if result == -1:
                    self.error_occurred.emit("VLC 无法播放此视频")
                    return
                self._poll_timer.start()
                self._set_playing(True)
            except Exception as error:
                self.error_occurred.emit(f"播放失败：{error}")
        else:
            self._qt_player.play()

    def pause(self) -> None:
        if self._using_vlc:
            if self._vlc_player:
                self._vlc_player.pause()
            self._set_playing(False)
        elif self._qt_player:
            self._qt_player.pause()

    def toggle(self) -> None:
        self.pause() if self.is_playing else self.play()

    def stop(self) -> None:
        if self._using_vlc:
            if self._vlc_player:
                try:
                    self._vlc_player.stop()
                except Exception:
                    pass
            self._poll_timer.stop()
        elif self._qt_player:
            self._qt_player.stop()
        self._set_playing(False)

    def seek(self, milliseconds: int) -> None:
        value = max(0, int(milliseconds))
        if self.duration_ms:
            value = min(value, self.duration_ms)
        if self._using_vlc:
            if self._vlc_player:
                self._vlc_player.set_time(value)
        elif self._qt_player:
            self._qt_player.setPosition(value)
        self._on_position(value)

    def step_frames(self, number_of_frames: int) -> None:
        self.seek(self.position_ms + int((1_000 / self.fps) * number_of_frames))

    def step_seconds(self, seconds: float) -> None:
        self.seek(self.position_ms + int(seconds * 1_000))

    def set_rate(self, rate: float) -> None:
        if self._using_vlc:
            if self._vlc_player:
                self._vlc_player.set_rate(float(rate))
        elif self._qt_player:
            self._qt_player.setPlaybackRate(float(rate))

    def release(self) -> None:
        self.stop()
        if self._using_vlc:
            try:
                if self._vlc_player:
                    self._vlc_player.release()
                if self._vlc_instance:
                    self._vlc_instance.release()
            except Exception:
                pass

    def shutdown_for_exit(self) -> None:
        """Stop UI activity without waiting on native VLC teardown."""
        self._poll_timer.stop()
        self.path = None
        self._playing = False
        if self._using_vlc:
            # libvlc_media_player_stop/release can block indefinitely for some
            # decoder states. The process is exiting, so Windows can reclaim
            # these native resources without freezing the GUI thread.
            return
        if self._qt_player:
            self._qt_player.blockSignals(True)
            try:
                self._qt_player.stop()
            except Exception:
                pass

    def _read_fps(self, path: Path) -> float:
        capture = cv2.VideoCapture(str(path))
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            return fps if fps > 1 else 25.0
        finally:
            capture.release()

    def _set_vlc_window(self) -> None:
        if not self._using_vlc or not self._vlc_player:
            return
        window_id = int(self.video_widget.winId())
        system = platform.system()
        if system == "Windows":
            self._vlc_player.set_hwnd(window_id)
        elif system == "Darwin":
            self._vlc_player.set_nsobject(window_id)
        else:
            self._vlc_player.set_xwindow(window_id)

    def _on_qt_position(self, milliseconds: int) -> None:
        self._on_position(milliseconds)

    def _on_qt_duration(self, milliseconds: int) -> None:
        self._on_duration(milliseconds)

    def _on_qt_state(self, state: QtMultimedia.QMediaPlayer.State) -> None:
        self._set_playing(state == QtMultimedia.QMediaPlayer.PlayingState)

    def _on_qt_error(self, *_: object) -> None:
        if self._qt_player and self._qt_player.error() != QtMultimedia.QMediaPlayer.NoError:
            detail = self._qt_player.errorString() or "DirectShow 无法渲染此媒体"
            guidance = (
                "当前正在使用 Qt Media 后备播放器。Windows DirectShow 无法连接此视频所需的"
                "解码器。请在当前 Python 环境安装 python-vlc，并确保项目目录中的 "
                "libvlc.dll 与 plugins 文件夹完整；也可以安装系统视频解码器。"
            )
            if self._vlc_error:
                guidance += f"\n\nVLC 初始化失败：{self._vlc_error}"
            self.error_occurred.emit(f"{detail}\n\n{guidance}")

    def _poll_vlc(self) -> None:
        if not self._vlc_player:
            return
        try:
            self._on_duration(self._vlc_player.get_length())
            self._on_position(self._vlc_player.get_time())
            self._set_playing(bool(self._vlc_player.is_playing()))
        except Exception:
            return

    def _on_position(self, milliseconds: int) -> None:
        value = max(0, int(milliseconds or 0))
        if value != self._position_ms:
            self._position_ms = value
            self.position_changed.emit(value)

    def _on_duration(self, milliseconds: int) -> None:
        value = max(0, int(milliseconds or 0))
        if value and value != self._duration_ms:
            self._duration_ms = value
            self.duration_changed.emit(value)

    def _set_playing(self, playing: bool) -> None:
        if playing != self._playing:
            self._playing = playing
            self.playback_changed.emit(playing)


class AnnotationTimeline(QtWidgets.QSlider):
    """A seek bar with separate phase, task and key-frame annotation lanes."""

    seek_requested = QtCore.pyqtSignal(int)
    annotation_selected = QtCore.pyqtSignal(str)
    zoom_changed = QtCore.pyqtSignal(int)
    ZOOM_LEVELS = (1, 2, 4, 8, 16)
    LANE_ROWS = {"phase": 2, "task": 3, "keyframe": 2}

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(QtCore.Qt.Horizontal, parent)
        self._annotations: List[Annotation] = []
        self._duration = 0
        self._playhead = 0
        self._zoom_factor = 1
        self._selected_annotation_id: Optional[str] = None
        self.setRange(0, 0)
        self.setMinimumHeight(spacing_pixels("xxl") * 3 + spacing_pixels("sm"))
        self.setMouseTracking(True)

    def set_duration(self, milliseconds: int) -> None:
        self._duration = max(0, int(milliseconds))
        self._playhead = min(self._playhead, self._duration)
        self._zoom_factor = 1
        self.setRange(0, self._duration)
        self.setValue(self._playhead)
        self.zoom_changed.emit(self._zoom_factor)
        self.update()

    @property
    def zoom_factor(self) -> int:
        return self._zoom_factor

    def set_playhead(self, milliseconds: int) -> None:
        self._playhead = max(0, min(int(milliseconds), self._duration))
        if self._zoom_factor > 1 and not self.minimum() <= self._playhead <= self.maximum():
            self._set_view_around(self._playhead)
        self.blockSignals(True)
        self.setValue(max(self.minimum(), min(self._playhead, self.maximum())))
        self.blockSignals(False)

    def zoom_in(self) -> None:
        index = self.ZOOM_LEVELS.index(self._zoom_factor)
        if index < len(self.ZOOM_LEVELS) - 1:
            self.set_zoom_factor(self.ZOOM_LEVELS[index + 1])

    def zoom_out(self) -> None:
        index = self.ZOOM_LEVELS.index(self._zoom_factor)
        if index > 0:
            self.set_zoom_factor(self.ZOOM_LEVELS[index - 1])

    def reset_zoom(self) -> None:
        self.set_zoom_factor(1)

    def set_zoom_factor(self, factor: int) -> None:
        requested = min(self.ZOOM_LEVELS, key=lambda value: abs(value - int(factor)))
        if requested == self._zoom_factor and self.maximum() > self.minimum():
            return
        self._zoom_factor = requested
        self._set_view_around(self._playhead)
        self.zoom_changed.emit(self._zoom_factor)

    def pan(self, direction: int) -> None:
        if self._zoom_factor <= 1 or not self._duration:
            return
        span = max(1, self.maximum() - self.minimum())
        shift = max(1, int(span * 0.75)) * (1 if direction > 0 else -1)
        start = max(0, min(self.minimum() + shift, self._duration - span))
        self._apply_view(start, start + span)

    def _set_view_around(self, centre: int) -> None:
        if not self._duration or self._zoom_factor <= 1:
            self._apply_view(0, self._duration)
            return
        span = max(1, int(self._duration / self._zoom_factor))
        start = max(0, min(int(centre) - span // 2, self._duration - span))
        self._apply_view(start, start + span)

    def _apply_view(self, start: int, end: int) -> None:
        start = max(0, min(int(start), self._duration))
        end = max(start, min(int(end), self._duration))
        self.blockSignals(True)
        self.setRange(start, end)
        self.setValue(max(start, min(self._playhead, end)))
        self.blockSignals(False)
        self.update()

    def set_annotations(self, annotations: Iterable[Annotation]) -> None:
        self._annotations = [
            annotation
            for annotation in annotations
            if annotation.kind in {"interval", "point"} and annotation.start_ms >= 0
        ]
        if self._selected_annotation_id not in {
            annotation.id for annotation in self._annotations
        }:
            self._selected_annotation_id = None
        self.update()

    def set_selected_annotation(self, annotation_id: Optional[str]) -> None:
        selected = str(annotation_id) if annotation_id else None
        if selected != self._selected_annotation_id:
            self._selected_annotation_id = selected
            self.update()

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            value = self._value_from_x(event.pos().x())
            annotation = self._annotation_at(value, event.pos().y())
            if annotation:
                self.set_selected_annotation(annotation.id)
                self.annotation_selected.emit(annotation.id)
            self.setValue(value)
            self.seek_requested.emit(value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.buttons() & QtCore.Qt.LeftButton:
            value = self._value_from_x(event.pos().x())
            self.setValue(value)
            self.seek_requested.emit(value)
        else:
            self._show_annotation_tooltip(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.seek_requested.emit(self.value())
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if event.modifiers() & QtCore.Qt.ControlModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            event.accept()
            return
        if event.modifiers() & QtCore.Qt.ShiftModifier:
            self.pan(-1 if event.angleDelta().y() > 0 else 1)
            event.accept()
            return
        super().wheelEvent(event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        super().paintEvent(event)
        if not self._duration:
            return
        option = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self.style().subControlRect(
            QtWidgets.QStyle.CC_Slider,
            option,
            QtWidgets.QStyle.SC_SliderGroove,
            self,
        )
        if groove.width() <= 0:
            return
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        lane_rects = self._lane_rects(groove)
        rows = self._annotation_rows(groove)
        for annotation in self._annotations:
            annotation_end = (
                annotation.end_ms
                if annotation.end_ms is not None
                else annotation.start_ms
            )
            if annotation_end < self.minimum() or annotation.start_ms > self.maximum():
                continue
            colour = self._colour_for_annotation(annotation)
            selected = annotation.id == self._selected_annotation_id
            painter.setPen(
                QtGui.QPen(
                    QtGui.QColor(COLOURS["focus"]),
                    spacing_pixels("xxs"),
                )
                if selected
                else QtCore.Qt.NoPen
            )
            painter.setBrush(QtGui.QColor(colour))
            lane_key = self._lane_key(annotation)
            lane = self._track_rect(
                lane_rects[lane_key],
                rows.get(annotation.id, 0),
                self.LANE_ROWS[lane_key],
            )
            start_x = self._x_for_time(
                max(self.minimum(), annotation.start_ms), groove
            )
            if annotation.kind == "point":
                radius = lane.height() / 2 + (1 if selected else 0)
                painter.drawEllipse(
                    QtCore.QPointF(start_x, lane.center().y()),
                    radius,
                    radius,
                )
            else:
                end = annotation.end_ms if annotation.end_ms is not None else annotation.start_ms
                end_x = self._x_for_time(min(self.maximum(), end), groove)
                width = max(spacing_pixels("xs"), end_x - start_x)
                painter.drawRoundedRect(
                    QtCore.QRectF(start_x, lane.y(), width, lane.height()),
                    lane.height() / 2,
                    lane.height() / 2,
                )
        painter.end()

    def _groove_rect(self) -> QtCore.QRect:
        option = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(option)
        return self.style().subControlRect(
            QtWidgets.QStyle.CC_Slider,
            option,
            QtWidgets.QStyle.SC_SliderGroove,
            self,
        )

    @staticmethod
    def _lane_key(annotation: Annotation) -> str:
        if annotation.kind == "point":
            return "keyframe"
        return "phase" if annotation.category.lower() == "phase" else "task"

    def _lane_rects(self, groove: QtCore.QRect) -> Dict[str, QtCore.QRectF]:
        lane_height = max(
            spacing_pixels("xs"),
            spacing_pixels("sm") - spacing_pixels("xxs"),
        )
        gap = spacing_pixels("xxs")
        keys = ("phase", "task", "keyframe")
        band_heights = {
            key: self.LANE_ROWS[key] * lane_height
            + (self.LANE_ROWS[key] - 1) * gap
            for key in keys
        }
        total_height = sum(band_heights.values()) + (len(keys) - 1) * gap
        top = max(
            spacing_pixels("xxs"),
            groove.top() - spacing_pixels("xs") - total_height,
        )
        result = {}
        cursor = float(top)
        for key in keys:
            result[key] = QtCore.QRectF(
                groove.left(),
                cursor,
                groove.width(),
                band_heights[key],
            )
            cursor += band_heights[key] + gap
        return result

    @staticmethod
    def _track_rect(
        band: QtCore.QRectF, row: int, row_count: int
    ) -> QtCore.QRectF:
        gap = spacing_pixels("xxs")
        height = max(
            spacing_pixels("xs"),
            (band.height() - (row_count - 1) * gap) / row_count,
        )
        selected_row = max(0, min(int(row), row_count - 1))
        return QtCore.QRectF(
            band.left(),
            band.top() + selected_row * (height + gap),
            band.width(),
            height,
        )

    def _annotation_rows(self, groove: QtCore.QRect) -> Dict[str, int]:
        assignments: Dict[str, int] = {}
        visible_span = max(1, self.maximum() - self.minimum())
        point_width = max(
            1,
            int(
                visible_span
                / max(1, groove.width())
                * spacing_pixels("lg")
            ),
        )
        for lane_key, row_count in self.LANE_ROWS.items():
            occupied_until = [-1] * row_count
            candidates = sorted(
                (
                    annotation
                    for annotation in self._annotations
                    if self._lane_key(annotation) == lane_key
                ),
                key=lambda item: (
                    item.start_ms,
                    item.end_ms if item.end_ms is not None else item.start_ms,
                ),
            )
            for annotation in candidates:
                end = (
                    int(annotation.end_ms)
                    if annotation.end_ms is not None
                    else annotation.start_ms + point_width
                )
                row = next(
                    (
                        index
                        for index, occupied in enumerate(occupied_until)
                        if annotation.start_ms >= occupied
                    ),
                    row_count - 1,
                )
                assignments[annotation.id] = row
                occupied_until[row] = max(occupied_until[row], end)
        return assignments

    def _annotation_at(self, position: int, y: int) -> Optional[Annotation]:
        if not self._duration:
            return None
        groove = self._groove_rect()
        lane_rects = self._lane_rects(groove)
        hit_padding = max(1, spacing_pixels("xxs") // 2)
        lane_key = next(
            (
                key
                for key, rect in lane_rects.items()
                if rect.top() - hit_padding <= y <= rect.bottom() + hit_padding
            ),
            None,
        )
        if not lane_key:
            return None
        candidates = [
            annotation
            for annotation in self._annotations
            if self._lane_key(annotation) == lane_key
        ]
        threshold = max(
            250,
            int(
                max(1, self.maximum() - self.minimum())
                / max(1, groove.width())
                * spacing_pixels("sm")
            ),
        )
        if lane_key == "keyframe":
            nearby = [
                annotation
                for annotation in candidates
                if abs(annotation.start_ms - position) <= threshold
            ]
            return min(
                nearby,
                key=lambda annotation: abs(annotation.start_ms - position),
                default=None,
            )

        containing = [
            annotation
            for annotation in candidates
            if annotation.start_ms
            <= position
            <= (annotation.end_ms if annotation.end_ms is not None else annotation.start_ms)
        ]
        if containing:
            return min(
                containing,
                key=lambda annotation: (
                    (annotation.end_ms or annotation.start_ms) - annotation.start_ms
                ),
            )
        nearby = [
            annotation
            for annotation in candidates
            if min(
                abs(annotation.start_ms - position),
                abs((annotation.end_ms or annotation.start_ms) - position),
            )
            <= threshold
        ]
        return min(
            nearby,
            key=lambda annotation: min(
                abs(annotation.start_ms - position),
                abs((annotation.end_ms or annotation.start_ms) - position),
            ),
            default=None,
        )

    def _value_from_x(self, x: int) -> int:
        if self.maximum() <= self.minimum():
            return 0
        option = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(option)
        groove = self._groove_rect()
        span = max(1, groove.width())
        position = max(0, min(x - groove.x(), span))
        return QtWidgets.QStyle.sliderValueFromPosition(
            self.minimum(), self.maximum(), position, span, option.upsideDown
        )

    def _x_for_time(self, milliseconds: int, groove: QtCore.QRect) -> float:
        span = max(1, self.maximum() - self.minimum())
        visible = max(self.minimum(), min(milliseconds, self.maximum()))
        return groove.x() + ((visible - self.minimum()) / span) * groove.width()

    def _colour_for_annotation(self, annotation: Annotation) -> str:
        return annotation_colour(annotation.kind, annotation.category)

    def _show_annotation_tooltip(self, event: QtGui.QMouseEvent) -> None:
        if not self._duration:
            return
        position = self._value_from_x(event.pos().x())
        closest = self._annotation_at(position, event.pos().y())
        if closest:
            if closest.kind == "interval":
                value = f"{format_timecode(closest.start_ms)} — {format_timecode(closest.end_ms)}"
            else:
                value = format_timecode(closest.start_ms)
            QtWidgets.QToolTip.showText(event.globalPos(), f"{closest.label}\n{value}", self)


class LabelTreePage(QtWidgets.QWidget):
    """Searchable grouped template selection for phase and task labels."""

    template_selected = QtCore.pyqtSignal(str)
    add_requested = QtCore.pyqtSignal()
    edit_requested = QtCore.pyqtSignal(str)
    delete_requested = QtCore.pyqtSignal(str)
    import_requested = QtCore.pyqtSignal()

    def __init__(self, empty_text: str, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._templates: List[TemplateItem] = []
        self._empty_text = empty_text
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(
            spacing_pixels("md"),
            spacing_pixels("md"),
            spacing_pixels("md"),
            spacing_pixels("md"),
        )
        layout.setSpacing(spacing_pixels("sm"))

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("搜索标签…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate)
        layout.addWidget(self.search)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setIndentation(spacing_pixels("lg"))
        self.tree.itemSelectionChanged.connect(self._emit_selection)
        self.tree.itemDoubleClicked.connect(self._request_edit)
        layout.addWidget(self.tree, 1)

        self.hint = QtWidgets.QLabel(empty_text)
        self.hint.setObjectName("Muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        management = QtWidgets.QHBoxLayout()
        management.setSpacing(spacing_pixels("xs"))
        self.import_button = QtWidgets.QPushButton("导入")
        self.import_button.setToolTip("从 TXT 文件追加标签")
        self.import_button.clicked.connect(self.import_requested)
        self.add_button = QtWidgets.QPushButton("新增")
        self.add_button.clicked.connect(self.add_requested)
        self.edit_button = QtWidgets.QPushButton("编辑")
        self.edit_button.clicked.connect(self._request_edit)
        self.delete_button = QtWidgets.QPushButton("删除")
        self.delete_button.setProperty("danger", True)
        self.delete_button.clicked.connect(self._request_delete)
        for button in (
            self.import_button,
            self.add_button,
            self.edit_button,
            self.delete_button,
        ):
            management.addWidget(button)
        layout.addLayout(management)
        self._update_management_actions()

    def set_templates(self, templates: Iterable[TemplateItem]) -> None:
        self._templates = list(templates)
        self._populate()

    def select_template(self, template_id: Optional[str]) -> None:
        if not template_id:
            return
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            item = iterator.value()
            if item.data(0, QtCore.Qt.UserRole) == template_id:
                self.tree.setCurrentItem(item)
                return
            iterator += 1

    def _populate(self) -> None:
        selected = self._selected_id()
        term = self.search.text().strip().lower()
        self.tree.blockSignals(True)
        self.tree.clear()
        groups: Dict[str, List[TemplateItem]] = defaultdict(list)
        for template in self._templates:
            if term and term not in template.label.lower() and term not in template.group.lower():
                continue
            groups[template.group].append(template)
        for group_name, templates in groups.items():
            group = QtWidgets.QTreeWidgetItem([group_name])
            group.setFlags(group.flags() & ~QtCore.Qt.ItemIsSelectable)
            group.setForeground(0, QtGui.QBrush(QtGui.QColor(COLOURS["muted"])))
            self.tree.addTopLevelItem(group)
            for template in templates:
                child = QtWidgets.QTreeWidgetItem([template.label])
                child.setData(0, QtCore.Qt.UserRole, template.id)
                child.setData(0, QtCore.Qt.UserRole + 1, template.kind)
                child.setForeground(
                    0,
                    QtGui.QBrush(
                        QtGui.QColor(annotation_colour(template.kind, template.category))
                    ),
                )
                hints = []
                if template.start_hint:
                    hints.append(f"开始提示：{template.start_hint}")
                if template.end_hint:
                    hints.append(f"结束提示：{template.end_hint}")
                child.setToolTip(0, "\n".join(hints) or template.label)
                group.addChild(child)
                if template.id == selected:
                    self.tree.setCurrentItem(child)
            group.setExpanded(True)
        self.hint.setVisible(not bool(groups))
        self.tree.blockSignals(False)
        self._update_management_actions()

    def _selected_id(self) -> Optional[str]:
        item = self.tree.currentItem()
        return item.data(0, QtCore.Qt.UserRole) if item else None

    def _emit_selection(self) -> None:
        template_id = self._selected_id()
        self._update_management_actions()
        if template_id:
            self.template_selected.emit(str(template_id))

    def _update_management_actions(self) -> None:
        selected = bool(self._selected_id())
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def _request_edit(self, *_args) -> None:
        template_id = self._selected_id()
        if template_id:
            self.edit_requested.emit(str(template_id))

    def _request_delete(self) -> None:
        template_id = self._selected_id()
        if template_id:
            self.delete_requested.emit(str(template_id))


class RatingPage(QtWidgets.QWidget):
    """Compact segmented score controls, saved immediately on click."""

    score_selected = QtCore.pyqtSignal(str, int)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.content = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(self.content)
        self.layout.setContentsMargins(
            spacing_pixels("md"),
            spacing_pixels("md"),
            spacing_pixels("md"),
            spacing_pixels("md"),
        )
        self.layout.setSpacing(spacing_pixels("sm"))
        self.layout.addStretch()
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll)

    def set_templates(self, templates: Iterable[TemplateItem], ratings: Dict[str, Optional[int]]) -> None:
        self._clear()
        items = list(templates)
        if not items:
            label = QtWidgets.QLabel("未加载评分模板。可从“模板”菜单导入评分文件。")
            label.setObjectName("Muted")
            label.setWordWrap(True)
            self.layout.insertWidget(0, label)
            return
        for template in items:
            card = QtWidgets.QFrame()
            card.setObjectName("Panel")
            row = QtWidgets.QVBoxLayout(card)
            row.setContentsMargins(
                spacing_pixels("md"),
                spacing_pixels("sm"),
                spacing_pixels("md"),
                spacing_pixels("sm"),
            )
            title = QtWidgets.QLabel(template.label)
            title.setWordWrap(True)
            row.addWidget(title)
            scores = QtWidgets.QHBoxLayout()
            group = QtWidgets.QButtonGroup(card)
            group.setExclusive(True)
            current = ratings.get(template.id)
            for score in template.score_options:
                button = QtWidgets.QPushButton(str(score))
                button.setCheckable(True)
                button.setProperty("score", True)
                button.setToolTip(f"将“{template.label}”设为 {score}")
                group.addButton(button, score)
                button.setChecked(current == score)
                scores.addWidget(button)
            scores.addStretch()
            group.buttonClicked[int].connect(
                lambda score, template_id=template.id: self.score_selected.emit(template_id, score)
            )
            row.addLayout(scores)
            self.layout.insertWidget(self.layout.count() - 1, card)

    def _clear(self) -> None:
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class PointPage(QtWidgets.QWidget):
    """Point labels with direct record and record-plus-capture actions."""

    record_requested = QtCore.pyqtSignal(str, bool)
    template_selected = QtCore.pyqtSignal(str)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.content = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(self.content)
        self.layout.setContentsMargins(
            spacing_pixels("md"),
            spacing_pixels("md"),
            spacing_pixels("md"),
            spacing_pixels("md"),
        )
        self.layout.setSpacing(spacing_pixels("sm"))
        self.layout.addStretch()
        self.scroll.setWidget(self.content)
        root.addWidget(self.scroll)

    def set_templates(self, templates: Iterable[TemplateItem]) -> None:
        self._clear()
        items = list(templates)
        if not items:
            label = QtWidgets.QLabel("未加载关键帧/预警标签。评分模板中 #0 的条目会显示在这里。")
            label.setObjectName("Muted")
            label.setWordWrap(True)
            self.layout.insertWidget(0, label)
            return
        for template in items:
            card = QtWidgets.QFrame()
            card.setObjectName("Panel")
            row = QtWidgets.QHBoxLayout(card)
            row.setContentsMargins(
                spacing_pixels("md"),
                spacing_pixels("sm"),
                spacing_pixels("sm"),
                spacing_pixels("sm"),
            )
            title = QtWidgets.QLabel(template.label)
            title.setWordWrap(True)
            title.setObjectName("PointTemplateTitle")
            row.addWidget(title, 1)
            record = QtWidgets.QPushButton("记录")
            record.setToolTip("在当前时间记录此关键帧")
            record.clicked.connect(
                lambda _, template_id=template.id: self._record(template_id, False)
            )
            capture = QtWidgets.QToolButton()
            capture.setText("▣")
            capture.setToolTip("记录并保存当前画面")
            capture.clicked.connect(
                lambda _, template_id=template.id: self._record(template_id, True)
            )
            row.addWidget(record)
            row.addWidget(capture)
            self.layout.insertWidget(self.layout.count() - 1, card)

    def _record(self, template_id: str, capture: bool) -> None:
        self.template_selected.emit(template_id)
        self.record_requested.emit(template_id, capture)

    def _clear(self) -> None:
        while self.layout.count() > 1:
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()


class TemplateEditorDialog(QtWidgets.QDialog):
    """Small project-template editor used by both phase and task pages."""

    def __init__(
        self,
        category: str,
        template: Optional[TemplateItem] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(parent)
        self.category = category
        self.template = template
        category_name = "阶段" if category == "phase" else "动作"
        self.setWindowTitle(f"{'编辑' if template else '新增'}{category_name}标签")
        self.setMinimumWidth(460)

        root = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)

        self.label_edit = QtWidgets.QLineEdit(template.label if template else "")
        self.label_edit.setPlaceholderText(f"输入{category_name}标签名称")
        form.addRow("标签名称 *", self.label_edit)

        self.group_edit = QtWidgets.QLineEdit(template.group if template else "默认分组")
        self.group_edit.setPlaceholderText("默认分组")
        form.addRow("分组", self.group_edit)

        self.start_hint_edit = QtWidgets.QLineEdit(template.start_hint if template else "")
        self.start_hint_edit.setPlaceholderText("可选：如何判断该区间开始")
        form.addRow("开始提示", self.start_hint_edit)

        self.end_hint_edit = QtWidgets.QLineEdit(template.end_hint if template else "")
        self.end_hint_edit.setPlaceholderText("可选：如何判断该区间结束")
        form.addRow("结束提示", self.end_hint_edit)

        self.required_check = QtWidgets.QCheckBox("数据检查时提示该标签是否缺失")
        self.required_check.setChecked(bool(template.required) if template else False)
        form.addRow("必填", self.required_check)
        root.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.label_edit.setFocus()
        self.label_edit.selectAll()

    def accept(self) -> None:
        if not self.label_edit.text().strip():
            QtWidgets.QMessageBox.warning(self, "标签名称为空", "请输入标签名称。")
            self.label_edit.setFocus()
            return
        super().accept()

    def values(self) -> Dict[str, object]:
        return {
            "label": self.label_edit.text().strip(),
            "group": self.group_edit.text().strip() or "默认分组",
            "start_hint": self.start_hint_edit.text().strip(),
            "end_hint": self.end_hint_edit.text().strip(),
            "required": self.required_check.isChecked(),
        }


class EditAnnotationDialog(QtWidgets.QDialog):
    """An explicit editor for a historical record."""

    def __init__(
        self,
        annotation: Annotation,
        template: Optional[TemplateItem],
        parent: Optional[QtWidgets.QWidget] = None,
        duration_ms: int = 0,
        fps: float = 0.0,
        templates: Optional[Iterable[TemplateItem]] = None,
        current_position_ms: int = 0,
    ):
        super().__init__(parent)
        self.annotation = annotation
        self.template = template
        self.duration_ms = max(0, int(duration_ms))
        self.fps = fps if fps > 0 else 25.0
        self.current_position_ms = max(0, int(current_position_ms))
        if self.duration_ms:
            self.current_position_ms = min(self.current_position_ms, self.duration_ms)
        self.editable_templates = [
            item for item in (templates or ([template] if template else []))
            if item and item.kind == annotation.kind
        ]
        if template and not any(item.id == template.id for item in self.editable_templates):
            self.editable_templates.insert(0, template)
        self.setWindowTitle("编辑标注")
        self.setMinimumWidth(420)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        form.setSpacing(spacing_pixels("md"))

        self.template_combo = QtWidgets.QComboBox()
        for item in self.editable_templates:
            caption = f"{item.label}  ·  {item.category}" if item.category else item.label
            self.template_combo.addItem(caption, item.id)
        template_index = self.template_combo.findData(annotation.template_id)
        if template_index >= 0:
            self.template_combo.setCurrentIndex(template_index)
        self.template_combo.setEnabled(self.template_combo.count() > 1)
        self.template_combo.setToolTip("只能更换为相同标注类型的标签。")
        form.addRow("标签", self.template_combo)

        self.start = QtWidgets.QLineEdit(format_timecode(annotation.start_ms))
        self.start.setPlaceholderText("00:00:00.000")
        self.end = QtWidgets.QLineEdit(format_timecode(annotation.end_ms))
        self.end.setPlaceholderText("00:00:00.000")
        if annotation.kind != "rating":
            form.addRow("开始", self._time_editor(self.start, "start"))
        else:
            form.addRow("时间", QtWidgets.QLabel("评分不关联视频时间"))
        if annotation.kind == "interval":
            form.addRow("结束", self._time_editor(self.end, "end"))

        self.score = QtWidgets.QComboBox()
        if annotation.kind == "rating":
            self._populate_score_options(annotation.score)
            self.template_combo.currentIndexChanged.connect(
                lambda _index: self._populate_score_options()
            )
            form.addRow("评分", self.score)

        self.status = QtWidgets.QComboBox()
        for value, title in (("draft", "草稿"), ("ready", "待审核"), ("reviewed", "已审核")):
            self.status.addItem(title, value)
        self.status.setCurrentIndex(max(0, self.status.findData(annotation.status)))
        form.addRow("状态", self.status)

        self.note = QtWidgets.QPlainTextEdit(annotation.note)
        self.note.setPlaceholderText("可选备注，例如异常情况或审核说明")
        self.note.setFixedHeight(84)
        form.addRow("备注", self.note)

        self.keep_asset: Optional[QtWidgets.QCheckBox] = None
        if annotation.kind == "point" and annotation.asset_path:
            self.keep_asset = QtWidgets.QCheckBox("保留关联画面（它仍对应原记录时刻）")
            self.keep_asset.setChecked(True)
            self.keep_asset.setToolTip("取消后只会解除标注关联，不会删除截图文件。")
            form.addRow("截图", self.keep_asset)
        layout.addLayout(form)

        self.error = QtWidgets.QLabel()
        self.error.setObjectName("ErrorText")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _time_editor(self, editor: QtWidgets.QLineEdit, role: str) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(spacing_pixels("sm"))
        row.addWidget(editor, 1)
        use_current = QtWidgets.QPushButton("使用当前")
        use_current.setToolTip(
            f"填入当前播放位置 {format_timecode(self.current_position_ms)}"
        )
        use_current.clicked.connect(
            lambda: editor.setText(format_timecode(self.current_position_ms))
        )
        setattr(self, f"use_current_{role}_button", use_current)
        row.addWidget(use_current)
        return container

    def _selected_template(self) -> Optional[TemplateItem]:
        template_id = self.template_combo.currentData()
        return next(
            (item for item in self.editable_templates if item.id == template_id),
            None,
        )

    def _populate_score_options(self, preferred: Optional[int] = None) -> None:
        if preferred is None and self.score.count():
            preferred = int(self.score.currentData())
        self.score.clear()
        template = self._selected_template()
        if not template:
            return
        for score in template.score_options:
            self.score.addItem(str(score), score)
        index = self.score.findData(preferred)
        self.score.setCurrentIndex(index if index >= 0 else 0)

    def values(self) -> Dict[str, object]:
        values: Dict[str, object] = {
            "note": self.note.toPlainText().strip(),
            "status": self.status.currentData(),
        }
        if self.template_combo.count():
            values["template_id"] = str(self.template_combo.currentData())
        if self.annotation.kind != "rating":
            values["start_ms"] = parse_timecode(self.start.text())
        if self.annotation.kind == "interval":
            values["end_ms"] = parse_timecode(self.end.text())
        if self.annotation.kind == "rating" and self.score.count():
            values["score"] = int(self.score.currentData())
        if self.annotation.kind == "point":
            values["frame"] = int(round((int(values["start_ms"]) / 1_000) * self.fps))
            if self.keep_asset and not self.keep_asset.isChecked():
                values["asset_path"] = ""
        return values

    def _validate(self) -> None:
        try:
            if not self._selected_template():
                raise ValueError("请选择有效标签")
            if self.annotation.kind == "rating" and not self.score.count():
                raise ValueError("目标评分标签没有可选分值")
            values = self.values()
            if (
                self.annotation.kind == "interval"
                and int(values["end_ms"]) < int(values["start_ms"])
            ):
                raise ValueError("结束时间必须晚于或等于开始时间")
            if "start_ms" in values and int(values["start_ms"]) < 0:
                raise ValueError("开始时间不能为负数")
            if self.duration_ms:
                if "start_ms" in values and int(values["start_ms"]) > self.duration_ms:
                    raise ValueError("开始时间不能超过视频时长")
                if "end_ms" in values and int(values["end_ms"]) > self.duration_ms:
                    raise ValueError("结束时间不能超过视频时长")
        except (ValueError, TypeError) as error:
            self.error.setText(str(error))
            return
        self.accept()


class ValidationReportDialog(QtWidgets.QDialog):
    """A concise, non-destructive pre-export quality report."""

    def __init__(self, issues: List[ValidationIssue], parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("数据检查")
        self.setMinimumSize(520, 280)
        layout = QtWidgets.QVBoxLayout(self)
        errors = sum(item.severity == "error" for item in issues)
        warnings = sum(item.severity == "warning" for item in issues)
        summary = QtWidgets.QLabel(
            "检查通过，可以导出。" if not issues else f"发现 {errors} 个错误、{warnings} 个提示。"
        )
        summary.setObjectName("ValidationSummary")
        summary.setProperty(
            "severity", "error" if errors else "warning" if warnings else "ok"
        )
        layout.addWidget(summary)
        table = QtWidgets.QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["级别", "说明"])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for issue in issues:
            row = table.rowCount()
            table.insertRow(row)
            level = "错误" if issue.severity == "error" else "提示"
            first = QtWidgets.QTableWidgetItem(level)
            first.setForeground(
                QtGui.QBrush(
                    QtGui.QColor(
                        COLOURS["danger_text" if issue.severity == "error" else "warning_text"]
                    )
                )
            )
            table.setItem(row, 0, first)
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(issue.message))
        layout.addWidget(table, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


class AnnotationWindow(QtWidgets.QMainWindow):
    """The product-oriented main window."""

    def __init__(self) -> None:
        super().__init__()
        self.settings = QtCore.QSettings("SurgiAnnotate", "SurgiAnnotate")
        requested_theme = self.settings.value("appearance/theme", DEFAULT_THEME, type=str)
        self.theme_id = DEFAULT_THEME
        self._apply_application_theme(requested_theme)
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(1100, 720)
        self.resize(1440, 920)

        configured_root = self.settings.value(
            "output_root", str(ROOT_DIRECTORY / "outputs"), type=str
        )
        self.output_root = Path(configured_root)
        self.video_path: Optional[Path] = None
        self.store: Optional[ProjectStore] = None
        self.templates: List[TemplateItem] = default_templates(ROOT_DIRECTORY)
        self.active_template_id: Optional[str] = None
        self.pending_interval: Optional[Tuple[str, int]] = None
        self._last_position = 0
        self._closing = False

        self._save_timer = QtCore.QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(350)
        self._save_timer.timeout.connect(self._save_project)

        self._build_actions()
        self._build_window()
        self._build_menus()
        self._bind_annotation_shortcuts()
        self._build_toolbar()
        self._refresh_template_pages()
        self._refresh_project_views()

        app = QtWidgets.QApplication.instance()
        if app:
            app.installEventFilter(self)

    def _apply_application_theme(self, theme_id: str) -> None:
        """Apply an approved DESIGN.md theme to the whole Qt application."""
        requested = theme_id if theme_id in THEME_LABELS else DEFAULT_THEME
        try:
            tokens = activate_theme(requested)
        except ValueError:
            tokens = activate_theme(DEFAULT_THEME)
        self.theme_id = tokens.identifier
        app = QtWidgets.QApplication.instance()
        if app:
            app.setStyle("Fusion")
            app.setPalette(build_palette(self.theme_id))
            app.setStyleSheet("")
            app.setStyleSheet(build_stylesheet(self.theme_id))
        if hasattr(self, "open_action"):
            self._refresh_action_icons()

    def apply_theme(self, theme_id: str) -> None:
        if theme_id not in THEME_LABELS:
            return
        self._apply_application_theme(theme_id)
        self.settings.setValue("appearance/theme", self.theme_id)
        if hasattr(self, "theme_actions"):
            action = self.theme_actions.get(self.theme_id)
            if action:
                action.setChecked(True)
        if hasattr(self, "timeline"):
            self._refresh_template_pages()
            self._refresh_project_views()
            self.timeline.update()
        self._info(f"已切换为 {THEME_LABELS[self.theme_id]}")

    def _themed_standard_icon(
        self, standard_icon: QtWidgets.QStyle.StandardPixmap, colour_key: str = "primary"
    ) -> QtGui.QIcon:
        """Tint a native glyph with an active semantic token, including disabled state."""
        size = QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg"))
        source = self.style().standardIcon(standard_icon).pixmap(size)

        def tinted(colour: str) -> QtGui.QPixmap:
            result = QtGui.QPixmap(source.size())
            result.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(result)
            painter.drawPixmap(0, 0, source)
            painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
            painter.fillRect(result.rect(), QtGui.QColor(colour))
            painter.end()
            return result

        icon = QtGui.QIcon()
        icon.addPixmap(tinted(COLOURS[colour_key]), QtGui.QIcon.Normal)
        icon.addPixmap(tinted(COLOURS["disabled"]), QtGui.QIcon.Disabled)
        return icon

    def _refresh_action_icons(self) -> None:
        self.open_action.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogOpenButton)
        )
        self.save_action.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogSaveButton)
        )
        self.export_action.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogSaveButton)
        )
        self.undo_action.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_ArrowBack, "muted")
        )
        self.redo_action.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_ArrowForward, "muted")
        )
        self.capture_action.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogSaveButton)
        )
        for name, standard_icon in (
            ("back_seconds_button", QtWidgets.QStyle.SP_MediaSeekBackward),
            ("back_frame_button", QtWidgets.QStyle.SP_MediaSkipBackward),
            ("forward_frame_button", QtWidgets.QStyle.SP_MediaSkipForward),
            ("forward_seconds_button", QtWidgets.QStyle.SP_MediaSeekForward),
            ("capture_button", QtWidgets.QStyle.SP_DialogSaveButton),
            ("timeline_pan_left", QtWidgets.QStyle.SP_ArrowBack),
            ("timeline_pan_right", QtWidgets.QStyle.SP_ArrowForward),
        ):
            if hasattr(self, name):
                getattr(self, name).setIcon(self._themed_standard_icon(standard_icon))
        if hasattr(self, "play_button"):
            self._on_playback_changed(self.backend.is_playing)

    def _build_actions(self) -> None:
        self.open_action = QtWidgets.QAction(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogOpenButton), "打开视频", self
        )
        self.open_action.setShortcut("Ctrl+O")
        self.open_action.triggered.connect(self.open_video)

        self.open_project_action = QtWidgets.QAction("打开项目…", self)
        self.open_project_action.setShortcut("Ctrl+Shift+O")
        self.open_project_action.triggered.connect(self.open_project)

        self.save_action = QtWidgets.QAction(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogSaveButton), "立即保存", self
        )
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.triggered.connect(self._save_project)

        self.export_action = QtWidgets.QAction(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogSaveButton), "导出数据…", self
        )
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.triggered.connect(self.export_project)

        self.undo_action = QtWidgets.QAction(
            self._themed_standard_icon(QtWidgets.QStyle.SP_ArrowBack, "muted"), "撤销", self
        )
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self.undo)
        self.redo_action = QtWidgets.QAction(
            self._themed_standard_icon(QtWidgets.QStyle.SP_ArrowForward, "muted"), "重做", self
        )
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        self.redo_action.triggered.connect(self.redo)

        self.capture_action = QtWidgets.QAction(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogSaveButton), "保存当前画面", self
        )
        self.capture_action.setShortcut("F")
        self.capture_action.triggered.connect(self.capture_current_frame)
        self.extract_frames_action = QtWidgets.QAction("批量提取标注关键帧…", self)
        self.extract_frames_action.triggered.connect(self.extract_annotation_frames)

        self.validate_action = QtWidgets.QAction("数据检查", self)
        self.validate_action.triggered.connect(self.show_validation)
        self.shortcuts_action = QtWidgets.QAction("快捷键说明", self)
        self.shortcuts_action.setShortcut("F1")
        self.shortcuts_action.triggered.connect(self.show_shortcuts)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.open_project_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.export_action)
        file_menu.addSeparator()
        choose_root = QtWidgets.QAction("更改输出位置…", self)
        choose_root.triggered.connect(self.change_output_directory)
        file_menu.addAction(choose_root)
        import_legacy = QtWidgets.QAction("导入旧版 TXT 标注…", self)
        import_legacy.triggered.connect(self.import_legacy)
        file_menu.addAction(import_legacy)
        file_menu.addSeparator()
        exit_action = QtWidgets.QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = self.menuBar().addMenu("编辑")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        self.edit_annotation_action = QtWidgets.QAction("编辑选中标注…", self)
        self.edit_annotation_action.setShortcuts(
            [
                QtGui.QKeySequence(QtCore.Qt.Key_Return),
                QtGui.QKeySequence(QtCore.Qt.Key_Enter),
            ]
        )
        self.edit_annotation_action.triggered.connect(self.edit_selected_annotation)
        edit_menu.addAction(self.edit_annotation_action)
        self.delete_annotation_action = QtWidgets.QAction("删除选中标注", self)
        self.delete_annotation_action.setShortcut("Delete")
        self.delete_annotation_action.triggered.connect(self.delete_selected_annotation)
        edit_menu.addAction(self.delete_annotation_action)

        template_menu = self.menuBar().addMenu("模板")
        add_phase_template = QtWidgets.QAction("新增阶段标签…", self)
        add_phase_template.triggered.connect(
            lambda _checked=False: self.add_interval_template("phase")
        )
        template_menu.addAction(add_phase_template)
        add_task_template = QtWidgets.QAction("新增动作标签…", self)
        add_task_template.triggered.connect(
            lambda _checked=False: self.add_interval_template("task")
        )
        template_menu.addAction(add_task_template)
        template_menu.addSeparator()
        phase_template = QtWidgets.QAction("导入阶段标签…", self)
        phase_template.triggered.connect(self.load_phase_template)
        template_menu.addAction(phase_template)
        task_template = QtWidgets.QAction("导入动作标签…", self)
        task_template.triggered.connect(self.load_task_template)
        template_menu.addAction(task_template)
        rating_template = QtWidgets.QAction("导入评分/关键帧模板…", self)
        rating_template.triggered.connect(self.load_rating_template)
        template_menu.addAction(rating_template)
        template_menu.addSeparator()
        reset_templates = QtWidgets.QAction("恢复内置模板", self)
        reset_templates.triggered.connect(self.restore_default_templates)
        template_menu.addAction(reset_templates)

        view_menu = self.menuBar().addMenu("视图")
        appearance_menu = view_menu.addMenu("外观主题")
        self.theme_action_group = QtWidgets.QActionGroup(self)
        self.theme_action_group.setExclusive(True)
        self.theme_actions: Dict[str, QtWidgets.QAction] = {}
        for theme_id, label in THEME_LABELS.items():
            action = QtWidgets.QAction(label, self, checkable=True)
            action.setChecked(theme_id == self.theme_id)
            action.triggered.connect(
                lambda checked, selected_theme=theme_id: checked
                and self.apply_theme(selected_theme)
            )
            self.theme_action_group.addAction(action)
            appearance_menu.addAction(action)
            self.theme_actions[theme_id] = action

        quality_menu = self.menuBar().addMenu("质量")
        quality_menu.addAction(self.validate_action)
        quality_menu.addAction(self.extract_frames_action)
        labelme_action = QtWidgets.QAction("用 LabelMe 打开选中画面", self)
        labelme_action.triggered.connect(self.open_selected_in_labelme)
        quality_menu.addAction(labelme_action)

        help_menu = self.menuBar().addMenu("帮助")
        help_menu.addAction(self.shortcuts_action)
        about_action = QtWidgets.QAction("关于 SurgiAnnotate", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _bind_annotation_shortcuts(self) -> None:
        """Limit record editing shortcuts to the record table and its viewport."""
        for action in (self.edit_annotation_action, self.delete_annotation_action):
            action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
            self.annotation_table.addAction(action)

    def _build_toolbar(self) -> None:
        toolbar = QtWidgets.QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg")))
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.addToolBar(toolbar)

        brand = QtWidgets.QLabel("SurgiAnnotate")
        brand.setObjectName("Brand")
        toolbar.addWidget(brand)
        toolbar.addSeparator()
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addAction(self.export_action)
        toolbar.addSeparator()

        self.case_title = QtWidgets.QLabel("尚未打开病例")
        self.case_title.setObjectName("CaseTitle")
        self.case_title.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred
        )
        toolbar.addWidget(self.case_title)

        self.progress = QtWidgets.QProgressBar()
        self.progress.setFixedWidth(spacing_pixels("xxl") * 7)
        self.progress.setFixedHeight(spacing_pixels("lg"))
        self.progress.setTextVisible(True)
        toolbar.addWidget(self.progress)

        self.save_state = QtWidgets.QLabel("准备就绪")
        self.save_state.setObjectName("StatusPill")
        toolbar.addWidget(self.save_state)

    def _build_window(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(
            spacing_pixels("md"),
            spacing_pixels("md"),
            spacing_pixels("md"),
            spacing_pixels("sm"),
        )
        root.setSpacing(spacing_pixels("md"))

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        root.addWidget(self.main_splitter, 1)

        video_pane = self._build_video_pane()
        video_pane.setMinimumWidth(520)
        self.main_splitter.addWidget(video_pane)
        annotation_pane = self._build_annotation_pane()
        annotation_pane.setMinimumWidth(500)
        self.main_splitter.addWidget(annotation_pane)
        self.main_splitter.setStretchFactor(0, 4)
        self.main_splitter.setStretchFactor(1, 3)
        self.main_splitter.setSizes([780, 620])
        saved_splitter = self.settings.value("layout/main_splitter_v2")
        if saved_splitter:
            self.main_splitter.restoreState(saved_splitter)

        self.status_message = QtWidgets.QLabel("打开视频后即可开始标注。")
        self.status_message.setObjectName("Muted")
        self.output_path_label = QtWidgets.QLabel(f"输出：{self.output_root}")
        self.output_path_label.setObjectName("Muted")
        self.statusBar().addWidget(self.status_message, 1)
        self.statusBar().addPermanentWidget(self.output_path_label)

    def _build_video_pane(self) -> QtWidgets.QWidget:
        pane = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing_pixels("sm"))

        heading = QtWidgets.QHBoxLayout()
        section = QtWidgets.QLabel("视频工作台")
        section.setObjectName("SectionCaption")
        heading.addWidget(section)
        heading.addStretch()
        self.backend_label = QtWidgets.QLabel("播放器：正在初始化")
        self.backend_label.setObjectName("Muted")
        heading.addWidget(self.backend_label)
        layout.addLayout(heading)

        stage = QtWidgets.QFrame()
        stage.setObjectName("VideoStage")
        stage_layout = QtWidgets.QVBoxLayout(stage)
        stage_layout.setContentsMargins(1, 1, 1, 1)
        self.video_widget = QtMultimediaWidgets.QVideoWidget()
        self.video_widget.setObjectName("VideoSurface")
        self.video_widget.setMinimumHeight(390)
        self.video_widget.setAttribute(QtCore.Qt.WA_NativeWindow, True)
        self.video_widget.installEventFilter(self)
        stage_layout.addWidget(self.video_widget)
        layout.addWidget(stage, 1)

        self.backend = VideoBackend(self.video_widget, self)
        self.backend.position_changed.connect(self._on_player_position)
        self.backend.duration_changed.connect(self._on_player_duration)
        self.backend.playback_changed.connect(self._on_playback_changed)
        self.backend.error_occurred.connect(self._show_player_error)
        self.backend_label.setText(f"播放器：{self.backend.backend_name}")

        controls = QtWidgets.QFrame()
        controls.setObjectName("Panel")
        controls_layout = QtWidgets.QVBoxLayout(controls)
        controls_layout.setContentsMargins(
            spacing_pixels("md"),
            spacing_pixels("sm"),
            spacing_pixels("md"),
            spacing_pixels("sm"),
        )
        controls_layout.setSpacing(spacing_pixels("xs"))

        transport_row = QtWidgets.QHBoxLayout()
        transport_row.setSpacing(spacing_pixels("sm"))
        transport_row.addStretch()

        self.back_seconds_button = QtWidgets.QToolButton()
        self.back_seconds_button.setObjectName("TransportWideButton")
        self.back_seconds_button.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_MediaSeekBackward)
        )
        self.back_seconds_button.setIconSize(
            QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg"))
        )
        self.back_seconds_button.setText("5s")
        self.back_seconds_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.back_seconds_button.setToolTip("后退 5 秒 (Ctrl+←)")
        self.back_seconds_button.setAccessibleName("后退 5 秒")
        self.back_seconds_button.clicked.connect(lambda: self.backend.step_seconds(-5))
        transport_row.addWidget(self.back_seconds_button)

        self.back_frame_button = QtWidgets.QToolButton()
        self.back_frame_button.setObjectName("TransportButton")
        self.back_frame_button.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_MediaSkipBackward)
        )
        self.back_frame_button.setIconSize(
            QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg"))
        )
        self.back_frame_button.setToolTip("前一帧 (←)")
        self.back_frame_button.setAccessibleName("前一帧")
        self.back_frame_button.clicked.connect(lambda: self.backend.step_frames(-1))
        transport_row.addWidget(self.back_frame_button)

        self.play_button = QtWidgets.QToolButton()
        self.play_button.setObjectName("PlayButton")
        self.play_button.setIconSize(
            QtCore.QSize(spacing_pixels("xl"), spacing_pixels("xl"))
        )
        self.play_button.setToolTip("播放/暂停 (Space)")
        self.play_button.setAccessibleName("播放或暂停")
        self.play_button.clicked.connect(self.toggle_playback)
        transport_row.addWidget(self.play_button)

        self.forward_frame_button = QtWidgets.QToolButton()
        self.forward_frame_button.setObjectName("TransportButton")
        self.forward_frame_button.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_MediaSkipForward)
        )
        self.forward_frame_button.setIconSize(
            QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg"))
        )
        self.forward_frame_button.setToolTip("后一帧 (→)")
        self.forward_frame_button.setAccessibleName("后一帧")
        self.forward_frame_button.clicked.connect(lambda: self.backend.step_frames(1))
        transport_row.addWidget(self.forward_frame_button)

        self.forward_seconds_button = QtWidgets.QToolButton()
        self.forward_seconds_button.setObjectName("TransportWideButton")
        self.forward_seconds_button.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_MediaSeekForward)
        )
        self.forward_seconds_button.setIconSize(
            QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg"))
        )
        self.forward_seconds_button.setText("5s")
        self.forward_seconds_button.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.forward_seconds_button.setToolTip("前进 5 秒 (Ctrl+→)")
        self.forward_seconds_button.setAccessibleName("前进 5 秒")
        self.forward_seconds_button.clicked.connect(lambda: self.backend.step_seconds(5))
        transport_row.addWidget(self.forward_seconds_button)
        transport_row.addStretch()
        controls_layout.addLayout(transport_row)

        metadata_row = QtWidgets.QHBoxLayout()
        metadata_row.setSpacing(spacing_pixels("sm"))
        speed_caption = QtWidgets.QLabel("速度")
        speed_caption.setObjectName("Muted")
        metadata_row.addWidget(speed_caption)
        self.speed = QtWidgets.QComboBox()
        self.speed.addItem("0.5×", 0.5)
        self.speed.addItem("0.75×", 0.75)
        self.speed.addItem("1.0×", 1.0)
        self.speed.addItem("1.5×", 1.5)
        self.speed.addItem("2.0×", 2.0)
        self.speed.setCurrentIndex(2)
        self.speed.setFixedWidth(spacing_pixels("xxl") * 2 + spacing_pixels("sm"))
        self.speed.currentIndexChanged.connect(
            lambda _: self.backend.set_rate(float(self.speed.currentData()))
        )
        metadata_row.addWidget(self.speed)
        metadata_row.addStretch()

        self.position_label = QtWidgets.QLabel("00:00:00.000")
        self.position_label.setObjectName("Timecode")
        self.position_label.setMinimumWidth(
            spacing_pixels("xxl") * 3 + spacing_pixels("md")
        )
        self.position_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        metadata_row.addWidget(self.position_label)
        duration_caption = QtWidgets.QLabel("/")
        duration_caption.setObjectName("Muted")
        metadata_row.addWidget(duration_caption)
        self.duration_label = QtWidgets.QLabel("00:00:00.000")
        self.duration_label.setObjectName("TimecodeMuted")
        self.duration_label.setMinimumWidth(
            spacing_pixels("xxl") * 3 + spacing_pixels("md")
        )
        metadata_row.addWidget(self.duration_label)
        metadata_row.addStretch()

        self.capture_button = QtWidgets.QPushButton("截取画面")
        self.capture_button.setObjectName("CaptureButton")
        self.capture_button.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_DialogSaveButton)
        )
        self.capture_button.setIconSize(
            QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg"))
        )
        self.capture_button.setToolTip("保存当前画面 (F)")
        self.capture_button.clicked.connect(self.capture_current_frame)
        metadata_row.addWidget(self.capture_button)
        controls_layout.addLayout(metadata_row)
        layout.addWidget(controls)

        timeline_card = QtWidgets.QFrame()
        timeline_card.setObjectName("Panel")
        timeline_layout = QtWidgets.QVBoxLayout(timeline_card)
        timeline_layout.setContentsMargins(
            spacing_pixels("md"),
            spacing_pixels("xs"),
            spacing_pixels("md"),
            spacing_pixels("xs"),
        )
        self.timeline = AnnotationTimeline()
        self.timeline.seek_requested.connect(self.backend.seek)
        self.timeline.annotation_selected.connect(
            self._select_annotation_from_timeline
        )
        timeline_layout.addWidget(self.timeline)
        legend = QtWidgets.QHBoxLayout()
        for object_name, caption in (
            ("LegendPhase", "阶段"),
            ("LegendTask", "动作"),
            ("LegendKeyframe", "关键帧"),
        ):
            dot = QtWidgets.QLabel("●")
            dot.setObjectName(object_name)
            legend.addWidget(dot)
            text = QtWidgets.QLabel(caption)
            text.setObjectName("Muted")
            legend.addWidget(text)
        legend.addStretch()
        self.timeline_pan_left = QtWidgets.QToolButton()
        self.timeline_pan_left.setObjectName("TimelineToolButton")
        self.timeline_pan_left.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_ArrowBack)
        )
        self.timeline_pan_left.setIconSize(
            QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg"))
        )
        self.timeline_pan_left.setToolTip("向前平移时间轴视窗")
        self.timeline_pan_left.setAccessibleName("向前平移时间轴")
        self.timeline_pan_left.clicked.connect(lambda: self.timeline.pan(-1))
        legend.addWidget(self.timeline_pan_left)
        zoom_out = QtWidgets.QToolButton()
        zoom_out.setObjectName("TimelineToolButton")
        zoom_out.setText("−")
        zoom_out.setToolTip("缩小时间轴 (Ctrl+滚轮向下)")
        zoom_out.clicked.connect(self.timeline.zoom_out)
        legend.addWidget(zoom_out)
        self.timeline_zoom = QtWidgets.QToolButton()
        self.timeline_zoom.setObjectName("TimelineZoomButton")
        self.timeline_zoom.setText("1×")
        self.timeline_zoom.setToolTip("恢复完整时间轴")
        self.timeline_zoom.clicked.connect(self.timeline.reset_zoom)
        legend.addWidget(self.timeline_zoom)
        zoom_in = QtWidgets.QToolButton()
        zoom_in.setObjectName("TimelineToolButton")
        zoom_in.setText("+")
        zoom_in.setToolTip("放大时间轴 (Ctrl+滚轮向上)")
        zoom_in.clicked.connect(self.timeline.zoom_in)
        legend.addWidget(zoom_in)
        self.timeline_pan_right = QtWidgets.QToolButton()
        self.timeline_pan_right.setObjectName("TimelineToolButton")
        self.timeline_pan_right.setIcon(
            self._themed_standard_icon(QtWidgets.QStyle.SP_ArrowForward)
        )
        self.timeline_pan_right.setIconSize(
            QtCore.QSize(spacing_pixels("lg"), spacing_pixels("lg"))
        )
        self.timeline_pan_right.setToolTip("向后平移时间轴视窗")
        self.timeline_pan_right.setAccessibleName("向后平移时间轴")
        self.timeline_pan_right.clicked.connect(lambda: self.timeline.pan(1))
        legend.addWidget(self.timeline_pan_right)
        self.timeline.zoom_changed.connect(
            lambda factor: self.timeline_zoom.setText(f"{factor}×")
        )
        timeline_layout.addLayout(legend)
        timeline_card.setToolTip(
            "拖动定位 · 点击标记选择 · Ctrl+滚轮缩放 · Shift+滚轮平移"
        )
        layout.addWidget(timeline_card)

        self._on_playback_changed(False)
        return pane

    def _build_annotation_pane(self) -> QtWidgets.QWidget:
        pane = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(spacing_pixels("sm"))

        controls = QtWidgets.QFrame()
        controls.setObjectName("AnnotationControls")
        control_layout = QtWidgets.QVBoxLayout(controls)
        control_layout.setContentsMargins(
            spacing_pixels("sm"),
            spacing_pixels("sm"),
            spacing_pixels("sm"),
            spacing_pixels("sm"),
        )
        control_layout.setSpacing(spacing_pixels("xs"))
        current_header = QtWidgets.QHBoxLayout()
        current_header.setSpacing(spacing_pixels("sm"))
        caption = QtWidgets.QLabel("当前标注")
        caption.setObjectName("SectionCaption")
        current_header.addWidget(caption)
        self.active_label = QtWidgets.QLabel("从“阶段”或“动作”中选择一个标签")
        self.active_label.setObjectName("ActiveLabel")
        self.active_label.setWordWrap(True)
        current_header.addWidget(self.active_label, 1)
        control_layout.addLayout(current_header)
        self.pending_label = QtWidgets.QLabel("选择标签后按 I 记录开始，按 O 记录结束。")
        self.pending_label.setObjectName("Muted")
        self.pending_label.setWordWrap(True)
        control_layout.addWidget(self.pending_label)
        buttons = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("记录开始  I")
        self.start_button.setObjectName("IntervalActionButton")
        self.start_button.setProperty("accent", True)
        self.start_button.clicked.connect(self.mark_start)
        self.end_button = QtWidgets.QPushButton("记录结束  O")
        self.end_button.setObjectName("IntervalActionButton")
        self.end_button.setProperty("success", True)
        self.end_button.clicked.connect(self.mark_end)
        self.cancel_draft_button = QtWidgets.QToolButton()
        self.cancel_draft_button.setObjectName("CancelDraftButton")
        self.cancel_draft_button.setText("取消")
        self.cancel_draft_button.setToolTip("取消当前未完成的区间")
        self.cancel_draft_button.clicked.connect(self.cancel_pending_interval)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.end_button)
        buttons.addWidget(self.cancel_draft_button)
        control_layout.addLayout(buttons)
        layout.addWidget(controls)

        self.template_tabs = QtWidgets.QTabWidget()
        self.template_tabs.setObjectName("TemplateTabs")
        self.template_tabs.setMinimumHeight(180)
        self.phase_page = LabelTreePage("没有阶段标签。请导入阶段/动作模板。")
        self.task_page = LabelTreePage("没有动作标签。请导入阶段/动作模板。")
        self.rating_page = RatingPage()
        self.point_page = PointPage()
        self.template_tabs.addTab(self.phase_page, "阶段")
        self.template_tabs.addTab(self.task_page, "动作")
        self.template_tabs.addTab(self.rating_page, "评分")
        self.template_tabs.addTab(self.point_page, "关键帧")
        self.phase_page.template_selected.connect(self.select_template)
        self.task_page.template_selected.connect(self.select_template)
        self.phase_page.add_requested.connect(
            lambda: self.add_interval_template("phase")
        )
        self.task_page.add_requested.connect(
            lambda: self.add_interval_template("task")
        )
        self.phase_page.edit_requested.connect(self.edit_interval_template)
        self.task_page.edit_requested.connect(self.edit_interval_template)
        self.phase_page.delete_requested.connect(self.delete_interval_template)
        self.task_page.delete_requested.connect(self.delete_interval_template)
        self.phase_page.import_requested.connect(self.load_phase_template)
        self.task_page.import_requested.connect(self.load_task_template)
        self.rating_page.score_selected.connect(self.set_rating)
        self.point_page.template_selected.connect(self.select_template)
        self.point_page.record_requested.connect(self.record_point)
        records = QtWidgets.QFrame()
        records.setObjectName("Panel")
        records_layout = QtWidgets.QVBoxLayout(records)
        records_layout.setContentsMargins(
            spacing_pixels("md"),
            spacing_pixels("sm"),
            spacing_pixels("md"),
            spacing_pixels("md"),
        )
        record_header = QtWidgets.QHBoxLayout()
        caption = QtWidgets.QLabel("标注记录")
        caption.setObjectName("SectionCaption")
        record_header.addWidget(caption)
        record_header.addStretch()
        self.record_count = QtWidgets.QLabel("0 条")
        self.record_count.setObjectName("Muted")
        record_header.addWidget(self.record_count)
        records_layout.addLayout(record_header)
        self.record_filter = QtWidgets.QLineEdit()
        self.record_filter.setPlaceholderText("筛选标签、类型或备注…")
        self.record_filter.setClearButtonEnabled(True)
        self.record_filter.textChanged.connect(self._refresh_annotation_table)
        records_layout.addWidget(self.record_filter)
        self.annotation_table = QtWidgets.QTableWidget(0, 5)
        self.annotation_table.setHorizontalHeaderLabels(["类型", "标签", "开始", "结束/分数", "状态"])
        self.annotation_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.annotation_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.annotation_table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.annotation_table.setAlternatingRowColors(True)
        self.annotation_table.setShowGrid(False)
        self.annotation_table.setSortingEnabled(True)
        self.annotation_table.verticalHeader().setVisible(False)
        self.annotation_table.horizontalHeader().setStretchLastSection(True)
        header = self.annotation_table.horizontalHeader()
        header.setMinimumSectionSize(spacing_pixels("xxl"))
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QtWidgets.QHeaderView.ResizeToContents)
        self.annotation_table.setMinimumHeight(96)
        self.annotation_table.itemDoubleClicked.connect(lambda _: self.edit_selected_annotation())
        self.annotation_table.itemSelectionChanged.connect(self._update_selection_state)
        self.annotation_table.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.annotation_table.customContextMenuRequested.connect(
            self._show_annotation_context_menu
        )
        records_layout.addWidget(self.annotation_table)
        record_actions = QtWidgets.QHBoxLayout()
        self.jump_annotation_button = QtWidgets.QPushButton("跳转")
        self.jump_annotation_button.clicked.connect(self.jump_to_selected_annotation)
        self.edit_annotation_button = QtWidgets.QPushButton("编辑")
        self.edit_annotation_button.clicked.connect(self.edit_selected_annotation)
        self.delete_annotation_button = QtWidgets.QPushButton("删除")
        self.delete_annotation_button.setProperty("danger", True)
        self.delete_annotation_button.clicked.connect(self.delete_selected_annotation)
        record_actions.addWidget(self.jump_annotation_button)
        record_actions.addWidget(self.edit_annotation_button)
        record_actions.addWidget(self.delete_annotation_button)
        records_layout.addLayout(record_actions)
        self.workspace_tabs = QtWidgets.QTabWidget()
        self.workspace_tabs.setObjectName("WorkspaceTabs")
        self.workspace_tabs.tabBar().setObjectName("WorkspaceTabBar")
        self.workspace_tabs.addTab(self.template_tabs, "标签选择")
        self.workspace_tabs.addTab(records, "标注记录  0")
        layout.addWidget(self.workspace_tabs, 1)
        return pane

    def open_video(self) -> None:
        last_directory = self.settings.value("last_video_directory", str(Path.home()), type=str)
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "打开手术视频",
            last_directory,
            "视频文件 (*.mp4 *.avi *.mov *.mkv *.mpeg *.mpg *.wmv);;所有文件 (*.*)",
        )
        if filename:
            self._open_video_path(Path(filename))

    def _open_video_path(self, path: Path, loaded_store: Optional[ProjectStore] = None) -> None:
        if not path.is_file():
            self._error("找不到视频文件", str(path))
            return

        candidate_store: Optional[ProjectStore] = loaded_store
        if loaded_store:
            candidate_store = loaded_store
        else:
            destination = case_directory(self.output_root, path)
            project_path = destination / PROJECT_FILENAME
            if project_path.exists():
                choice = QtWidgets.QMessageBox.question(
                    self,
                    "发现已有项目",
                    f"已找到病例“{path.name}”的项目记录。\n\n是否继续上次的标注？",
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
                    QtWidgets.QMessageBox.Yes,
                )
                if choice == QtWidgets.QMessageBox.Cancel:
                    return
                if choice == QtWidgets.QMessageBox.Yes:
                    try:
                        candidate_store = ProjectStore.load(project_path)
                    except (OSError, ValueError) as error:
                        self._error("无法打开已有项目", str(error))
                        return
                else:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    candidate_store = ProjectStore.create(
                        destination / f"project_{timestamp}.surgui.json", path, self.templates
                    )
            else:
                candidate_store = ProjectStore.create(project_path, path, self.templates)

        if not candidate_store:
            self._error("无法创建项目", "项目初始化未返回有效数据。")
            return
        candidate_templates = self._ensure_store_templates(candidate_store)
        if self.pending_interval and self.store and not self._confirm_discard_pending_interval(
            "放弃并切换"
        ):
            return
        if self.store and self.store.is_dirty and not self._save_project():
            return

        candidate_store.clear_history()
        self.pending_interval = None
        self.video_path = path
        self.store = candidate_store
        self.templates = candidate_templates
        self.settings.setValue("last_video_directory", str(path.parent))
        self.backend.open(path)
        self.case_title.setText(path.name)
        self._refresh_template_pages()
        self._refresh_project_views()
        self._schedule_autosave()
        self._info(f"已打开 {path.name}。选择标签后即可标注。")
        if self.store.recovered_from_backup:
            source = self.store.recovery_source.name if self.store.recovery_source else "上一个备份"
            self._warning(
                "已从备份恢复项目",
                f"主项目文件无法读取，已使用 {source} 恢复当前项目。请尽快保存。",
            )

    def _ensure_store_templates(self, store: ProjectStore) -> List[TemplateItem]:
        """Persist bundled defaults instead of rendering templates absent from a project."""
        templates = store.templates
        if templates:
            return templates
        bundled = default_templates(ROOT_DIRECTORY)
        if bundled:
            store.replace_templates(bundled)
            return store.templates
        return []

    def open_project(self) -> None:
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "打开 SurgiAnnotate 项目", str(self.output_root), "项目文件 (*.json)"
        )
        if not filename:
            return
        try:
            store = ProjectStore.load(Path(filename))
        except (OSError, ValueError) as error:
            self._error("无法打开项目", str(error))
            return
        media_path = str(store.media.get("path") or "").strip()
        path = Path(media_path) if media_path else None
        relink_required = False
        if not path or not path.is_file():
            selected, _ = QtWidgets.QFileDialog.getOpenFileName(
                self,
                "原视频已移动，请重新定位",
                str(Path.home()),
                "视频文件 (*.mp4 *.avi *.mov *.mkv *.mpeg *.mpg *.wmv);;所有文件 (*.*)",
            )
            if not selected:
                return
            path = Path(selected)
            relink_required = True
        else:
            recorded_fingerprint = str(store.media.get("fingerprint") or "")
            current_fingerprint = media_fingerprint(path)
            if recorded_fingerprint and recorded_fingerprint != current_fingerprint:
                if not self._confirm_media_relink(path):
                    return
                relink_required = True
            elif not recorded_fingerprint:
                relink_required = True
        if relink_required:
            try:
                store.relink_media(path)
            except (OSError, ValueError) as error:
                self._error("无法关联视频", str(error))
                return
        self._open_video_path(path, store)

    def change_output_directory(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择项目输出位置", str(self.output_root)
        )
        if not selected:
            return
        new_root = Path(selected)
        try:
            new_root.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._error("无法使用输出位置", str(error))
            return
        if self.store and self.video_path:
            migrate = QtWidgets.QMessageBox.question(
                self,
                "迁移当前项目",
                "是否同时把当前项目复制到新的输出位置？旧项目将保留不被删除。",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes,
            )
            if migrate == QtWidgets.QMessageBox.Yes:
                if self.store.is_dirty and not self._save_project():
                    return
                target = case_directory(new_root, self.video_path)
                previous_path = self.store.path
                previous_dirty = self.store.is_dirty
                if target.resolve() != self.store.output_directory.resolve():
                    target_project = target / PROJECT_FILENAME
                    if target_project.exists():
                        overwrite = QtWidgets.QMessageBox.question(
                            self,
                            "目标已有项目",
                            "目标位置已有同病例项目。迁移会写入新的项目副本，是否继续？",
                            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel,
                            QtWidgets.QMessageBox.Cancel,
                        )
                        if overwrite != QtWidgets.QMessageBox.Yes:
                            return
                    try:
                        target.mkdir(parents=True, exist_ok=True)
                        old_images = self.store.output_directory / "images"
                        if old_images.exists():
                            shutil.copytree(old_images, target / "images", dirs_exist_ok=True)
                        self.store.set_path(target_project)
                        if not self._save_project():
                            self.store.path = previous_path
                            self.store.is_dirty = previous_dirty
                            self.save_state.setText("已保留原项目")
                            return
                    except OSError as error:
                        self.store.path = previous_path
                        self.store.is_dirty = previous_dirty
                        self._error("项目迁移失败", str(error))
                        return
        self.output_root = new_root
        self.settings.setValue("output_root", str(new_root))
        self.output_path_label.setText(f"输出：{new_root}")
        self._info(f"输出位置已更新为 {new_root}")

    def load_phase_template(self) -> None:
        self._load_interval_template("phase")

    def load_task_template(self) -> None:
        self._load_interval_template("task")

    def load_interval_template(self) -> None:
        """Compatibility entry point for callers of the former combined import."""
        category, accepted = QtWidgets.QInputDialog.getItem(
            self,
            "选择标签类型",
            "本次导入的标签属于：",
            ["阶段", "动作"],
            0,
            False,
        )
        if accepted:
            self._load_interval_template("phase" if category == "阶段" else "task")

    def _load_interval_template(self, category: str) -> None:
        if not self._require_project():
            return
        category_name = "阶段" if category == "phase" else "动作"
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            f"导入{category_name}标签",
            str(ROOT_DIRECTORY / "samples"),
            "文本文件 (*.txt)",
        )
        if not filename:
            return
        try:
            additions = parse_interval_template(Path(filename), category)
        except (OSError, UnicodeError) as error:
            self._error("无法读取模板", str(error))
            return
        if self._append_templates(additions):
            self._info(f"已导入 {len(additions)} 个{category_name}标签。")

    def add_interval_template(self, category: str) -> None:
        if not self._require_project():
            return
        dialog = TemplateEditorDialog(category, parent=self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        values = dialog.values()
        template = TemplateItem(
            id=make_id(category),
            label=str(values["label"]),
            kind="interval",
            category=category,
            group=str(values["group"]),
            start_hint=str(values["start_hint"]),
            end_hint=str(values["end_hint"]),
            source="project",
            required=bool(values["required"]),
        )
        try:
            self.store.append_templates([template])
        except ValueError as error:
            self._warning("无法新增标签", str(error))
            return
        self.active_template_id = template.id
        self._after_project_change(f"已新增标签“{template.label}”")
        self.select_template(template.id)

    def edit_interval_template(self, template_id: str) -> None:
        if not self._require_project():
            return
        template = self._template(template_id)
        if not template or template.kind != "interval":
            self._warning("无法编辑标签", "没有找到对应的阶段或动作标签。")
            return
        dialog = TemplateEditorDialog(template.category, template, self)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        try:
            updated = self.store.update_template(template_id, **dialog.values())
        except (KeyError, ValueError) as error:
            self._warning("无法编辑标签", str(error))
            return
        self._after_project_change(f"已更新标签“{updated.label}”")
        if self.active_template_id == template_id:
            self.select_template(template_id)

    def delete_interval_template(self, template_id: str) -> None:
        if not self._require_project():
            return
        template = self._template(template_id)
        if not template or template.kind != "interval":
            self._warning("无法删除标签", "没有找到对应的阶段或动作标签。")
            return
        if self.pending_interval and self.pending_interval[0] == template_id:
            self._warning("标签正在使用", "请先取消或完成当前未结束的区间，再删除该标签。")
            return
        referenced = sum(
            1 for annotation in self.store.annotations if annotation.template_id == template_id
        )
        if referenced:
            self._warning(
                "标签已有标注记录",
                f"“{template.label}”已有 {referenced} 条记录。"
                "请先删除这些记录，或将记录改为其他同类标签。",
            )
            return
        answer = QtWidgets.QMessageBox.question(
            self,
            "删除标签",
            f"确定删除“{template.label}”吗？\n该操作可以通过 Ctrl+Z 撤销。",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if answer != QtWidgets.QMessageBox.Yes:
            return
        try:
            self.store.delete_template(template_id)
        except (KeyError, ValueError) as error:
            self._warning("无法删除标签", str(error))
            return
        if self.active_template_id == template_id:
            self.active_template_id = None
        self._after_project_change(f"已删除标签“{template.label}”")

    def load_rating_template(self) -> None:
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "导入评分/关键帧模板", str(ROOT_DIRECTORY / "samples"), "文本文件 (*.txt)"
        )
        if not filename:
            return
        try:
            additions = parse_rating_template(Path(filename))
        except (OSError, UnicodeError) as error:
            self._error("无法读取模板", str(error))
            return
        if self._append_templates(additions):
            self._info(f"已添加 {len(additions)} 个评分或关键帧标签。")

    def restore_default_templates(self) -> None:
        additions = default_templates(ROOT_DIRECTORY)
        if self.store and self.store.annotations:
            self._warning("不能覆盖当前模板", "当前项目已有标注。请使用“导入模板”追加，以避免历史标签失效。")
            return
        if self.store:
            try:
                self.store.replace_templates(additions)
            except ValueError as error:
                self._warning("无法恢复模板", str(error))
                return
            self.templates = self.store.templates
            self._schedule_autosave()
        else:
            self.templates = additions
        self._refresh_template_pages()
        self._info("已恢复内置模板。")

    def _append_templates(self, additions: List[TemplateItem]) -> bool:
        if not additions:
            return False
        if self.store:
            try:
                self.store.append_templates(additions)
            except ValueError as error:
                self._warning("无法导入模板", str(error))
                return False
            self.templates = self.store.templates
            self._schedule_autosave()
        else:
            existing = {item.id for item in self.templates}
            identifiers = [item.id for item in additions]
            if len(set(identifiers)) != len(identifiers) or any(
                identifier in existing for identifier in identifiers
            ):
                self._warning("无法导入模板", "模板 ID 重复。")
                return False
            self.templates.extend(additions)
        self._refresh_template_pages()
        return True

    def select_template(self, template_id: str) -> None:
        template = self._template(template_id)
        if not template:
            return
        self.active_template_id = template_id
        self.active_label.setText(template.label)
        hints = []
        if template.kind == "interval":
            if template.start_hint:
                hints.append(f"开始：{template.start_hint}")
            if template.end_hint:
                hints.append(f"结束：{template.end_hint}")
            self.template_tabs.setCurrentWidget(
                self.phase_page if template.category.lower() == "phase" else self.task_page
            )
        elif template.kind == "rating":
            self.template_tabs.setCurrentWidget(self.rating_page)
            hints.append("点击评分会立即自动保存。")
        else:
            self.template_tabs.setCurrentWidget(self.point_page)
            hints.append("可记录当前时间，或同时保存当前画面。")
        self.pending_label.setText(" · ".join(hints) or "已选择标签。")
        self._refresh_annotation_controls()

    def mark_start(self) -> None:
        if not self._require_project():
            return
        template = self._active_template()
        if not template or template.kind != "interval":
            self._warning("请选择区间标签", "请先在“阶段”或“动作”页选择一个标签。")
            return
        if self.pending_interval:
            pending_template = self._template(self.pending_interval[0])
            replace = QtWidgets.QMessageBox.question(
                self,
                "替换未完成标注",
                f"“{pending_template.label if pending_template else '当前标签'}”尚未记录结束时间。\n"
                "要放弃它并从当前位置重新开始吗？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if replace != QtWidgets.QMessageBox.Yes:
                return
        self.pending_interval = (template.id, self._last_position)
        self._refresh_annotation_controls()
        self._info(f"已记录“{template.label}”开始：{format_timecode(self._last_position)}")

    def mark_end(self) -> None:
        if not self._require_project():
            return
        if not self.pending_interval:
            self._warning("没有进行中的标注", "请先按 I 或点击“记录开始”。")
            return
        template = self._template(self.pending_interval[0])
        if not template:
            self.cancel_pending_interval()
            return
        start = self.pending_interval[1]
        end = self._last_position
        if end < start:
            self._warning("时间顺序无效", "结束时间早于开始时间。请向后定位后再记录结束。")
            return
        try:
            self.store.add_annotation(template, start, end)
        except ValueError as error:
            self._warning("无法完成标注", str(error))
            return
        self.pending_interval = None
        self._after_project_change(f"已完成“{template.label}”")

    def cancel_pending_interval(self) -> None:
        if self.pending_interval:
            self.pending_interval = None
            self._refresh_annotation_controls()
            self._info("已取消未完成标注。")

    def record_point(self, template_id: str, capture: bool = False) -> None:
        if not self._require_project():
            return
        template = self._template(template_id)
        if not template or template.kind != "point":
            return
        asset_path = ""
        if capture:
            asset_path = self._capture_frame_file()
            if not asset_path:
                return
        frame = int(round((self._last_position / 1_000) * self.backend.fps))
        try:
            self.store.add_annotation(
                template, self._last_position, frame=frame, asset_path=asset_path
            )
        except ValueError as error:
            self._warning("无法记录关键帧", str(error))
            return
        self._after_project_change(f"已记录关键帧“{template.label}”")

    def set_rating(self, template_id: str, score: int) -> None:
        if not self._require_project():
            return
        template = self._template(template_id)
        if not template:
            return
        try:
            self.store.set_rating(template, score)
        except ValueError as error:
            self._warning("评分无效", str(error))
            return
        self._after_project_change(f"“{template.label}”评分已设为 {score}")

    def capture_current_frame(self) -> None:
        if not self._require_project():
            return
        template = self._active_template()
        if template and template.kind == "point":
            self.record_point(template.id, True)
            return
        saved = self._capture_frame_file()
        if saved:
            self._info(f"当前画面已保存：{saved}")

    def extract_annotation_frames(self) -> None:
        """Extract one representative image for every interval or point annotation."""
        if not self._require_project():
            return
        annotations = [
            annotation
            for annotation in self.store.annotations
            if annotation.kind in {"interval", "point"}
        ]
        if not annotations:
            self._warning("没有可提取的标注", "请先完成阶段、动作或关键帧标注。")
            return
        try:
            images = self.store.output_directory / "images"
            images.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._error("无法创建画面目录", str(error))
            return

        capture = cv2.VideoCapture(str(self.video_path))
        if not capture.isOpened():
            capture.release()
            self._warning("无法提取画面", "无法打开当前视频以读取标注画面。")
            return

        progress = QtWidgets.QProgressDialog(
            "正在按阶段、动作和预警标注提取代表帧…",
            "停止",
            0,
            len(annotations),
            self,
        )
        progress.setWindowTitle("批量提取关键帧")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setMinimumDuration(0)
        assets: Dict[str, str] = {}
        skipped = 0
        failed = 0
        cancelled = False
        try:
            for index, annotation in enumerate(annotations, start=1):
                progress.setValue(index - 1)
                progress.setLabelText(
                    f"正在提取 {index}/{len(annotations)}：{annotation.label}"
                )
                QtWidgets.QApplication.processEvents()
                if progress.wasCanceled():
                    cancelled = True
                    break
                if annotation.asset_path:
                    current = self.store.output_directory / annotation.asset_path
                    try:
                        current.resolve().relative_to(
                            self.store.output_directory.resolve()
                        )
                        is_safe = not Path(annotation.asset_path).is_absolute()
                    except (OSError, ValueError):
                        is_safe = False
                    if is_safe and current.is_file():
                        skipped += 1
                        continue
                timestamp = representative_frame_time(annotation)
                filename = (
                    f"auto_{annotation.kind}_{annotation.id}_{timestamp:012d}.png"
                )
                destination = images / filename
                try:
                    capture.set(cv2.CAP_PROP_POS_MSEC, timestamp)
                    ok, frame = capture.read()
                    if not ok or frame is None or not cv2.imwrite(str(destination), frame):
                        failed += 1
                        continue
                except (cv2.error, OSError):
                    failed += 1
                    continue
                assets[annotation.id] = str(
                    destination.relative_to(self.store.output_directory).as_posix()
                )
        finally:
            capture.release()
            progress.setValue(len(annotations))
            progress.close()

        if assets:
            try:
                self.store.set_annotation_assets(assets)
            except (KeyError, ValueError) as error:
                self._error("无法关联提取画面", str(error))
                return
            self._after_project_change(f"已提取并关联 {len(assets)} 张标注画面")
        result = (
            f"新增 {len(assets)} 张，已有画面 {skipped} 张"
            + (f"，失败 {failed} 张" if failed else "")
        )
        if cancelled:
            result += "；任务已停止，已完成部分仍然保留"
        QtWidgets.QMessageBox.information(self, "关键帧提取完成", result)

    def _capture_frame_file(self) -> str:
        if not self.video_path or not self.store:
            return ""
        images = self.store.output_directory / "images"
        try:
            images.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._error("无法保存画面", str(error))
            return ""
        timestamp = max(0, self._last_position)
        filename = f"frame_{timestamp:012d}_{datetime.now().strftime('%H%M%S%f')}.png"
        destination = images / filename
        capture = None
        try:
            capture = cv2.VideoCapture(str(self.video_path))
            if not capture.isOpened():
                self._warning("无法保存画面", "无法打开当前视频以读取画面。")
                return ""
            capture.set(cv2.CAP_PROP_POS_MSEC, timestamp)
            ok, frame = capture.read()
            if not ok or frame is None:
                self._warning("无法保存画面", "当前视频位置无法读取画面，请稍后重试。")
                return ""
            if not cv2.imwrite(str(destination), frame):
                self._warning("无法保存画面", "图像文件写入失败。")
                return ""
        except (cv2.error, OSError) as error:
            self._error("无法保存画面", str(error))
            return ""
        finally:
            if capture is not None:
                capture.release()
        return str(destination.relative_to(self.store.output_directory).as_posix())

    def _refresh_template_pages(self) -> None:
        interval_templates = [item for item in self.templates if item.kind == "interval"]
        phase = [item for item in interval_templates if item.category.lower() == "phase"]
        tasks = [item for item in interval_templates if item.category.lower() != "phase"]
        ratings = [item for item in self.templates if item.kind == "rating"]
        points = [item for item in self.templates if item.kind == "point"]
        self.phase_page.set_templates(phase)
        self.task_page.set_templates(tasks)
        rating_values = {
            item.id: self.store.rating_for(item.id) if self.store else None for item in ratings
        }
        self.rating_page.set_templates(ratings, rating_values)
        self.point_page.set_templates(points)

        all_ids = {item.id for item in self.templates}
        if self.active_template_id not in all_ids:
            preferred = phase or tasks or ratings or points
            self.active_template_id = preferred[0].id if preferred else None
        self.phase_page.select_template(self.active_template_id)
        self.task_page.select_template(self.active_template_id)
        self._refresh_annotation_controls()

    def _refresh_project_views(self) -> None:
        annotations = self.store.annotations if self.store else []
        self.timeline.set_annotations(annotations)
        self._refresh_annotation_table()
        self._refresh_annotation_controls()
        self._refresh_progress()
        self._update_action_state()

    def _refresh_annotation_table(self) -> None:
        if not hasattr(self, "annotation_table"):
            return
        selected_id = self._selected_annotation_id()
        annotations = self.store.annotations if self.store else []
        total_count = len(annotations)
        term = self.record_filter.text().strip().lower() if hasattr(self, "record_filter") else ""
        if term:
            annotations = [
                item
                for item in annotations
                if term in item.label.lower()
                or term in item.category.lower()
                or term in item.note.lower()
                or term in human_kind(item.kind).lower()
            ]
        annotations.sort(key=lambda item: (item.start_ms, item.created_at))
        self.annotation_table.setSortingEnabled(False)
        self.annotation_table.setRowCount(0)
        for annotation in annotations:
            row = self.annotation_table.rowCount()
            self.annotation_table.insertRow(row)
            values = [
                human_kind(annotation.kind),
                annotation.label,
                format_timecode(annotation.start_ms),
                str(annotation.score)
                if annotation.kind == "rating"
                else format_timecode(annotation.end_ms),
                (
                    f"{human_status(annotation.status)} · 图"
                    if annotation.asset_path
                    else human_status(annotation.status)
                ),
            ]
            for column, value in enumerate(values):
                cell = QtWidgets.QTableWidgetItem(value)
                cell.setData(QtCore.Qt.UserRole, annotation.id)
                if column == 0:
                    colour = annotation_colour(annotation.kind, annotation.category)
                    cell.setForeground(QtGui.QBrush(QtGui.QColor(colour)))
                if column == 1 and annotation.note:
                    cell.setToolTip(annotation.note)
                if column == 4 and annotation.asset_path:
                    cell.setToolTip(f"已关联画面：{annotation.asset_path}")
                self.annotation_table.setItem(row, column, cell)
                if annotation.id == selected_id:
                    self.annotation_table.selectRow(row)
        self.record_count.setText(f"{len(annotations)} 条")
        if hasattr(self, "workspace_tabs"):
            self.workspace_tabs.setTabText(1, f"标注记录  {total_count}")
        self.annotation_table.setSortingEnabled(True)
        self._update_selection_state()

    def _refresh_annotation_controls(self) -> None:
        template = self._active_template()
        has_video = bool(self.store and self.video_path)
        is_interval = bool(template and template.kind == "interval")
        is_pending = bool(self.pending_interval)
        self.start_button.setEnabled(has_video and is_interval)
        self.end_button.setEnabled(has_video and is_pending)
        self.cancel_draft_button.setEnabled(is_pending)
        self.start_button.setText("记录开始  I" if not is_pending else "重新开始  I")
        self.end_button.setText("记录结束  O" if not is_pending else "完成区间  O")
        self.start_button.setProperty("accent", not is_pending)
        self.end_button.setProperty("success", is_pending)
        for button in (self.start_button, self.end_button):
            button.style().unpolish(button)
            button.style().polish(button)
        if not template:
            self.active_label.setText("从“阶段”或“动作”中选择一个标签")
            self.pending_label.setText("选择标签后按 I 记录开始，按 O 记录结束。")
        elif self.pending_interval:
            pending = self._template(self.pending_interval[0])
            self.active_label.setText(pending.label if pending else template.label)
            self.pending_label.setText(
                f"进行中：开始于 {format_timecode(self.pending_interval[1])}。"
                "定位到结束位置后按 O。"
            )
        else:
            self.active_label.setText(template.label)

    def _refresh_progress(self) -> None:
        if not self.store:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.progress.setFormat("未打开病例")
            self.progress.setToolTip("打开视频后显示阶段覆盖率和审核状态。")
            return
        annotations = self.store.annotations
        coverage = round(self.store.phase_coverage_ratio() * 100)
        reviewed = sum(item.status == "reviewed" for item in annotations)
        ready = sum(item.status == "ready" for item in annotations)
        draft = sum(item.status == "draft" for item in annotations)
        issues = self.store.validate()
        errors = sum(item.severity == "error" for item in issues)
        warnings = sum(item.severity == "warning" for item in issues)
        self.progress.setRange(0, 100)
        self.progress.setValue(coverage)
        self.progress.setFormat(f"覆盖 {coverage}% · 审 {reviewed}/{len(annotations)}")
        self.progress.setToolTip(
            f"阶段覆盖率：{coverage}%\n"
            f"草稿：{draft} · 待审核：{ready} · 已审核：{reviewed}\n"
            f"数据错误：{errors} · 提示：{warnings}"
        )

    def _on_player_position(self, milliseconds: int) -> None:
        self._last_position = max(0, milliseconds)
        self.position_label.setText(format_timecode(self._last_position))
        self.timeline.set_playhead(self._last_position)

    def _on_player_duration(self, milliseconds: int) -> None:
        self.duration_label.setText(format_timecode(milliseconds))
        self.timeline.set_duration(milliseconds)
        if self.store:
            before = (
                self.store.media.get("duration_ms"),
                self.store.media.get("fps"),
            )
            self.store.update_media_info(duration_ms=milliseconds, fps=self.backend.fps)
            after = (
                self.store.media.get("duration_ms"),
                self.store.media.get("fps"),
            )
            if after != before:
                self._schedule_autosave()

    def _on_playback_changed(self, playing: bool) -> None:
        icon = self._themed_standard_icon(
            QtWidgets.QStyle.SP_MediaPause if playing else QtWidgets.QStyle.SP_MediaPlay,
            "on_primary",
        )
        self.play_button.setIcon(icon)
        self.play_button.setText("" if playing else "")
        self.play_button.setToolTip("暂停 (Space)" if playing else "播放 (Space)")

    def _show_player_error(self, message: str) -> None:
        self._warning("播放器提示", message)
        self._info(message)

    def toggle_playback(self) -> None:
        if not self.video_path:
            self.open_video()
            return
        self.backend.toggle()

    def undo(self) -> None:
        if self.store and self.store.undo():
            self.templates = self.store.templates
            self._after_project_change("已撤销上一步")

    def redo(self) -> None:
        if self.store and self.store.redo():
            self.templates = self.store.templates
            self._after_project_change("已重做上一步")

    def _after_project_change(self, message: str) -> None:
        if self.store:
            self.templates = self.store.templates
        self._refresh_project_views()
        self._refresh_template_pages()
        self._schedule_autosave()
        self._info(message)

    def _schedule_autosave(self) -> None:
        if self.store and self.store.is_dirty:
            self.save_state.setText("等待自动保存")
            self._save_timer.start()

    def _save_project(self) -> bool:
        self._save_timer.stop()
        if not self.store:
            return False
        try:
            self.store.save()
        except OSError as error:
            self.save_state.setText("保存失败")
            self._error("项目保存失败", str(error))
            return False
        try:
            self.store.sync_default_exports()
        except OSError as error:
            self.save_state.setText("项目已保存 · 导出同步失败")
            self._info(f"项目 JSON 已保存，但 CSV/TXT 同步失败：{error}")
            self._update_action_state()
            return True
        self.save_state.setText(f"已保存并同步 {datetime.now().strftime('%H:%M:%S')}")
        self._update_action_state()
        return True

    def export_project(self) -> None:
        if not self._require_project():
            return
        default_directory = self.store.output_directory / "exports"
        try:
            default_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self._error("无法创建默认导出文件夹", str(error))
            return
        issues = self.store.validate()
        errors = [item for item in issues if item.severity == "error"]
        if errors:
            ValidationReportDialog(issues, self).exec_()
            self._warning("请先修复数据错误", "修复后即可导出；提示项不阻止导出。")
            return
        destination = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择导出位置", str(default_directory)
        )
        if not destination:
            return
        destination_path = Path(destination)
        if not self._save_project():
            return
        try:
            csv_path = self.store.export_csv(destination_path / "annotations.csv")
            legacy_paths = self.store.export_legacy(destination_path)
        except OSError as error:
            self._error("导出失败", str(error))
            return
        if issues:
            ValidationReportDialog(issues, self).exec_()
        self._info(f"已导出 CSV 和 {len(legacy_paths)} 份兼容文本到 {destination_path}")
        QtWidgets.QMessageBox.information(
            self,
            "导出完成",
            f"已生成：\n{csv_path.name}\n"
            f"兼容文本 {len(legacy_paths)} 份\n\n无损项目文件仍保存在：\n{self.store.path}",
        )

    def show_validation(self) -> None:
        if not self._require_project():
            return
        ValidationReportDialog(self.store.validate(), self).exec_()

    def import_legacy(self) -> None:
        if not self._require_project():
            return
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择旧版 TXT 标注所在文件夹", str(self.store.output_directory)
        )
        if not directory:
            return
        try:
            reports = self.store.import_legacy_annotations(Path(directory))
        except (OSError, ValueError) as error:
            self._error("旧版标注导入失败", str(error))
            return
        self._after_project_change("旧版标注导入完成")
        if reports:
            ValidationReportDialog(reports, self).exec_()

    def _selected_annotation_id(self) -> Optional[str]:
        rows = self.annotation_table.selectionModel().selectedRows() if hasattr(self, "annotation_table") else []
        if not rows:
            return None
        item = self.annotation_table.item(rows[0].row(), 0)
        return str(item.data(QtCore.Qt.UserRole)) if item else None

    def _selected_annotation(self) -> Optional[Annotation]:
        annotation_id = self._selected_annotation_id()
        if not annotation_id or not self.store:
            return None
        for annotation in self.store.annotations:
            if annotation.id == annotation_id:
                return annotation
        return None

    def _update_selection_state(self) -> None:
        annotation = self._selected_annotation()
        selected = annotation is not None
        if hasattr(self, "timeline"):
            self.timeline.set_selected_annotation(
                annotation.id if annotation else None
            )
        for name in (
            "jump_annotation_button",
            "edit_annotation_button",
            "delete_annotation_button",
        ):
            if hasattr(self, name):
                getattr(self, name).setEnabled(selected)
        for name in ("edit_annotation_action", "delete_annotation_action"):
            if hasattr(self, name):
                getattr(self, name).setEnabled(selected)

    def _select_annotation_from_timeline(self, annotation_id: str) -> None:
        def matching_row() -> Optional[int]:
            for row in range(self.annotation_table.rowCount()):
                item = self.annotation_table.item(row, 0)
                if item and str(item.data(QtCore.Qt.UserRole)) == annotation_id:
                    return row
            return None

        row = matching_row()
        if row is None and self.record_filter.text():
            self.record_filter.clear()
            row = matching_row()
        if row is None:
            self.timeline.set_selected_annotation(None)
            return
        self.workspace_tabs.setCurrentIndex(1)
        self.annotation_table.selectRow(row)
        item = self.annotation_table.item(row, 0)
        if item:
            self.annotation_table.scrollToItem(
                item, QtWidgets.QAbstractItemView.PositionAtCenter
            )
        annotation = self._selected_annotation()
        if annotation:
            self._info(
                f"已选择“{annotation.label}” · {format_timecode(annotation.start_ms)}"
            )

    def _show_annotation_context_menu(self, position: QtCore.QPoint) -> None:
        index = self.annotation_table.indexAt(position)
        if not index.isValid():
            return
        self.annotation_table.selectRow(index.row())
        if not self._selected_annotation():
            return
        menu = QtWidgets.QMenu(self)
        jump = menu.addAction("跳转到标注")
        edit = menu.addAction("编辑标注…")
        menu.addSeparator()
        delete = menu.addAction("删除标注")
        chosen = menu.exec_(self.annotation_table.viewport().mapToGlobal(position))
        if chosen is jump:
            self.jump_to_selected_annotation()
        elif chosen is edit:
            self.edit_selected_annotation()
        elif chosen is delete:
            self.delete_selected_annotation()

    def jump_to_selected_annotation(self) -> None:
        annotation = self._selected_annotation()
        if not annotation:
            self._warning("请选择标注", "请先从记录列表选择一条标注。")
            return
        self.backend.seek(annotation.start_ms)

    def edit_selected_annotation(self) -> None:
        annotation = self._selected_annotation()
        if not annotation or not self.store:
            self._warning("请选择标注", "请先从记录列表选择一条标注。")
            return
        dialog = EditAnnotationDialog(
            annotation,
            self._template(annotation.template_id),
            self,
            duration_ms=self.backend.duration_ms,
            fps=self.backend.fps,
            templates=self.templates,
            current_position_ms=self._last_position,
        )
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        try:
            self.store.update_annotation(annotation.id, **dialog.values())
        except (KeyError, ValueError) as error:
            self._error("无法更新标注", str(error))
            return
        self._after_project_change("标注已更新")

    def delete_selected_annotation(self) -> None:
        annotation = self._selected_annotation()
        if not annotation or not self.store:
            self._warning("请选择标注", "请先从记录列表选择一条标注。")
            return
        if not self._confirm_annotation_delete(annotation):
            return
        try:
            self.store.delete_annotation(annotation.id)
        except KeyError as error:
            self._error("无法删除标注", str(error))
            return
        self._after_project_change("标注已删除")

    def _confirm_annotation_delete(self, annotation: Annotation) -> bool:
        """Use an explicit destructive role instead of a non-existent Qt enum."""
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Warning)
        dialog.setWindowTitle("删除标注")
        dialog.setText(f"确定删除“{annotation.label}”吗？")
        dialog.setInformativeText("删除后仍可使用 Ctrl+Z 撤销。")
        delete_button = dialog.addButton("删除", QtWidgets.QMessageBox.DestructiveRole)
        cancel_button = dialog.addButton("取消", QtWidgets.QMessageBox.RejectRole)
        delete_button.setProperty("danger", True)
        delete_button.style().unpolish(delete_button)
        delete_button.style().polish(delete_button)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec_()
        return dialog.clickedButton() is delete_button

    def _confirm_media_relink(self, path: Path) -> bool:
        """Require an explicit decision before binding annotations to changed media."""
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Warning)
        dialog.setWindowTitle("视频文件已变化")
        dialog.setText(f"“{path.name}”的内容与项目保存时不一致。")
        dialog.setInformativeText(
            "请确认它仍是同一病例版本；重新关联后，现有标注将使用这个视频。"
        )
        relink_button = dialog.addButton("重新关联当前视频", QtWidgets.QMessageBox.AcceptRole)
        cancel_button = dialog.addButton("取消打开", QtWidgets.QMessageBox.RejectRole)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec_()
        return dialog.clickedButton() is relink_button

    def _confirm_discard_pending_interval(self, action_label: str) -> bool:
        """Keep an in-progress interval from being silently lost."""
        if not self.pending_interval:
            return True
        dialog = QtWidgets.QMessageBox(self)
        dialog.setIcon(QtWidgets.QMessageBox.Warning)
        dialog.setWindowTitle("未完成的区间标注")
        dialog.setText("当前有未完成的区间标注。")
        dialog.setInformativeText(f"“{action_label}”会放弃这个未保存区间。")
        discard_button = dialog.addButton(action_label, QtWidgets.QMessageBox.DestructiveRole)
        cancel_button = dialog.addButton("继续标注", QtWidgets.QMessageBox.RejectRole)
        discard_button.setProperty("danger", True)
        discard_button.style().unpolish(discard_button)
        discard_button.style().polish(discard_button)
        dialog.setDefaultButton(cancel_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec_()
        return dialog.clickedButton() is discard_button

    def open_selected_in_labelme(self) -> None:
        annotation = self._selected_annotation()
        if not annotation:
            self._warning("请选择标注", "请先在记录列表选择带画面的标注。")
            return
        if not annotation.asset_path or not self.store:
            self._warning("没有关联画面", "该记录没有保存画面。请使用“记录并保存当前画面”。")
            return
        image = self.store.output_directory / annotation.asset_path
        if not image.exists():
            self._warning("找不到画面文件", str(image))
            return
        executable = shutil.which("labelme")
        if not executable:
            self._warning(
                "未找到 LabelMe",
                "请先安装 labelme，并确保其命令位于系统 PATH 中。",
            )
            return
        try:
            subprocess.Popen([executable, str(image)], cwd=str(image.parent))
        except OSError as error:
            self._error("无法启动 LabelMe", str(error))

    def show_shortcuts(self) -> None:
        QtWidgets.QMessageBox.information(
            self,
            "快捷键",
            "Space  播放/暂停\n"
            "← / →  前一帧 / 后一帧\n"
            "Shift + ← / →  后退 / 前进 1 秒\n"
            "Ctrl + ← / →  后退 / 前进 5 秒\n"
            "I / O  记录当前标签的开始 / 结束\n"
            "F  保存当前画面\n"
            "Ctrl + S  立即保存\n"
            "Ctrl + Z / Ctrl + Shift + Z  撤销 / 重做\n"
            "Ctrl + E  导出\n"
            "Enter / Delete  编辑 / 删除选中记录\n"
            "时间轴：Ctrl + 滚轮缩放，Shift + 滚轮平移",
        )

    def show_about(self) -> None:
        QtWidgets.QMessageBox.about(
            self,
            f"关于 {APP_NAME}",
            f"{APP_NAME} 是一个本地优先的手术视频标注工作台。\n\n"
            "项目采用版本化 JSON 自动保存；CSV 和旧版 TXT 仅作为导出格式。\n"
            f"当前播放器后端：{self.backend.backend_name}",
        )

    def _template(self, template_id: Optional[str]) -> Optional[TemplateItem]:
        if not template_id:
            return None
        return next((item for item in self.templates if item.id == template_id), None)

    def _active_template(self) -> Optional[TemplateItem]:
        return self._template(self.active_template_id)

    def _require_project(self) -> bool:
        if self.store and self.video_path:
            return True
        self._warning("请先打开视频", "打开视频后会自动创建或恢复一个本地项目。")
        return False

    def _update_action_state(self) -> None:
        has_project = bool(self.store)
        self.save_action.setEnabled(has_project)
        self.export_action.setEnabled(has_project)
        self.validate_action.setEnabled(has_project)
        self.capture_action.setEnabled(has_project)
        self.extract_frames_action.setEnabled(has_project)
        self.undo_action.setEnabled(bool(self.store and self.store.can_undo))
        self.redo_action.setEnabled(bool(self.store and self.store.can_redo))
        if hasattr(self, "annotation_table"):
            self._update_selection_state()

    def _info(self, message: str) -> None:
        self.status_message.setText(message)

    def _warning(self, title: str, message: str) -> None:
        QtWidgets.QMessageBox.warning(self, title, message)

    def _error(self, title: str, message: str) -> None:
        QtWidgets.QMessageBox.critical(self, title, message)

    def _global_video_shortcuts_allowed(self, key: Optional[int] = None) -> bool:
        """Keep native navigation while retaining I/O/F after choosing a label."""
        app = QtWidgets.QApplication.instance()
        if app and app.activeModalWidget() not in (None, self):
            return False
        focus = QtWidgets.QApplication.focusWidget()
        if not focus:
            return True
        if isinstance(
            focus,
            (
                QtWidgets.QAbstractItemView,
                QtWidgets.QAbstractButton,
                QtWidgets.QAbstractSlider,
                QtWidgets.QLineEdit,
                QtWidgets.QTextEdit,
                QtWidgets.QPlainTextEdit,
                QtWidgets.QComboBox,
                QtWidgets.QSpinBox,
                QtWidgets.QMenu,
            ),
        ):
            if isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit,
                                  QtWidgets.QComboBox, QtWidgets.QSpinBox, QtWidgets.QMenu)):
                return False
            return key in (QtCore.Qt.Key_I, QtCore.Qt.Key_O, QtCore.Qt.Key_F)
        window = focus.window()
        return not isinstance(window, QtWidgets.QDialog)

    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if watched is self.video_widget and event.type() == QtCore.QEvent.MouseButtonRelease:
            mouse_event = event
            if mouse_event.button() == QtCore.Qt.LeftButton:
                self.toggle_playback()
                return True
        if event.type() in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            key_event = event
            if key_event.key() == QtCore.Qt.Key_Space:
                app = QtWidgets.QApplication.instance()
                modal = app.activeModalWidget() if app else None
                if self.isActiveWindow() and modal is None:
                    if event.type() == QtCore.QEvent.KeyPress and not key_event.isAutoRepeat():
                        self.toggle_playback()
                    # Swallow both press and release so focused buttons, trees,
                    # tables and sliders never interpret Space themselves.
                    return True
        if event.type() == QtCore.QEvent.KeyPress:
            key_event = event
            key = key_event.key()
            modifiers = key_event.modifiers()
            focus = QtWidgets.QApplication.focusWidget()
            if (
                hasattr(self, "annotation_table")
                and key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter)
                and modifiers in (QtCore.Qt.NoModifier, QtCore.Qt.KeypadModifier)
                and focus is not None
                and (
                    focus is self.annotation_table
                    or focus is self.annotation_table.viewport()
                    or self.annotation_table.isAncestorOf(focus)
                )
            ):
                self.edit_annotation_action.trigger()
                return True
            if not self._global_video_shortcuts_allowed(key):
                return super().eventFilter(watched, event)
            if key == QtCore.Qt.Key_I and modifiers == QtCore.Qt.NoModifier:
                self.mark_start()
                return True
            if key == QtCore.Qt.Key_O and modifiers == QtCore.Qt.NoModifier:
                self.mark_end()
                return True
            if key == QtCore.Qt.Key_F and modifiers == QtCore.Qt.NoModifier:
                self.capture_current_frame()
                return True
            if key in (QtCore.Qt.Key_Left, QtCore.Qt.Key_Right):
                direction = -1 if key == QtCore.Qt.Key_Left else 1
                if modifiers & QtCore.Qt.ControlModifier:
                    self.backend.step_seconds(direction * 5)
                elif modifiers & QtCore.Qt.ShiftModifier:
                    self.backend.step_seconds(direction)
                else:
                    self.backend.step_frames(direction)
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        if self._closing:
            event.accept()
            return
        if self.pending_interval and not self._confirm_discard_pending_interval("放弃并退出"):
            event.ignore()
            return
        if self.store and self.store.is_dirty and not self._save_project():
            event.ignore()
            return
        self._closing = True
        self._save_timer.stop()
        self.settings.setValue("layout/main_splitter_v2", self.main_splitter.saveState())
        app = QtWidgets.QApplication.instance()
        if app:
            app.removeEventFilter(self)
        self.backend.shutdown_for_exit()
        event.accept()


# Compatibility aliases for existing launch scripts and packaged builds.
Window = AnnotationWindow
Slider = AnnotationTimeline


def main() -> int:
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = AnnotationWindow()
    window.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
