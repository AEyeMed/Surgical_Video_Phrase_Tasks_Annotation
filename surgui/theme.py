"""Theme runtime generated from the project's DESIGN.md token documents.

Qt stylesheets do not support CSS variables, so the application resolves the
active DESIGN document into a complete QSS string. The documents remain the
source of truth; this module only maps their semantic tokens to Qt widgets.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Dict, Iterable, Mapping, Optional, Tuple


_PACKAGE_ROOT = Path(__file__).resolve().parent
_SOURCE_ROOT = _PACKAGE_ROOT.parent


def resource_root() -> Path:
    """Find bundled DESIGN documents in source, frozen and installed layouts."""
    frozen_root = getattr(sys, "_MEIPASS", "")
    candidates = (
        _SOURCE_ROOT,
        Path(frozen_root) if frozen_root else None,
        Path(sys.prefix) / "surgui_assets",
    )
    for candidate in candidates:
        if candidate and (candidate / "DESIGN.md").is_file():
            return candidate
    return _SOURCE_ROOT


PROJECT_ROOT = resource_root()
DEFAULT_THEME = "clinical-light"
THEME_DOCUMENTS = {
    "clinical-light": ("临床浅色", PROJECT_ROOT / "DESIGN.md"),
    "clinical-dark": ("临床深色", PROJECT_ROOT / "DESIGN.clinical-dark.md"),
    "theatre-dim": ("手术室低照度", PROJECT_ROOT / "DESIGN.theatre-dim.md"),
}
THEME_LABELS = {theme_id: item[0] for theme_id, item in THEME_DOCUMENTS.items()}

REQUIRED_COLOURS = (
    "canvas",
    "surface",
    "surface_alt",
    "surface_hover",
    "surface_pressed",
    "surface_input",
    "video",
    "border",
    "text",
    "muted",
    "disabled",
    "focus",
    "primary",
    "on_primary",
    "primary_hover",
    "primary_container",
    "on_primary_container",
    "success",
    "on_success",
    "success_container",
    "on_success_container",
    "success_text",
    "warning",
    "on_warning",
    "warning_container",
    "on_warning_container",
    "warning_text",
    "danger",
    "on_danger",
    "danger_container",
    "on_danger_container",
    "danger_text",
    "violet",
    "on_violet",
    "violet_container",
    "on_violet_container",
    "annotation_phase",
    "on_annotation_phase",
    "annotation_task",
    "on_annotation_task",
    "annotation_keyframe",
    "on_annotation_keyframe",
    "annotation_rating",
    "on_annotation_rating",
    "selection",
    "on_selection",
    "scrollbar",
)
REQUIRED_TYPOGRAPHY = ("brand", "title-md", "body-md", "body-sm", "label-sm", "timecode")
REQUIRED_SPACING = ("xxs", "xs", "sm", "md", "lg", "xl", "xxl")
REQUIRED_ROUNDED = ("sm", "md", "lg", "full")


class DesignTokenError(ValueError):
    """Raised when an active theme document is not a usable DESIGN.md."""


@dataclass(frozen=True)
class ThemeTokens:
    identifier: str
    label: str
    document: Path
    colours: Mapping[str, str]
    typography: Mapping[str, Mapping[str, str]]
    spacing: Mapping[str, str]
    rounded: Mapping[str, str]


def _scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    return value


def _frontmatter(path: Path) -> Dict[str, object]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise DesignTokenError(f"无法读取主题规范：{path.name} ({error})") from error
    if not lines or lines[0].strip() != "---":
        raise DesignTokenError(f"{path.name} 缺少 DESIGN.md YAML front matter")
    try:
        end = next(index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration as error:
        raise DesignTokenError(f"{path.name} 的 YAML front matter 未闭合") from error

    result: Dict[str, object] = {}
    section: Optional[str] = None
    typography_name: Optional[str] = None
    for raw in lines[1:end]:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if indent == 0:
            typography_name = None
            if value:
                result[key] = _scalar(value)
                section = None
            else:
                section = key
                result.setdefault(section, {})
            continue
        if section in {"colors", "spacing", "rounded"} and indent == 2:
            target = result.setdefault(section, {})
            assert isinstance(target, dict)
            target[key] = _scalar(value)
            continue
        if section == "typography" and indent == 2:
            typography_name = key
            target = result.setdefault("typography", {})
            assert isinstance(target, dict)
            target.setdefault(typography_name, {})
            continue
        if section == "typography" and indent >= 4 and typography_name:
            target = result["typography"]
            assert isinstance(target, dict)
            definition = target[typography_name]
            assert isinstance(definition, dict)
            definition[key] = _scalar(value)
    return result


def _missing(values: Mapping[str, object], required: Iterable[str]) -> Tuple[str, ...]:
    return tuple(key for key in required if key not in values)


def load_theme(theme_id: str) -> ThemeTokens:
    """Load one approved theme directly from its DESIGN.md token document."""
    if theme_id not in THEME_DOCUMENTS:
        theme_id = DEFAULT_THEME
    label, document = THEME_DOCUMENTS[theme_id]
    data = _frontmatter(document)
    raw_colours = data.get("colors")
    raw_typography = data.get("typography")
    raw_spacing = data.get("spacing")
    raw_rounded = data.get("rounded")
    if not all(isinstance(value, dict) for value in (raw_colours, raw_typography, raw_spacing, raw_rounded)):
        raise DesignTokenError(f"{document.name} 缺少 colors、typography、spacing 或 rounded tokens")

    colours = {
        str(key).replace("-", "_"): str(value)
        for key, value in raw_colours.items()
    }
    typography = {
        str(key): {str(prop): str(value) for prop, value in definition.items()}
        for key, definition in raw_typography.items()
        if isinstance(definition, dict)
    }
    spacing = {str(key): str(value) for key, value in raw_spacing.items()}
    rounded = {str(key): str(value) for key, value in raw_rounded.items()}
    missing = (
        _missing(colours, REQUIRED_COLOURS)
        + _missing(typography, REQUIRED_TYPOGRAPHY)
        + _missing(spacing, REQUIRED_SPACING)
        + _missing(rounded, REQUIRED_ROUNDED)
    )
    if missing:
        raise DesignTokenError(f"{document.name} 缺少 token：{', '.join(missing)}")
    return ThemeTokens(theme_id, label, document, colours, typography, spacing, rounded)


CURRENT_THEME = DEFAULT_THEME
COLOURS: Dict[str, str] = {}
_CURRENT_TOKENS: Optional[ThemeTokens] = None


def activate_theme(theme_id: str) -> ThemeTokens:
    """Switch active token values in place so existing imports stay current."""
    global CURRENT_THEME, _CURRENT_TOKENS
    tokens = load_theme(theme_id)
    CURRENT_THEME = tokens.identifier
    _CURRENT_TOKENS = tokens
    COLOURS.clear()
    COLOURS.update(tokens.colours)
    return tokens


def active_tokens() -> ThemeTokens:
    global _CURRENT_TOKENS
    if _CURRENT_TOKENS is None:
        _CURRENT_TOKENS = activate_theme(DEFAULT_THEME)
    return _CURRENT_TOKENS


def theme_label(theme_id: str) -> str:
    return THEME_LABELS.get(theme_id, THEME_LABELS[DEFAULT_THEME])


def annotation_colour(kind: str, category: str = "") -> str:
    """Resolve annotation visuals by semantic role rather than saved hex values."""
    colours = active_tokens().colours
    if kind == "point":
        return colours["annotation_keyframe"]
    if kind == "rating":
        return colours["annotation_rating"]
    if category.lower() == "phase":
        return colours["annotation_phase"]
    return colours["annotation_task"]


def spacing_pixels(name: str) -> int:
    """Read a pixel layout value from the active DESIGN spacing scale."""
    value = active_tokens().spacing[name]
    if not value.endswith("px"):
        raise DesignTokenError(f"间距 token 必须使用 px：{name}={value}")
    try:
        return int(value[:-2])
    except ValueError as error:
        raise DesignTokenError(f"间距 token 无效：{name}={value}") from error


def _type(tokens: ThemeTokens, name: str, property_name: str, fallback: str = "") -> str:
    return tokens.typography[name].get(property_name, fallback)


def build_stylesheet(theme_id: Optional[str] = None) -> str:
    """Build one Qt-compatible style sheet entirely from DESIGN tokens."""
    tokens = load_theme(theme_id or CURRENT_THEME)
    c = tokens.colours
    s = tokens.spacing
    r = tokens.rounded
    body_family = _type(tokens, "body-md", "fontFamily")
    body_size = _type(tokens, "body-md", "fontSize")
    brand_size = _type(tokens, "brand", "fontSize")
    brand_weight = _type(tokens, "brand", "fontWeight", "700")
    title_size = _type(tokens, "title-md", "fontSize")
    title_weight = _type(tokens, "title-md", "fontWeight", "700")
    label_size = _type(tokens, "label-sm", "fontSize")
    label_weight = _type(tokens, "label-sm", "fontWeight", "700")
    timecode_family = _type(tokens, "timecode", "fontFamily")
    timecode_size = _type(tokens, "timecode", "fontSize")
    timecode_weight = _type(tokens, "timecode", "fontWeight", "600")

    return f"""
