from __future__ import annotations

import argparse

from app.tools.text_repair import (
    REPO_ROOT,
    repair_repository,
    scan_default_template_issues,
    scan_repository,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Repair mojibake in repository text files.")
    parser.add_argument("--apply", action="store_true", help="Apply file-level repairs in-place.")
    args = parser.parse_args()

    template_issues = scan_default_template_issues()
    file_issues = scan_repository()

    if not args.apply:
        if not template_issues and not file_issues:
            print("Nothing to repair.")
            return 0
        print("Template issues:", len(template_issues))
        print("File issues:", len(file_issues))
        print(
            "Run with --apply to repair repository files. "
            "Managed DB templates are auto-repaired on startup."
        )
        return 1

    repaired = repair_repository()
    print(f"Repaired files: {len(repaired)}")
    for path, changed in repaired:
        relative_path = path.relative_to(REPO_ROOT) if path.is_absolute() else path
        print(f"  {relative_path}: {changed} line(s)")

    remaining_template_issues = scan_default_template_issues()
    remaining_file_issues = scan_repository()
    if not remaining_template_issues and not remaining_file_issues:
        print("Repair complete. No mojibake remains in scanned repository files.")
        return 0

    print("Repair finished, but some issues remain.")
    print("Template issues:", len(remaining_template_issues))
    print("File issues:", len(remaining_file_issues))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
