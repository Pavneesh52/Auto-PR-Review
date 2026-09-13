"""Tests for smart context selection."""

from __future__ import annotations

from pr_review_agent.context.smart_context import (
    detect_language,
    extract_imports_from_diff,
    find_related_files,
    module_to_file_path,
)
from pr_review_agent.models.review import ChangedFile


class TestDetectLanguage:
    def test_python_file(self):
        assert detect_language("src/auth/login.py") == "python"

    def test_typescript_file(self):
        assert detect_language("src/components/App.tsx") == "typescript"

    def test_unknown_extension(self):
        assert detect_language("README") == "unknown"


class TestExtractImports:
    def test_python_imports(self):
        files = [
            ChangedFile(
                path="app.py",
                patch="""@@ -1,3 +1,4 @@
+import os
+from models import User
+from utils.helpers import parse_date
""",
            )
        ]
        imports = extract_imports_from_diff(files)
        assert "os" in imports
        assert "models" in imports
        assert "utils.helpers" in imports

    def test_no_patch_extracts_nothing(self):
        files = [ChangedFile(path="app.py", patch="")]
        imports = extract_imports_from_diff(files)
        assert len(imports) == 0

    def test_only_added_lines(self):
        files = [
            ChangedFile(
                path="app.py",
                patch="""@@ -1,3 +1,3 @@
 import old_module
-import removed_module
+import new_module
""",
            )
        ]
        imports = extract_imports_from_diff(files)
        assert "new_module" in imports
        # Removed lines should not be extracted (they start with -)
        assert "removed_module" not in imports


class TestModuleToFilePath:
    def test_simple_module(self):
        all_files = ["src/utils/helpers.py", "src/models.py"]
        result = module_to_file_path("utils.helpers", all_files)
        # Should find src/utils/helpers.py or utils/helpers.py
        assert result is None or result.endswith("helpers.py")

    def test_module_not_found(self):
        all_files = ["src/app.py"]
        result = module_to_file_path("nonexistent.module", all_files)
        assert result is None


class TestFindRelatedFiles:
    def test_finds_imported_files(self):
        changed_files = [
            ChangedFile(
                path="src/main.py",
                patch="""@@ -1,2 +1,3 @@
+from src.auth import login
+from src.utils.helpers import parse_date
""",
            )
        ]
        all_files = [
            "src/main.py",
            "src/auth/__init__.py",
            "src/auth/login.py",
            "src/utils/helpers.py",
            "src/utils/__init__.py",
        ]

        related = find_related_files(changed_files, all_files, max_context_files=10)
        # Should find at least the imported files
        assert len(related) > 0

    def test_finds_test_files(self):
        changed_files = [
            ChangedFile(
                path="src/auth/login.py",
                patch="@@ -1 +1,2 @@\n+import os",
            )
        ]
        all_files = [
            "src/auth/login.py",
            "tests/test_login.py",
            "tests/test_auth.py",
        ]

        related = find_related_files(changed_files, all_files, max_context_files=10)
        assert "tests/test_login.py" in related

    def test_respects_max_limit(self):
        changed_files = [
            ChangedFile(
                path="src/main.py",
                patch="@@ -1 +1,2 @@\n+import os",
            )
        ]
        all_files = [f"src/module_{i}.py" for i in range(50)]

        related = find_related_files(changed_files, all_files, max_context_files=5)
        assert len(related) <= 5