* {{
    font-family: {body_family};
    font-size: {body_size};
}}
QMainWindow, QDialog {{
    background: {c["canvas"]};
    color: {c["text"]};
}}
QWidget {{
    color: {c["text"]};
}}
QToolTip {{
    color: {c["text"]};
    background: {c["surface"]};
    border: 1px solid {c["focus"]};
    border-radius: {r["sm"]};
    padding: {s["xs"]};
}}
QMenuBar, QToolBar, QStatusBar {{
    background: {c["surface"]};
    border: 0;
    border-bottom: 1px solid {c["border"]};
    spacing: {s["sm"]};
    padding: {s["xs"]} {s["sm"]};
}}
QToolBar::separator {{
    background: {c["border"]};
    width: 1px;
    margin: {s["xs"]} {s["sm"]};
}}
QMenuBar::item, QMenu::item {{
    padding: {s["sm"]} {s["md"]};
    background: transparent;
}}
QMenuBar::item:selected, QMenu::item:selected {{
    background: {c["surface_hover"]};
    border-radius: {r["sm"]};
}}
QMenu {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: {r["md"]};
    padding: {s["xs"]};
}}
QMenu::separator {{
    height: 1px;
    background: {c["border"]};
    margin: {s["xs"]} {s["sm"]};
}}
QLabel#Brand {{
    color: {c["text"]};
    font-size: {brand_size};
    font-weight: {brand_weight};
    padding-right: {s["sm"]};
}}
QLabel#CaseTitle {{
    color: {c["muted"]};
    font-size: {body_size};
    padding: 0 {s["md"]};
}}
QLabel#StatusPill {{
    color: {c["on_primary_container"]};
    background: {c["primary_container"]};
    border: 1px solid {c["primary"]};
    border-radius: {r["full"]};
    padding: {s["xxs"]} {s["sm"]};
}}
QLabel#Muted {{
    color: {c["muted"]};
}}
QLabel#Timecode {{
    color: {c["text"]};
    font-family: {timecode_family};
    font-size: {timecode_size};
    font-weight: {timecode_weight};
}}
QLabel#TimecodeMuted {{
    color: {c["muted"]};
    font-family: {timecode_family};
    font-size: {timecode_size};
    font-weight: {timecode_weight};
}}
QLabel#SectionCaption {{
    color: {c["muted"]};
    font-size: {label_size};
    font-weight: {label_weight};
}}
QLabel#ActiveLabel {{
    color: {c["text"]};
    font-size: {title_size};
    font-weight: {title_weight};
}}
QLabel#ErrorText {{
    color: {c["danger_text"]};
}}
QLabel#ValidationSummary[severity="ok"] {{
    color: {c["success_text"]};
    font-weight: {label_weight};
}}
QLabel#ValidationSummary[severity="warning"] {{
    color: {c["warning_text"]};
    font-weight: {label_weight};
}}
QLabel#ValidationSummary[severity="error"] {{
    color: {c["danger_text"]};
    font-weight: {label_weight};
}}
QLabel#LegendPhase {{ color: {c["annotation_phase"]}; }}
QLabel#LegendTask {{ color: {c["annotation_task"]}; }}
QLabel#LegendKeyframe {{ color: {c["annotation_keyframe"]}; }}
QLabel#PointTemplateTitle {{ color: {c["annotation_keyframe"]}; }}
QFrame#VideoStage, QFrame#Panel, QFrame#AnnotationControls, QFrame#EmptyState {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: {r["md"]};
}}
QFrame#VideoStage, QVideoWidget#VideoSurface {{
    background: {c["video"]};
}}
QPushButton, QToolButton {{
    background: {c["surface_alt"]};
    border: 1px solid {c["border"]};
    border-radius: {r["sm"]};
    color: {c["text"]};
    min-height: {s["xxl"]};
    padding: {s["xs"]} {s["md"]};
}}
QPushButton:hover, QToolButton:hover {{
    background: {c["surface_hover"]};
    border-color: {c["focus"]};
}}
QPushButton:pressed, QToolButton:pressed {{
    background: {c["surface_pressed"]};
}}
QPushButton:disabled, QToolButton:disabled {{
    color: {c["disabled"]};
    background: {c["surface_alt"]};
    border-color: {c["border"]};
}}
QPushButton:focus, QToolButton:focus {{
    border: {s["xxs"]} solid {c["focus"]};
}}
QPushButton[accent="true"] {{
    color: {c["on_primary"]};
    background: {c["primary"]};
    border-color: {c["primary"]};
    font-weight: {label_weight};
}}
QPushButton[accent="true"]:hover {{
    color: {c["on_primary"]};
    background: {c["primary_hover"]};
    border-color: {c["primary_hover"]};
}}
QPushButton[success="true"] {{
    color: {c["on_success"]};
    background: {c["success"]};
    border-color: {c["success"]};
}}
QPushButton[danger="true"] {{
    color: {c["on_danger"]};
    background: {c["danger"]};
    border-color: {c["danger"]};
}}
QPushButton[score="true"] {{
    min-width: {s["xxl"]};
    padding: {s["xs"]} {s["sm"]};
}}
QPushButton[score="true"]:checked {{
    color: {c["on_violet"]};
    background: {c["violet"]};
    border-color: {c["violet"]};
    font-weight: {label_weight};
}}
QToolButton#PlayButton {{
    color: {c["on_primary"]};
    background: {c["primary"]};
    border: 1px solid {c["primary"]};
    border-radius: {r["md"]};
    min-width: {s["xxl"]};
    min-height: {s["xxl"]};
    padding: {s["sm"]};
}}
QToolButton#PlayButton:hover {{
    background: {c["primary_hover"]};
    border-color: {c["primary_hover"]};
}}
QToolButton#TransportButton,
QToolButton#TimelineToolButton {{
    min-width: {s["xxl"]};
    min-height: {s["xxl"]};
    padding: {s["xxs"]};
    border-radius: {r["md"]};
}}
QToolButton#TransportWideButton,
QToolButton#TimelineZoomButton {{
    min-height: {s["xxl"]};
    padding: {s["xxs"]} {s["sm"]};
    border-radius: {r["md"]};
}}
QPushButton#CaptureButton,
QPushButton#IntervalActionButton {{
    min-height: {s["xxl"]};
    padding: {s["xs"]} {s["md"]};
}}
QToolButton#CancelDraftButton {{
    min-height: {s["xxl"]};
    padding: {s["xs"]} {s["sm"]};
}}
QToolButton#PlayButton:focus,
QToolButton#TransportButton:focus,
QToolButton#TransportWideButton:focus,
QToolButton#TimelineToolButton:focus,
QToolButton#TimelineZoomButton:focus {{
    border: {s["xxs"]} solid {c["focus"]};
}}
QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox {{
    background: {c["surface_input"]};
    border: 1px solid {c["border"]};
    border-radius: {r["sm"]};
    padding: {s["xs"]} {s["sm"]};
    color: {c["text"]};
    selection-background-color: {c["selection"]};
    selection-color: {c["on_selection"]};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: {s["xxs"]} solid {c["focus"]};
}}
QComboBox::drop-down {{
    border: 0;
    width: {s["xl"]};
}}
QComboBox QAbstractItemView {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    selection-background-color: {c["selection"]};
    selection-color: {c["on_selection"]};
}}
QTabWidget::pane {{
    border: 1px solid {c["border"]};
    background: {c["surface"]};
    border-radius: {r["md"]};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {c["muted"]};
    padding: {s["sm"]} {s["md"]};
    margin-right: {s["xxs"]};
}}
QTabBar::tab:selected {{
    color: {c["text"]};
    border-bottom: {s["xxs"]} solid {c["primary"]};
    font-weight: {label_weight};
}}
QTabWidget#WorkspaceTabs::pane {{
    border: 1px solid {c["border"]};
    background: {c["surface"]};
    border-radius: {r["md"]};
    top: -1px;
}}
QTabBar#WorkspaceTabBar::tab {{
    color: {c["muted"]};
    background: {c["surface_alt"]};
    border: 1px solid {c["border"]};
    border-radius: {r["md"]};
    padding: {s["sm"]} {s["xl"]};
    margin-right: {s["sm"]};
}}
QTabBar#WorkspaceTabBar::tab:selected {{
    color: {c["on_primary_container"]};
    background: {c["primary_container"]};
    border-color: {c["primary"]};
    font-weight: {label_weight};
}}
QTreeWidget, QTableWidget, QListWidget {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: {r["sm"]};
    alternate-background-color: {c["surface_alt"]};
    gridline-color: {c["border"]};
}}
QTreeWidget:focus, QTableWidget:focus, QListWidget:focus {{
    border: {s["xxs"]} solid {c["focus"]};
}}
QTreeWidget::item, QTableWidget::item, QListWidget::item {{
    padding: {s["xs"]};
}}
QTreeWidget::item:selected, QTableWidget::item:selected, QListWidget::item:selected {{
    background: {c["selection"]};
    color: {c["on_selection"]};
}}
QHeaderView::section {{
    background: {c["surface_alt"]};
    color: {c["muted"]};
    border: 0;
    border-bottom: 1px solid {c["border"]};
    padding: {s["sm"]};
    font-size: {label_size};
    font-weight: {label_weight};
}}
QScrollBar:vertical {{
    width: {s["md"]};
    background: transparent;
    margin: {s["xs"]};
}}
QScrollBar::handle:vertical {{
    min-height: {s["xl"]};
    background: {c["scrollbar"]};
    border-radius: {r["sm"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QSlider::groove:horizontal {{
    height: {s["sm"]};
    background: {c["border"]};
    border-radius: {r["sm"]};
}}
QSlider::sub-page:horizontal {{
    background: {c["primary"]};
    border-radius: {r["sm"]};
}}
QSlider::handle:horizontal {{
    width: {s["lg"]};
    height: {s["lg"]};
    margin: -{s["xs"]} 0;
    border-radius: {r["full"]};
    background: {c["surface"]};
    border: {s["xxs"]} solid {c["primary"]};
}}
QSlider::handle:horizontal:focus {{
    border: {s["xxs"]} solid {c["focus"]};
}}
QProgressBar {{
    background: {c["surface_alt"]};
    border: 1px solid {c["border"]};
    border-radius: {r["sm"]};
    text-align: center;
    color: {c["text"]};
}}
QProgressBar::chunk {{
    background: {c["primary"]};
    border-radius: {r["sm"]};
}}
QSplitter::handle {{
    background: {c["border"]};
}}
QSplitter::handle:hover {{
    background: {c["focus"]};
}}
"""


def build_palette(theme_id: Optional[str] = None):
    """Build the native Qt palette from the active DESIGN color roles."""
    from PyQt5 import QtGui

    tokens = load_theme(theme_id or CURRENT_THEME)
    c = tokens.colours
    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor(c["canvas"]))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor(c["text"]))
    palette.setColor(QtGui.QPalette.Base, QtGui.QColor(c["surface_input"]))
    palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor(c["surface_alt"]))
    palette.setColor(QtGui.QPalette.ToolTipBase, QtGui.QColor(c["surface"]))
    palette.setColor(QtGui.QPalette.ToolTipText, QtGui.QColor(c["text"]))
    palette.setColor(QtGui.QPalette.Text, QtGui.QColor(c["text"]))
    palette.setColor(QtGui.QPalette.Button, QtGui.QColor(c["surface_alt"]))
    palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(c["text"]))
    palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor(c["selection"]))
    palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor(c["on_selection"]))
    palette.setColor(
        QtGui.QPalette.Disabled, QtGui.QPalette.Text, QtGui.QColor(c["disabled"])
    )
    palette.setColor(
        QtGui.QPalette.Disabled, QtGui.QPalette.ButtonText, QtGui.QColor(c["disabled"])
    )
    return palette


def _hex_to_rgb(value: str) -> Tuple[float, float, float]:
    if not value.startswith("#") or len(value) != 7:
        raise ValueError(f"对比度检查只支持 #RRGGBB：{value}")
    return tuple(int(value[index:index + 2], 16) / 255 for index in (1, 3, 5))


def _linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def contrast_ratio(foreground: str, background: str) -> float:
    """Return WCAG contrast ratio for two DESIGN color tokens."""
    def luminance(value: str) -> float:
        red, green, blue = (_linear(component) for component in _hex_to_rgb(value))
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    first, second = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (first + 0.05) / (second + 0.05)


def accessibility_pairs(tokens: Optional[ThemeTokens] = None) -> Tuple[Tuple[str, str, str], ...]:
    """Pairs that are required to meet WCAG AA in every supported theme."""
    colours = (tokens or active_tokens()).colours
    return (
        ("正文", colours["text"], colours["canvas"]),
        ("次级文字", colours["muted"], colours["surface"]),
        ("主按钮", colours["on_primary"], colours["primary"]),
        ("完成按钮", colours["on_success"], colours["success"]),
        ("警告按钮", colours["on_warning"], colours["warning"]),
        ("危险按钮", colours["on_danger"], colours["danger"]),
        ("评分按钮", colours["on_violet"], colours["violet"]),
        ("成功提示文字（表面）", colours["success_text"], colours["surface"]),
        ("警告提示文字（表面）", colours["warning_text"], colours["surface"]),
        ("危险提示文字（表面）", colours["danger_text"], colours["surface"]),
        ("成功提示文字（画布）", colours["success_text"], colours["canvas"]),
        ("警告提示文字（画布）", colours["warning_text"], colours["canvas"]),
        ("危险提示文字（画布）", colours["danger_text"], colours["canvas"]),
        ("阶段标记", colours["annotation_phase"], colours["surface"]),
        ("动作标记", colours["annotation_task"], colours["surface"]),
        ("关键帧标记", colours["annotation_keyframe"], colours["surface"]),
        ("评分标记", colours["annotation_rating"], colours["surface"]),
    )


def non_text_accessibility_pairs(
    tokens: Optional[ThemeTokens] = None,
) -> Tuple[Tuple[str, str, str], ...]:
    """Critical non-text control boundaries that must meet 3:1 contrast."""
    colours = (tokens or active_tokens()).colours
    return (
        ("控件边框（输入框）", colours["border"], colours["surface_input"]),
        ("控件边框（普通表面）", colours["border"], colours["surface"]),
        ("控件边框（次级表面）", colours["border"], colours["surface_alt"]),
        ("禁用控件文字", colours["disabled"], colours["surface_alt"]),
    )


activate_theme(DEFAULT_THEME)
APP_STYLESHEET = build_stylesheet(DEFAULT_THEME)
