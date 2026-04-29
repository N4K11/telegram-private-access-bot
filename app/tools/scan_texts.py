from __future__ import annotations

from app.tools.text_repair import REPO_ROOT, scan_default_template_issues, scan_repository


def main() -> int:
    template_issues = scan_default_template_issues()
    file_issues = scan_repository()

    if not template_issues and not file_issues:
        print("No mojibake found in managed templates or repository files.")
        return 0

    if template_issues:
        print("Managed template issues:")
        for issue in template_issues:
            repaired = f" -> {issue.repaired}" if issue.repaired else ""
            print(f"  {issue.label}: {issue.original}{repaired}")

    if file_issues:
        print("Repository file issues:")
        for issue in file_issues:
            relative_path = (
                issue.path.relative_to(REPO_ROOT) if issue.path.is_absolute() else issue.path
            )
            repaired = f" -> {issue.repaired}" if issue.repaired else ""
            print(f"  {relative_path}:{issue.line_number}: {issue.original}{repaired}")

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
