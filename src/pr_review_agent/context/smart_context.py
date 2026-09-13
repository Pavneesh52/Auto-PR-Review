"""Smart context selection.

Phase 3 - Only fetch files that the diff actually references
(imports, shared types, called functions) rather than loading
the whole repo. This keeps token costs under control.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from pr_review_agent.models.review import ChangedFile


def extract_imports_from_diff(changed_files: list[ChangedFile]) -> set[str]:
    """Extract import paths from diff patches.

    Parses the added lines in each diff hunk to find import statements.
    Returns file paths that might need to be fetched as context.
    """
    import_patterns = [
        # Python
        r"(?:from|import)\s+([\w.]+)",
        # JavaScript/TypeScript
        r"""(?:import|require)\s*\(?['"]([^'"]+)['"]\)?""",
        # Go
        r'"([^"]+)"',
        # Java
        r"import\s+([\w.]+);",
    ]

    referenced_modules: set[str] = set()

    for file in changed_files:
        if not file.patch:
            continue

        # Only look at added lines (start with +)
        added_lines = [line[1:] for line in file.patch.split("\n") if line.startswith("+")]

        for line in added_lines:
            for pattern in import_patterns:
                for match in re.finditer(pattern, line):
                    referenced_modules.add(match.group(1))

    return referenced_modules


def module_to_file_path(module: str, all_files: list[str]) -> str | None:
    """Convert a module import to a likely file path in the repo.

    E.g., "utils.helpers" -> "src/utils/helpers.py" or "utils/helpers.py"
    """
    # Try direct path conversion
    parts = module.replace(".", "/")

    # Check common patterns
    candidates = [
        f"{parts}.py",
        f"{parts}/__init__.py",
        f"{parts}.ts",
        f"{parts}.js",
        f"src/{parts}.py",
        f"src/{parts}/__init__.py",
        f"src/{parts}.ts",
        f"lib/{parts}.py",
    ]

    file_set = set(all_files)
    for candidate in candidates:
        if candidate in file_set:
            return candidate

    return None


def find_related_files(
    changed_files: list[ChangedFile],
    all_repo_files: list[str],
    max_context_files: int = 20,
) -> list[str]:
    """Find files that should be fetched as context for the review.

    Strategy:
    1. Extract imports from the diff
    2. Convert imports to file paths
    3. Look for files in the same directory
    4. Look for test files matching changed files
    5. Limit to max_context_files

    Returns:
        List of file paths to fetch.
    """
    context_candidates: list[str] = []

    # 1. Files referenced by imports in the diff
    imports = extract_imports_from_diff(changed_files)
    for module in imports:
        file_path = module_to_file_path(module, all_repo_files)
        if file_path:
            context_candidates.append(file_path)

    # 2. Sibling files (same directory)
    seen_dirs: set[str] = set()
    for file in changed_files:
        dir_name = str(PurePosixPath(file.path).parent)
        if dir_name not in seen_dirs:
            seen_dirs.add(dir_name)
            for repo_file in all_repo_files:
                if (
                    repo_file.startswith(dir_name + "/")
                    and repo_file != file.path
                    and repo_file not in context_candidates
                ):
                    context_candidates.append(repo_file)

    # 3. Test files for changed files
    for file in changed_files:
        stem = PurePosixPath(file.path).stem
        parent = PurePosixPath(file.path).parent
        test_patterns = [
            f"{parent}/test_{stem}.py",
            f"{parent}/tests/test_{stem}.py",
            f"{parent}/{stem}.test.ts",
            f"{parent}/{stem}.spec.ts",
            f"{parent}/__tests__/{stem}.test.ts",
            # Also check root-level tests/ directory
            f"tests/test_{stem}.py",
            f"test_{stem}.py",
        ]
        for pattern in test_patterns:
            if pattern in all_repo_files and pattern not in context_candidates:
                context_candidates.append(pattern)

    # 4. Deduplicate and limit
    seen: set[str] = set()
    unique: list[str] = []
    for path in context_candidates:
        if path not in seen:
            seen.add(path)
            unique.append(path)
            if len(unique) >= max_context_files:
                break

    return unique


def detect_language(file_path: str) -> str:
    """Detect the programming language from file extension."""
    ext_map = {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
        ".cs": "csharp",
        ".cpp": "cpp",
        ".c": "c",
        ".h": "c",
        ".hpp": "cpp",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".md": "markdown",
        ".sql": "sql",
        ".sh": "shell",
        ".bash": "shell",
    }
    suffix = PurePosixPath(file_path).suffix.lower()
    return ext_map.get(suffix, "unknown")
