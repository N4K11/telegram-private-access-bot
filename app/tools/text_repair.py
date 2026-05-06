from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.texts import iter_default_template_texts
from app.utils.encoding import is_mojibake, repair_mojibake_text

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_RELATIVE_PATHS = (
    "app",
    "tests",
    "web",
    "README.md",
    "DEPLOY.md",
    "TESTING.md",
    "PROJECT_OVERVIEW.md",
    "CHANGELOG.md",
)
TEXT_EXTENSIONS = {".py", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini"}
SKIP_DIRECTORIES = {"__pycache__", ".git", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
SKIP_FILES = {Path("app/utils/encoding.py")}


@dataclass(slots=True)
class FileIssue:
    path: Path
    line_number: int
    original: str
    repaired: str | None


@dataclass(slots=True)
class TemplateIssue:
    label: str
    original: str
    repaired: str | None


def iter_candidate_files(root: Path = REPO_ROOT) -> list[Path]:
    files: list[Path] = []
    for relative in SCAN_RELATIVE_PATHS:
        path = root / relative
        if not path.exists():
            continue
        if path.is_file():
            files.append(path)
            continue
        for candidate in path.rglob("*"):
            if not candidate.is_file():
                continue
            if any(part in SKIP_DIRECTORIES for part in candidate.parts):
                continue
            if candidate.suffix.lower() not in TEXT_EXTENSIONS:
                continue
            if candidate.relative_to(root) in SKIP_FILES:
                continue
            files.append(candidate)
    return sorted(files)


def scan_file(path: Path) -> list[FileIssue]:
    issues: list[FileIssue] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if "# mojibake-allow" in line:
            continue
        if not is_mojibake(line):
            continue
        repaired = repair_mojibake_text(line)
        issues.append(
            FileIssue(
                path=path,
                line_number=index,
                original=line,
                repaired=repaired if repaired != line else None,
            )
        )
    return issues


def scan_repository(root: Path = REPO_ROOT) -> list[FileIssue]:
    issues: list[FileIssue] = []
    for path in iter_candidate_files(root):
        issues.extend(scan_file(path))
    return issues


def repair_file(path: Path) -> int:
    original_lines = path.read_text(encoding="utf-8").splitlines()
    changed = 0
    repaired_lines: list[str] = []

    for line in original_lines:
        if "# mojibake-allow" in line:
            repaired_lines.append(line)
            continue
        if not is_mojibake(line):
            repaired_lines.append(line)
            continue
        repaired = repair_mojibake_text(line)
        if repaired is not None and repaired != line:
            repaired_lines.append(repaired)
            changed += 1
            continue
        repaired_lines.append(line)

    if changed:
        path.write_text("\n".join(repaired_lines) + "\n", encoding="utf-8", newline="\n")
    return changed


def repair_repository(root: Path = REPO_ROOT) -> list[tuple[Path, int]]:
    repaired: list[tuple[Path, int]] = []
    for path in iter_candidate_files(root):
        changed = repair_file(path)
        if changed:
            repaired.append((path, changed))
    return repaired


def scan_default_template_issues() -> list[TemplateIssue]:
    issues: list[TemplateIssue] = []
    for label, value in iter_default_template_texts():
        if not is_mojibake(value):
            continue
        repaired = repair_mojibake_text(value)
        issues.append(
            TemplateIssue(
                label=label,
                original=value,
                repaired=repaired if repaired != value else None,
            )
        )
    return issues
