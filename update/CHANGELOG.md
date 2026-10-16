# Change Log

## 2026-10-16 - Refresh the software README

Status: Done

Summary:
- Added a Markdown README for the GitHub repository homepage, grounded in the current workbench, storage implementation, templates and package configuration.
- Expanded installation, the first annotation workflow, shortcuts, review states, project backups, CSV fields, frame extraction, legacy migration and troubleshooting.
- Preserved the existing plain-text README and its output-location guidance, adding a pointer to the full guide and clarifying LabelMe discovery and zero-based score options.

Changed files:
- `README.md`: complete Chinese user guide and development verification commands.
- `README.txt`: full-guide pointer and focused usage clarifications.
- `update/CHANGELOG.md`: record this documentation update.

Documentation impact:
- `README.md` is the full user guide; `README.txt` remains a plain-text reference.
- No application code, packaging scripts or annotation data changed in this update.

Verification:
- `.venv/Scripts/python.exe -m unittest discover -s tests -q`: 56 tests passed.
- `.venv/Scripts/python.exe -m compileall -q surgui tests`: passed.
- README audit: local links resolve, Markdown fences balance, CSV columns match the implementation, and template examples parse as documented.
- Project maintenance validator and Git whitespace checks: passed.

Follow-up:
- None.

## 2026-08-09 - Stability and data-integrity repair

Status: Done

Summary:
- Hardened project recovery, metadata/template invariants, append-only audit history, legacy import/export routing, video switching, media relinking, output migration, VLC teardown/seeking, frame stepping, FPS handling, and installed resource/output discovery.
- Made LabelMe consistently optional, refreshed the Windows launcher for current executable names, and stopped the legacy PyInstaller spec from bundling the demo video.
- Added focused storage, playback, Qt interaction, installation-layout, and packaging regression coverage.

Changed files:
- `surgui/project_store.py`: preserve valid recovery backups, make metadata updates atomic, enforce storage invariants, retain audit events, and make legacy routing collision-safe.
- `surgui/vidPlayer_working.py`: prevent stale project reloads and destructive migration/relink behavior; repair VLC lifecycle, authoritative seeking, frame stepping, and FPS fallback behavior.
- `surgui/theme.py`: discover target/user install assets and choose a per-user writable root outside source/frozen layouts.
- `requirements.txt`: remove optional LabelMe from mandatory runtime dependencies.
- `run_surgui.bat`: recognize current packaged executables and preflight Python runtimes.
- `vidPlayer_working.spec`: package only runtime sample text/image assets.
- `tests/test_project_store.py`, `tests/test_video_backend.py`, `tests/test_theme_tokens.py`, `tests/test_workbench_interactions.py`: add regression coverage and isolate autosave timers.

Documentation impact:
- `README.txt`: documented source, portable, and pip-installed output locations.

Verification:
- `.venv\\Scripts\\python.exe -m unittest discover -s tests -q`: 56 tests passed.
- `.venv\\Scripts\\python.exe -m compileall -q surgui tests`: passed.
- `.venv\\Scripts\\python.exe -m pip check`: no broken requirements found.
- `.venv\\Scripts\\python.exe setup.py check --strict`: passed.
- Isolated setuptools install-root smoke check: installed theme assets and 50 default templates were discovered; the writable root resolved to the current user's application-data directory.

Follow-up:
- None.
