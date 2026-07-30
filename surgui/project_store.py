"""Versioned local project storage for SurgiAnnotate.

The Qt interface only talks to this repository. It never appends txt rows
directly, which keeps annotations recoverable, undoable and exportable.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


SCHEMA_VERSION = 1
APP_VERSION = "1.2.0"
VALID_KINDS = {"interval", "point", "rating"}
VALID_STATUSES = {"draft", "ready", "reviewed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_id(prefix: str = "") -> str:
    value = uuid.uuid4().hex
    return f"{prefix}_{value}" if prefix else value


def safe_filename(value: str, fallback: str = "untitled") -> str:
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(value)).strip(" ._")
    return result[:96] or fallback


def format_timecode(milliseconds: Optional[int], include_milliseconds: bool = True) -> str:
    if milliseconds is None:
        return "—"
    total = max(0, int(milliseconds))
    hours, remainder = divmod(total, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    if include_milliseconds:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def format_legacy_timecode(milliseconds: Optional[int]) -> str:
    if milliseconds is None:
        return "0"
    seconds_total = max(0, int(milliseconds)) // 1_000
    hours, remainder = divmod(seconds_total, 3_600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def parse_timecode(value: str) -> int:
    raw = str(value).strip()
    if not raw:
        raise ValueError("时间不能为空")
    if raw.replace(".", "", 1).isdigit():
        return int(round(float(raw) * 1_000))
    match = re.fullmatch(
        r"(?:(?P<h>\d+):)?(?P<m>\d{1,2}):(?P<s>\d{1,2})(?:[.,](?P<ms>\d{1,3}))?",
        raw,
    )
    if not match:
        raise ValueError(f"无法识别时间码：{value}")
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"时间码超出范围：{value}")
    fraction = (match.group("ms") or "").ljust(3, "0")
    millis = int(fraction) if fraction else 0
    return ((hours * 3_600 + minutes * 60 + seconds) * 1_000) + millis


def media_fingerprint(path: Path, block_size: int = 1_048_576) -> str:
    digest = hashlib.sha256()
    try:
        stat = path.stat()
        digest.update(str(stat.st_size).encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("utf-8"))
        with path.open("rb") as handle:
            digest.update(handle.read(block_size))
            if stat.st_size > block_size:
                handle.seek(max(0, stat.st_size - block_size))
                digest.update(handle.read(block_size))
    except OSError:
        digest.update(str(path).encode("utf-8", errors="replace"))
    return digest.hexdigest()


def case_directory(output_root: Path, media_path: Path) -> Path:
    return Path(output_root) / f"{safe_filename(media_path.stem)}_{media_fingerprint(media_path)[:10]}"


@dataclass
class TemplateItem:
    id: str
    label: str
    kind: str
    category: str
    group: str = "默认分组"
    colour: str = ""
    start_hint: str = ""
    end_hint: str = ""
    score_options: List[int] = field(default_factory=list)
    source: str = ""
    required: bool = False

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TemplateItem":
        data = dict(value)
        data.setdefault("group", "默认分组")
        data.setdefault("colour", "")
        data.setdefault("start_hint", "")
        data.setdefault("end_hint", "")
        data.setdefault("score_options", [])
        data.setdefault("source", "")
        data.setdefault("required", False)
        data["score_options"] = [int(item) for item in data["score_options"]]
        return cls(**data)


@dataclass
class Annotation:
    id: str
    kind: str
    template_id: str
    label: str
    category: str
    start_ms: int
    end_ms: Optional[int] = None
    score: Optional[int] = None
    note: str = ""
    status: str = "draft"
    frame: Optional[int] = None
    asset_path: str = ""
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Annotation":
        data = dict(value)
        data.setdefault("end_ms", None)
        data.setdefault("score", None)
        data.setdefault("note", "")
        data.setdefault("status", "draft")
        data.setdefault("frame", None)
        data.setdefault("asset_path", "")
        data.setdefault("created_at", utc_now())
        data.setdefault("updated_at", data["created_at"])
        return cls(**data)


@dataclass
class ValidationIssue:
    severity: str
    message: str
    annotation_id: str = ""


def representative_frame_time(annotation: Annotation) -> int:
    """Return the representative timestamp used for automatic frame extraction."""
    if annotation.kind == "interval" and annotation.end_ms is not None:
        return annotation.start_ms + max(0, annotation.end_ms - annotation.start_ms) // 2
    return annotation.start_ms


def interval_coverage_ms(
    annotations: Iterable[Annotation], duration_ms: int = 0
) -> int:
    """Measure the union of interval annotations, optionally clipped to a video."""
    limit = max(0, int(duration_ms))
    spans = []
    for annotation in annotations:
        if annotation.kind != "interval" or annotation.end_ms is None:
            continue
        start = max(0, int(annotation.start_ms))
        end = max(start, int(annotation.end_ms))
        if limit:
            start = min(start, limit)
            end = min(end, limit)
        spans.append((start, end))
    if not spans:
        return 0
    spans.sort()
    covered = 0
    current_start, current_end = spans[0]
    for start, end in spans[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        covered += current_end - current_start
        current_start, current_end = start, end
    return covered + current_end - current_start


def _template_id(category: str, index: int) -> str:
    return f"{safe_filename(category).lower()}_{index:03d}_{uuid.uuid4().hex[:8]}"


def parse_interval_template(path: Path, category: Optional[str] = None) -> List[TemplateItem]:
    path = Path(path)
    category = category or path.stem
    result: List[TemplateItem] = []
    group = "默认分组"
    group_number = 1
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text or text.startswith("//"):
                continue
            parts = [part.strip() for part in text.split("#")]
            label = parts[0]
            if label == "--":
                group_number += 1
                group = f"分组 {group_number}"
                continue
            if not label:
                continue
            result.append(
                TemplateItem(
                    id=_template_id(category, line_number),
                    label=label,
                    kind="interval",
                    category=category,
                    group=group,
                    start_hint=parts[1] if len(parts) > 1 else "",
                    end_hint=parts[2] if len(parts) > 2 else "",
                    source=str(path),
                )
            )
    return result


def parse_rating_template(path: Path, category: Optional[str] = None) -> List[TemplateItem]:
    path = Path(path)
    category = category or path.stem
    result: List[TemplateItem] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text or text.startswith("//"):
                continue
            parts = [part.strip() for part in text.split("#")]
            label = parts[0]
            if not label:
                continue
            try:
                score_count = int(parts[1]) if len(parts) > 1 else 2
            except ValueError:
                score_count = 2
            kind = "point" if score_count == 0 else "rating"
            result.append(
                TemplateItem(
                    id=_template_id(category, line_number),
                    label=label,
                    kind=kind,
                    category=category,
                    group="关键帧" if kind == "point" else "评分",
                    score_options=list(range(max(0, score_count))),
                    source=str(path),
                )
            )
    return result


def default_templates(base_directory: Path) -> List[TemplateItem]:
    samples = Path(base_directory) / "samples"
    templates: List[TemplateItem] = []
    for filename in ("phase.txt", "task.txt"):
        candidate = samples / filename
        if candidate.exists():
            templates.extend(parse_interval_template(candidate, candidate.stem))
    assessment = samples / "assessment.txt"
    if assessment.exists():
        templates.extend(parse_rating_template(assessment, assessment.stem))
    return templates


class ProjectStore:
    """Single source of truth for one local annotation project."""

    def __init__(self, project_path: Path, project: Dict[str, Any]) -> None:
        self.path = Path(project_path)
        self.project = project
        self._undo_stack: List[Dict[str, Any]] = []
        self._redo_stack: List[Dict[str, Any]] = []
        self.is_dirty = False
        self.recovered_from_backup = False
        self.recovery_source: Optional[Path] = None

    @classmethod
    def create(
        cls,
        project_path: Path,
        media_path: Path,
        templates: Sequence[TemplateItem],
        duration_ms: int = 0,
        fps: float = 0.0,
    ) -> "ProjectStore":
        now = utc_now()
        media = Path(media_path)
        project = {
            "schema_version": SCHEMA_VERSION,
            "app_version": APP_VERSION,
            "project_id": make_id("case"),
            "created_at": now,
            "updated_at": now,
            "media": {
                "path": str(media.resolve()),
                "file_name": media.name,
                "fingerprint": media_fingerprint(media),
                "duration_ms": max(0, int(duration_ms)),
                "fps": max(0.0, float(fps)),
            },
            "templates": [asdict(item) for item in templates],
            "annotations": [],
            "audit": [],
        }
        store = cls(project_path, project)
        store._append_audit("project_created", "创建项目")
        store.is_dirty = True
        return store

    @classmethod
    def load(cls, project_path: Path) -> "ProjectStore":
        path = Path(project_path)
        try:
            return cls._load_file(path)
        except ValueError as primary_error:
            backup = path.with_name(f"{path.stem}.previous{path.suffix}")
            if not backup.is_file():
                raise
            try:
                recovered = cls._load_file(backup)
            except (OSError, ValueError) as backup_error:
                raise ValueError(
                    f"项目文件无法读取，且备份也无效：主文件 {primary_error}；备份 {backup_error}"
                ) from primary_error
            recovered.path = path
            recovered.recovered_from_backup = True
            recovered.recovery_source = backup
            recovered._append_audit("project_recovered", f"从备份 {backup.name} 恢复项目")
            recovered.is_dirty = True
            return recovered

    @classmethod
    def _load_file(cls, path: Path) -> "ProjectStore":
        try:
            with path.open("r", encoding="utf-8") as handle:
                project = json.load(handle)
        except OSError:
            raise
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError(f"项目文件不是有效 JSON：{error}") from error
        if not isinstance(project, dict):
            raise ValueError("项目文件根节点必须是对象")
        try:
            version = int(project.get("schema_version", 0))
        except (TypeError, ValueError) as error:
            raise ValueError("项目 schema_version 无效") from error
        if version != SCHEMA_VERSION:
            raise ValueError("该项目文件版本不受当前程序支持")
        if not isinstance(project.get("project_id"), str) or not project["project_id"].strip():
            raise ValueError("项目文件缺少 project_id")
        media = project.get("media")
        if not isinstance(media, dict):
            raise ValueError("项目文件缺少 media 对象")
        if not isinstance(media.get("path"), str) or not isinstance(media.get("file_name"), str):
            raise ValueError("项目媒体信息不完整")
        if not isinstance(project.get("templates"), list) or not isinstance(project.get("annotations"), list):
            raise ValueError("项目模板或标注列表格式无效")
        if not isinstance(project.get("audit", []), list):
            raise ValueError("项目审计记录格式无效")
        project.setdefault("app_version", "unknown")
        project.setdefault("created_at", utc_now())
        project.setdefault("updated_at", project["created_at"])
        project.setdefault("audit", [])
        store = cls(path, project)
        try:
            store._normalise()
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"项目内容格式无效：{error}") from error
        return store

    def _normalise(self) -> None:
        template_ids = set()
        templates = []
        for raw in self.project["templates"]:
            if not isinstance(raw, dict):
                raise ValueError("模板项必须是对象")
            template = TemplateItem.from_dict(raw)
            if not isinstance(template.id, str) or not template.id.strip() or template.id in template_ids:
                raise ValueError(f"模板 ID 无效或重复：{template.id}")
            if not isinstance(template.label, str) or not template.label.strip():
                raise ValueError(f"模板标签无效：{template.id}")
            if template.kind not in VALID_KINDS:
                raise ValueError(f"模板类型无效：{template.kind}")
            if not isinstance(template.category, str) or not template.category.strip():
                raise ValueError(f"模板分类无效：{template.id}")
            template_ids.add(template.id)
            templates.append(asdict(template))
        self.project["templates"] = templates
        templates_by_id = {item["id"]: TemplateItem.from_dict(item) for item in templates}

        annotation_ids = set()
        annotations = []
        for raw in self.project["annotations"]:
            if not isinstance(raw, dict):
                raise ValueError("标注项必须是对象")
            annotation = Annotation.from_dict(raw)
            if not isinstance(annotation.id, str) or not annotation.id.strip() or annotation.id in annotation_ids:
                raise ValueError(f"标注 ID 无效或重复：{annotation.id}")
            if annotation.kind not in VALID_KINDS:
                raise ValueError(f"标注类型无效：{annotation.kind}")
            if annotation.status not in VALID_STATUSES:
                raise ValueError(f"标注状态无效：{annotation.status}")
            template = templates_by_id.get(annotation.template_id)
            if not template:
                raise ValueError(f"标注引用不存在的模板：{annotation.template_id}")
            annotation_ids.add(annotation.id)
            annotations.append(asdict(self._validate_annotation(annotation, template)))
        self.project["annotations"] = annotations

    @property
    def templates(self) -> List[TemplateItem]:
        return [TemplateItem.from_dict(item) for item in self.project["templates"]]

    @property
    def annotations(self) -> List[Annotation]:
        return [Annotation.from_dict(item) for item in self.project["annotations"]]

    @property
    def media(self) -> Dict[str, Any]:
        return self.project["media"]

    @property
    def output_directory(self) -> Path:
        return self.path.parent

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def set_path(self, project_path: Path) -> None:
        self.path = Path(project_path)
        self.is_dirty = True

    def _snapshot(self) -> Dict[str, Any]:
        return copy.deepcopy(self.project)

    def _begin_change(self) -> None:
        self._undo_stack.append(self._snapshot())
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def clear_history(self) -> None:
        """Treat project-open repairs as initialization, never as user undo steps."""
        self._undo_stack.clear()
        self._redo_stack.clear()

    def _append_audit(self, action: str, detail: str, annotation_id: str = "") -> None:
        audit = self.project.setdefault("audit", [])
        audit.append(
            {
                "id": make_id("audit"),
                "at": utc_now(),
                "action": action,
                "detail": detail,
                "annotation_id": annotation_id,
            }
        )
        if len(audit) > 500:
            del audit[:-500]

    def _changed(self, action: str, detail: str, annotation_id: str = "") -> None:
        self.project["updated_at"] = utc_now()
        self._append_audit(action, detail, annotation_id)
        self.is_dirty = True

    def _template_map(self) -> Dict[str, TemplateItem]:
        return {template.id: template for template in self.templates}

    def _annotation_index(self, annotation_id: str) -> int:
        for index, item in enumerate(self.project["annotations"]):
            if item.get("id") == annotation_id:
                return index
        raise KeyError(f"找不到标注 {annotation_id}")

    def _duration_limit(self) -> int:
        try:
            return max(0, int(self.media.get("duration_ms") or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _integer(value: Any, field_name: str, allow_none: bool = False) -> Optional[int]:
        if value is None and allow_none:
            return None
        if isinstance(value, bool):
            raise ValueError(f"{field_name} 必须是整数")
        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field_name} 必须是整数") from error

    def _validate_annotation(self, annotation: Annotation, template: TemplateItem) -> Annotation:
        if annotation.kind != template.kind or annotation.template_id != template.id:
            raise ValueError("标注与模板不一致")
        if annotation.status not in VALID_STATUSES:
            raise ValueError("标注状态无效")
        start = self._integer(annotation.start_ms, "开始时间")
        end = self._integer(annotation.end_ms, "结束时间", allow_none=True)
        frame = self._integer(annotation.frame, "帧号", allow_none=True)
        if start is None or start < 0:
            raise ValueError("开始时间不能为负数")
        if frame is not None and frame < 0:
            raise ValueError("帧号不能为负数")
        duration = self._duration_limit()
        score = annotation.score
        if template.kind == "interval":
            if end is None:
                raise ValueError("区间标注必须包含结束时间")
            if end < start:
                raise ValueError("结束时间不能早于开始时间")
            if duration and (start > duration or end > duration):
                raise ValueError("区间时间不能超过视频时长")
            score = None
        elif template.kind == "point":
            if duration and start > duration:
                raise ValueError("关键帧时间不能超过视频时长")
            end = None
            score = None
        elif template.kind == "rating":
            score = self._integer(score, "评分")
            if score not in template.score_options:
                raise ValueError(f"评分 {score} 不在允许范围内")
            start, end, frame = 0, None, None
        else:
            raise ValueError("未知标注类型")
        return Annotation(
            id=annotation.id,
            kind=template.kind,
            template_id=template.id,
            label=template.label,
            category=template.category,
            start_ms=int(start),
            end_ms=end,
            score=score,
            note=str(annotation.note or "").strip(),
            status=annotation.status,
            frame=frame,
            asset_path=str(annotation.asset_path or ""),
            created_at=annotation.created_at,
            updated_at=annotation.updated_at,
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.project, ensure_ascii=False, indent=2)
        backup = self.path.with_name(f"{self.path.stem}.previous{self.path.suffix}")
        if self.path.exists():
            try:
                backup.write_bytes(self.path.read_bytes())
            except OSError:
                pass
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.stem}.", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            self.is_dirty = False
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def relink_media(self, media_path: Path) -> None:
        path = Path(media_path)
        if not path.is_file():
            raise ValueError(f"找不到视频文件：{path}")
        replacement = {
            "path": str(path.resolve()),
            "file_name": path.name,
            "fingerprint": media_fingerprint(path),
        }
        if all(self.media.get(key) == value for key, value in replacement.items()):
            return
        self._begin_change()
        self.media.update(replacement)
        self._changed("media_relinked", "重新关联视频文件")

    def update_media_info(self, duration_ms: Optional[int] = None, fps: Optional[float] = None) -> None:
        changed = False
        if duration_ms is not None and int(duration_ms) > 0:
            value = int(duration_ms)
            if self.media.get("duration_ms") != value:
                self.media["duration_ms"] = value
                changed = True
        if fps is not None and float(fps) > 0:
            value = round(float(fps), 4)
            if self.media.get("fps") != value:
                self.media["fps"] = value
                changed = True
        if changed:
            self._changed("media_updated", "更新视频元数据")

    def replace_templates(self, templates: Sequence[TemplateItem]) -> None:
        serialised = [asdict(item) for item in templates]
        identifiers = [item["id"] for item in serialised]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("模板 ID 不能重复")
        if serialised == self.project["templates"]:
            return
        self._begin_change()
        self.project["templates"] = serialised
        self._changed("templates_updated", "更新标注模板")

    def append_templates(self, templates: Sequence[TemplateItem]) -> None:
        if not templates:
            return
        additions = [asdict(item) for item in templates]
        existing = {item["id"] for item in self.project["templates"]}
        identifiers = [item["id"] for item in additions]
        if len(set(identifiers)) != len(identifiers) or any(item in existing for item in identifiers):
            raise ValueError("导入模板与现有模板存在重复 ID")
        for item in additions:
            if not isinstance(item["label"], str) or not item["label"].strip():
                raise ValueError("标签名称不能为空")
            if item["kind"] not in VALID_KINDS:
                raise ValueError(f"模板类型无效：{item['kind']}")
            if not isinstance(item["category"], str) or not item["category"].strip():
                raise ValueError("标签分类不能为空")
        self._begin_change()
        self.project["templates"].extend(additions)
        self._changed("templates_updated", f"添加 {len(additions)} 个模板项")

    def update_template(self, template_id: str, **changes: Any) -> TemplateItem:
        """Update one template and keep denormalised annotation labels in sync."""
        permitted = {
            "label",
            "group",
            "colour",
            "start_hint",
            "end_hint",
            "required",
        }
        unexpected = set(changes) - permitted
        if unexpected:
            raise ValueError(f"不允许更新字段：{', '.join(sorted(unexpected))}")
        index = next(
            (
                item_index
                for item_index, item in enumerate(self.project["templates"])
                if item.get("id") == template_id
            ),
            None,
        )
        if index is None:
            raise KeyError(f"找不到标签 {template_id}")
        current = TemplateItem.from_dict(self.project["templates"][index])
        data = asdict(current)
        data.update(changes)
        for field_name in ("label", "group", "colour", "start_hint", "end_hint"):
            data[field_name] = str(data.get(field_name) or "").strip()
        if not data["label"]:
            raise ValueError("标签名称不能为空")
        data["group"] = data["group"] or "默认分组"
        data["required"] = bool(data.get("required", False))
        updated = TemplateItem.from_dict(data)
        if updated == current:
            return current

        self._begin_change()
        self.project["templates"][index] = asdict(updated)
        annotation_time = utc_now()
        for annotation in self.project["annotations"]:
            if annotation.get("template_id") != template_id:
                continue
            annotation["label"] = updated.label
            annotation["category"] = updated.category
            annotation["updated_at"] = annotation_time
        self._changed("template_updated", f"更新标签：{current.label} → {updated.label}")
        return updated

    def delete_template(self, template_id: str) -> TemplateItem:
        index = next(
            (
                item_index
                for item_index, item in enumerate(self.project["templates"])
                if item.get("id") == template_id
            ),
            None,
        )
        if index is None:
            raise KeyError(f"找不到标签 {template_id}")
        referenced = sum(
            1
            for annotation in self.project["annotations"]
            if annotation.get("template_id") == template_id
        )
        if referenced:
            raise ValueError(
                f"该标签已有 {referenced} 条标注记录。请先删除这些记录，"
                "或在记录编辑中改用其他标签。"
            )
        self._begin_change()
        deleted = TemplateItem.from_dict(self.project["templates"].pop(index))
        self._changed("template_deleted", f"删除标签：{deleted.label}")
        return deleted

    def add_annotation(
        self,
        template: TemplateItem,
        start_ms: int,
        end_ms: Optional[int] = None,
        note: str = "",
        status: str = "draft",
        frame: Optional[int] = None,
        asset_path: str = "",
    ) -> Annotation:
        persisted = self._template_map().get(template.id)
        if not persisted:
            raise ValueError("当前标签不属于此项目模板，无法保存标注")
        candidate = Annotation(
            id=make_id("ann"),
            kind=persisted.kind,
            template_id=persisted.id,
            label=persisted.label,
            category=persisted.category,
            start_ms=start_ms,
            end_ms=end_ms,
            note=str(note or ""),
            status=status,
            frame=frame,
            asset_path=asset_path,
        )
        annotation = self._validate_annotation(candidate, persisted)
        self._begin_change()
        self.project["annotations"].append(asdict(annotation))
        self._changed("annotation_added", f"添加{persisted.label}", annotation.id)
        return annotation

    def update_annotation(self, annotation_id: str, **changes: Any) -> Annotation:
        index = self._annotation_index(annotation_id)
        current = Annotation.from_dict(self.project["annotations"][index])
        permitted = {
            "template_id",
            "start_ms",
            "end_ms",
            "score",
            "note",
            "status",
            "frame",
            "asset_path",
        }
        unexpected = set(changes) - permitted
        if unexpected:
            raise ValueError(f"不允许更新字段：{', '.join(sorted(unexpected))}")
        target_template_id = changes.get("template_id", current.template_id)
        if not isinstance(target_template_id, str) or not target_template_id:
            raise ValueError("目标模板 ID 无效")
        template = self._template_map().get(target_template_id)
        if not template:
            raise ValueError("目标标签不属于当前项目模板")
        if template.kind != current.kind:
            raise ValueError("只能更换为相同类型的标签")
        if current.kind == "rating" and target_template_id != current.template_id:
            duplicate = any(
                item.get("id") != annotation_id
                and item.get("kind") == "rating"
                and item.get("template_id") == target_template_id
                for item in self.project["annotations"]
            )
            if duplicate:
                raise ValueError("目标评分标签已经有评分记录")
        data = asdict(current)
        data.update(changes)
        candidate = self._validate_annotation(Annotation.from_dict(data), template)
        tracked = (
            "template_id",
            "label",
            "category",
            "start_ms",
            "end_ms",
            "score",
            "note",
            "status",
            "frame",
            "asset_path",
        )
        if all(getattr(candidate, key) == getattr(current, key) for key in tracked):
            return current
        self._begin_change()
        updated = asdict(candidate)
        updated["updated_at"] = utc_now()
        self.project["annotations"][index] = updated
        detail = (
            f"将{current.label}更正为{candidate.label}"
            if candidate.template_id != current.template_id
            else f"更新{current.label}"
        )
        self._changed("annotation_updated", detail, annotation_id)
        return Annotation.from_dict(updated)

    def delete_annotation(self, annotation_id: str) -> Annotation:
        index = self._annotation_index(annotation_id)
        self._begin_change()
        deleted = Annotation.from_dict(self.project["annotations"].pop(index))
        self._changed("annotation_deleted", f"删除{deleted.label}", annotation_id)
        return deleted

    def set_rating(self, template: TemplateItem, score: int, status: str = "draft") -> Annotation:
        persisted = self._template_map().get(template.id)
        if not persisted or persisted.kind != "rating":
            raise ValueError("只有评分模板可以保存评分")
        if score not in persisted.score_options:
            raise ValueError(f"评分 {score} 不在允许范围内")
        for item in self.project["annotations"]:
            if item.get("kind") == "rating" and item.get("template_id") == persisted.id:
                return self.update_annotation(item["id"], score=score, status=status)
        candidate = Annotation(
            id=make_id("ann"),
            kind="rating",
            template_id=persisted.id,
            label=persisted.label,
            category=persisted.category,
            start_ms=0,
            score=score,
            status=status,
        )
        annotation = self._validate_annotation(candidate, persisted)
        self._begin_change()
        self.project["annotations"].append(asdict(annotation))
        self._changed("rating_set", f"{persisted.label} = {score}", annotation.id)
        return annotation

    def set_annotation_assets(self, assets: Mapping[str, str]) -> int:
        """Attach extracted images to annotations as one undoable project change."""
        requested = {
            str(annotation_id): str(asset_path or "").strip()
            for annotation_id, asset_path in assets.items()
        }
        if not requested:
            return 0
        unsafe_paths = [
            asset_path
            for asset_path in requested.values()
            if asset_path
            and (Path(asset_path).is_absolute() or ".." in Path(asset_path).parts)
        ]
        if unsafe_paths:
            raise ValueError("关联画面必须位于病例目录内")
        indices = {
            str(item.get("id")): index
            for index, item in enumerate(self.project["annotations"])
        }
        missing = sorted(set(requested) - set(indices))
        if missing:
            raise KeyError(f"找不到标注 {missing[0]}")
        invalid = [
            annotation_id
            for annotation_id in requested
            if self.project["annotations"][indices[annotation_id]].get("kind") == "rating"
        ]
        if invalid:
            raise ValueError("评分记录不能关联视频画面")
        changes = {
            annotation_id: asset_path
            for annotation_id, asset_path in requested.items()
            if str(self.project["annotations"][indices[annotation_id]].get("asset_path") or "")
            != asset_path
        }
        if not changes:
            return 0
        self._begin_change()
        now = utc_now()
        for annotation_id, asset_path in changes.items():
            item = self.project["annotations"][indices[annotation_id]]
            item["asset_path"] = asset_path
            item["updated_at"] = now
        self._changed("annotation_assets_updated", f"关联 {len(changes)} 张提取画面")
        return len(changes)

    def rating_for(self, template_id: str) -> Optional[int]:
        for item in self.project["annotations"]:
            if item.get("kind") == "rating" and item.get("template_id") == template_id:
                score = item.get("score")
                return int(score) if score is not None else None
        return None

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(self._snapshot())
        self.project = self._undo_stack.pop()
        self.project["updated_at"] = utc_now()
        self._append_audit("undo", "撤销上一步")
        self.is_dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(self._snapshot())
        self.project = self._redo_stack.pop()
        self.project["updated_at"] = utc_now()
        self._append_audit("redo", "重做上一步")
        self.is_dirty = True
        return True

    def validate(self) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        templates = self._template_map()
        duration = self._duration_limit()
        seen = set()
        annotations = self.annotations
        for annotation in annotations:
            template = templates.get(annotation.template_id)
            if not template:
                issues.append(ValidationIssue("error", f"“{annotation.label}”引用了不存在的模板", annotation.id))
                continue
            try:
                self._validate_annotation(annotation, template)
            except (TypeError, ValueError) as error:
                issues.append(ValidationIssue("error", str(error), annotation.id))
            identity = (
                annotation.kind,
                annotation.template_id,
                annotation.start_ms,
                annotation.end_ms,
                annotation.score,
            )
            if annotation.kind != "rating" and identity in seen:
                issues.append(ValidationIssue("warning", f"“{annotation.label}”存在重复标注", annotation.id))
            seen.add(identity)
            if duration and annotation.kind != "rating" and annotation.start_ms > duration:
                issues.append(ValidationIssue("error", f"“{annotation.label}”超过视频时长", annotation.id))
            if annotation.asset_path:
                relative = Path(annotation.asset_path)
                try:
                    root = self.output_directory.resolve()
                    target = (root / relative).resolve()
                    target.relative_to(root)
                except (OSError, ValueError):
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"“{annotation.label}”关联了病例目录之外的画面",
                            annotation.id,
                        )
                    )
                else:
                    if relative.is_absolute() or not target.is_file():
                        issues.append(
                            ValidationIssue(
                                "error",
                                f"“{annotation.label}”关联的画面不存在：{annotation.asset_path}",
                                annotation.id,
                            )
                        )
        for template in templates.values():
            if template.required and not any(item.template_id == template.id for item in annotations):
                issues.append(ValidationIssue("warning", f"必填标签“{template.label}”尚未标注"))

        intervals = [
            annotation
            for annotation in annotations
            if annotation.kind == "interval" and annotation.end_ms is not None
        ]
        phases = sorted(
            (
                annotation
                for annotation in intervals
                if annotation.category.lower() == "phase"
            ),
            key=lambda item: (item.start_ms, item.end_ms or item.start_ms),
        )
        tasks = [
            annotation
            for annotation in intervals
            if annotation.category.lower() != "phase"
        ]
        phase_templates = [
            template for template in templates.values()
            if template.kind == "interval" and template.category.lower() == "phase"
        ]
        if duration and phase_templates and not phases:
            issues.append(ValidationIssue("warning", "视频尚无阶段标注，阶段覆盖率为 0%"))
        if phases:
            previous = None
            phase_order = {
                template.id: index for index, template in enumerate(phase_templates)
            }
            for phase in phases:
                if previous is not None:
                    previous_end = int(previous.end_ms or previous.start_ms)
                    if phase.start_ms < previous_end:
                        issues.append(
                            ValidationIssue(
                                "error",
                                f"阶段“{phase.label}”与“{previous.label}”发生重叠",
                                phase.id,
                            )
                        )
                    elif phase.start_ms > previous_end:
                        issues.append(
                            ValidationIssue(
                                "warning",
                                f"阶段之间存在未覆盖区间：{format_timecode(previous_end)} — "
                                f"{format_timecode(phase.start_ms)}",
                                phase.id,
                            )
                        )
                    if (
                        phase_order.get(phase.template_id, 0)
                        < phase_order.get(previous.template_id, 0)
                    ):
                        issues.append(
                            ValidationIssue(
                                "warning",
                                f"阶段“{phase.label}”的顺序早于前一阶段“{previous.label}”",
                                phase.id,
                            )
                        )
                    if int(phase.end_ms or phase.start_ms) > previous_end:
                        previous = phase
                else:
                    if phase.start_ms > 0:
                        issues.append(
                            ValidationIssue(
                                "warning",
                                f"视频开头至 {format_timecode(phase.start_ms)} 尚无阶段覆盖",
                                phase.id,
                            )
                        )
                    previous = phase
            if duration and previous and int(previous.end_ms or 0) < duration:
                issues.append(
                    ValidationIssue(
                        "warning",
                        f"最后阶段结束后仍有未覆盖视频："
                        f"{format_timecode(previous.end_ms)} — {format_timecode(duration)}",
                        previous.id,
                    )
                )

        for task in tasks:
            if phases and not any(
                phase.start_ms <= task.start_ms
                and int(task.end_ms or task.start_ms)
                <= int(phase.end_ms or phase.start_ms)
                for phase in phases
            ):
                issues.append(
                    ValidationIssue(
                        "warning",
                        f"动作“{task.label}”没有完整落在任一阶段内",
                        task.id,
                    )
                )

        by_template: Dict[str, List[Annotation]] = {}
        for annotation in tasks:
            by_template.setdefault(annotation.template_id, []).append(annotation)
        for repeated in by_template.values():
            repeated.sort(key=lambda item: (item.start_ms, item.end_ms or item.start_ms))
            previous = None
            for annotation in repeated:
                if previous and annotation.start_ms < int(previous.end_ms or previous.start_ms):
                    issues.append(
                        ValidationIssue(
                            "warning",
                            f"同一动作“{annotation.label}”的区间发生重叠",
                            annotation.id,
                        )
                    )
                if previous is None or int(annotation.end_ms or 0) > int(previous.end_ms or 0):
                    previous = annotation
        return issues

    def phase_coverage_ratio(self) -> float:
        duration = self._duration_limit()
        if duration <= 0:
            return 0.0
        phases = [
            annotation
            for annotation in self.annotations
            if annotation.kind == "interval"
            and annotation.category.lower() == "phase"
        ]
        return min(1.0, interval_coverage_ms(phases, duration) / duration)

    def export_csv(self, output_path: Path) -> Path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fields = (
            "project_id", "video_file", "annotation_id", "kind", "category",
            "template_id", "label", "start_ms", "end_ms", "start_timecode",
            "end_timecode", "frame", "score", "status", "note", "asset_path",
            "created_at", "updated_at",
        )
        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for annotation in sorted(self.annotations, key=lambda item: (item.start_ms, item.created_at)):
                row = asdict(annotation)
                row.update(
                    {
                        "project_id": self.project["project_id"],
                        "video_file": self.media.get("file_name", ""),
                        "annotation_id": annotation.id,
                        "start_timecode": format_timecode(annotation.start_ms),
                        "end_timecode": format_timecode(annotation.end_ms),
                    }
                )
                row.pop("id", None)
                writer.writerow(row)
        return output_path

    def sync_default_exports(self) -> Tuple[Path, List[Path]]:
        """Refresh the always-available interoperability files for this case."""
        output_directory = self.output_directory / "exports"
        output_directory.mkdir(parents=True, exist_ok=True)
        try:
            previous_files = set(self._read_legacy_manifest(output_directory))
        except ValueError:
            # A damaged user-edited manifest must not block fresh export output.
            previous_files = set()
        csv_path = self.export_csv(output_directory / "annotations.csv")
        legacy_paths = self.export_legacy(output_directory)
        current_files = {path.name for path in legacy_paths}
        for filename in previous_files - current_files:
            stale_path = output_directory / filename
            try:
                if stale_path.is_file():
                    stale_path.unlink()
            except OSError:
                # Current output has already been refreshed; a locked obsolete
                # compatibility file should not invalidate the project save.
                pass
        return csv_path, legacy_paths

    def export_legacy(self, output_directory: Path) -> List[Path]:
        output_directory = Path(output_directory)
        output_directory.mkdir(parents=True, exist_ok=True)
        written: List[Path] = []
        used_names: Dict[str, str] = {}
        manifest_entries: List[Dict[str, str]] = []

        def legacy_path(category: str, suffix: str = "") -> Path:
            base = safe_filename(category)
            filename = f"{base}{suffix}.txt"
            owner = used_names.get(filename)
            if owner and owner != category:
                filename = f"{base}_{hashlib.sha256(category.encode('utf-8')).hexdigest()[:8]}{suffix}.txt"
            used_names[filename] = category
            return output_directory / filename

        annotations = self.annotations
        categories = sorted({item.category for item in annotations if item.kind in {"interval", "point"}})
        for category in categories:
            path = legacy_path(category)
            rows = [
                item for item in annotations
                if item.category == category and item.kind in {"interval", "point"}
            ]
            with path.open("w", encoding="utf-8") as handle:
                for item in sorted(rows, key=lambda row: (row.start_ms, row.label, row.id)):
                    end = item.end_ms if item.end_ms is not None else 0
                    handle.write(
                        f"{item.label} : ({format_legacy_timecode(item.start_ms)},"
                        f"{format_legacy_timecode(end)})\n"
                    )
            written.append(path)
            manifest_entries.append(
                {"file": path.name, "category": category, "kind": "interval"}
            )

        rating_categories: Dict[str, List[TemplateItem]] = {}
        for template in self.templates:
            if template.kind == "rating":
                rating_categories.setdefault(template.category, []).append(template)
        for category, templates in rating_categories.items():
            path = legacy_path(category, "_scores")
            with path.open("w", encoding="utf-8") as handle:
                for template in templates:
                    score = self.rating_for(template.id)
                    handle.write(
                        f"{template.label} : {score}\n"
                        if score is not None else f"{template.label}\n"
                    )
            written.append(path)
            manifest_entries.append(
                {"file": path.name, "category": category, "kind": "rating"}
            )
        manifest_path = output_directory / "surgui_legacy_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "files": manifest_entries,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return written

    @staticmethod
    def _read_legacy_manifest(directory: Path) -> Dict[str, Tuple[str, str]]:
        """Return filename -> (route kind, original category) for our exports."""
        path = Path(directory) / "surgui_legacy_manifest.json"
        if not path.is_file():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeError) as error:
            raise ValueError(f"旧版导入映射文件无效：{error}") from error
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("旧版导入映射文件版本不受支持")
        entries = payload.get("files")
        if not isinstance(entries, list):
            raise ValueError("旧版导入映射文件缺少 files 列表")
        routes: Dict[str, Tuple[str, str]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("旧版导入映射条目无效")
            filename = entry.get("file")
            category = entry.get("category")
            route_kind = entry.get("kind")
            if (
                not isinstance(filename, str)
                or Path(filename).name != filename
                or not filename.lower().endswith(".txt")
                or not isinstance(category, str)
                or not category
                or route_kind not in {"interval", "rating"}
                or filename in routes
            ):
                raise ValueError("旧版导入映射条目字段无效")
            routes[filename] = (route_kind, category)
        return routes

    def import_legacy_annotations(self, directory: Path) -> List[ValidationIssue]:
        """Read all old txt files first, then commit one atomic project change."""
        directory = Path(directory)
        if not directory.is_dir():
            raise ValueError(f"旧版标注目录不存在：{directory}")
        interval_templates: Dict[Tuple[str, str], List[TemplateItem]] = {}
        rating_templates: Dict[Tuple[str, str], List[TemplateItem]] = {}
        for template in self.templates:
            key = (template.category, template.label)
            if template.kind in {"interval", "point"}:
                interval_templates.setdefault(key, []).append(template)
            elif template.kind == "rating":
                rating_templates.setdefault(key, []).append(template)

        reports: List[ValidationIssue] = []
        manifest_routes = self._read_legacy_manifest(directory)
        interval_file_categories: Dict[str, List[str]] = {}
        rating_file_categories: Dict[str, List[str]] = {}
        for category in {category for category, _ in interval_templates}:
            interval_file_categories.setdefault(safe_filename(category), []).append(category)
        for category in {category for category, _ in rating_templates}:
            rating_file_categories.setdefault(
                f"{safe_filename(category)}_scores", []
            ).append(category)

        candidate_entries = copy.deepcopy(self.project["annotations"])
        identities = {
            (
                item.get("kind"), item.get("template_id"), item.get("start_ms"),
                item.get("end_ms"), item.get("score"),
            )
            for item in candidate_entries
        }
        interval_pattern = re.compile(r"^\s*(.*?)\s*:\s*\(([^,]+),([^)]*)\)\s*$")
        imported = 0
        for file_path in sorted(directory.glob("*.txt"), key=lambda value: value.name.lower()):
            with file_path.open("r", encoding="utf-8-sig", errors="replace") as handle:
                lines = list(handle)
            route = manifest_routes.get(file_path.name)
            if route:
                route_kind, category = route
            else:
                interval_candidates = interval_file_categories.get(file_path.stem, [])
                rating_candidates = rating_file_categories.get(file_path.stem, [])
                if len(interval_candidates) == 1 and not rating_candidates:
                    route_kind, category = "interval", interval_candidates[0]
                elif len(rating_candidates) == 1 and not interval_candidates:
                    route_kind, category = "rating", rating_candidates[0]
                elif interval_candidates or rating_candidates:
                    reports.append(
                        ValidationIssue(
                            "warning",
                            f"{file_path.name} 文件名对应多个模板分类；请使用带映射文件的导出结果。",
                        )
                    )
                    continue
                elif file_path.stem.endswith("_scores"):
                    route_kind, category = "rating", file_path.stem[: -len("_scores")]
                else:
                    route_kind, category = "interval", file_path.stem

            if route_kind == "rating":
                rating_category = category
                for line_number, raw in enumerate(lines, start=1):
                    text = raw.strip()
                    if not text or " : " not in text:
                        continue
                    label, raw_score = text.rsplit(" : ", 1)
                    choices = rating_templates.get((rating_category, label.strip()), [])
                    if not choices:
                        reports.append(ValidationIssue("warning", f"{file_path.name}:{line_number} 找不到评分标签"))
                        continue
                    try:
                        score = int(raw_score.strip())
                    except ValueError:
                        reports.append(ValidationIssue("warning", f"{file_path.name}:{line_number} 评分无效"))
                        continue
                    template = choices[0]
                    if score not in template.score_options:
                        reports.append(ValidationIssue("warning", f"{file_path.name}:{line_number} 评分超出范围"))
                        continue
                    index = next(
                        (
                            position for position, item in enumerate(candidate_entries)
                            if item.get("kind") == "rating" and item.get("template_id") == template.id
                        ),
                        None,
                    )
                    if index is None:
                        annotation = self._validate_annotation(
                            Annotation(
                                id=make_id("ann"),
                                kind="rating",
                                template_id=template.id,
                                label=template.label,
                                category=template.category,
                                start_ms=0,
                                score=score,
                            ),
                            template,
                        )
                        candidate_entries.append(asdict(annotation))
                        imported += 1
                    elif candidate_entries[index].get("score") != score:
                        candidate_entries[index]["score"] = score
                        candidate_entries[index]["status"] = "draft"
                        candidate_entries[index]["updated_at"] = utc_now()
                        imported += 1
                continue

            for line_number, raw in enumerate(lines, start=1):
                match = interval_pattern.match(raw)
                if not match:
                    if raw.strip():
                        reports.append(ValidationIssue("warning", f"{file_path.name}:{line_number} 格式无法识别"))
                    continue
                label, raw_start, raw_end = match.groups()
                choices = interval_templates.get((category, label), [])
                if not choices:
                    reports.append(ValidationIssue("warning", f"{file_path.name}:{line_number} 找不到标签"))
                    continue
                template = choices[0]
                try:
                    candidate = Annotation(
                        id=make_id("ann"),
                        kind=template.kind,
                        template_id=template.id,
                        label=template.label,
                        category=template.category,
                        start_ms=parse_timecode(raw_start),
                        end_ms=None if template.kind == "point" else parse_timecode(raw_end),
                    )
                    annotation = self._validate_annotation(candidate, template)
                except ValueError as error:
                    reports.append(ValidationIssue("warning", f"{file_path.name}:{line_number} {error}"))
                    continue
                identity = (
                    annotation.kind, annotation.template_id, annotation.start_ms,
                    annotation.end_ms, annotation.score,
                )
                if identity in identities:
                    reports.append(ValidationIssue("warning", f"{file_path.name}:{line_number} 与已有标注重复，已跳过"))
                    continue
                candidate_entries.append(asdict(annotation))
                identities.add(identity)
                imported += 1
        if imported:
            self._begin_change()
            self.project["annotations"] = candidate_entries
            self._changed("legacy_imported", f"导入 {imported} 条旧标注")
        return reports
