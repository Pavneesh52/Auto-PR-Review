"""Tests for the CLI entry point."""

from __future__ import annotations

from pr_review_agent.cli import _parse_args, _should_index


class TestParseArgs:
    def test_defaults_to_serve(self):
        args = _parse_args([])
        assert args.command is None  # None means serve

    def test_serve_command(self):
        args = _parse_args(["serve"])
        assert args.command == "serve"

    def test_index_command(self):
        args = _parse_args(["index", "org/repo"])
        assert args.command == "index"
        assert args.repo == "org/repo"
        assert args.max_files == 200

    def test_index_options(self):
        args = _parse_args(["index", "org/repo", "--ref", "develop", "--max-files", "5"])
        assert args.ref == "develop"
        assert args.max_files == 5


class TestShouldIndex:
    def test_source_files_are_indexed(self):
        assert _should_index("src/app.py") is True
        assert _should_index("web/index.ts") is True
        assert _should_index("cmd/main.go") is True

    def test_lock_files_are_skipped(self):
        assert _should_index("poetry.lock") is False
        assert _should_index("package-lock.json") is False

    def test_vendored_and_build_dirs_are_skipped(self):
        assert _should_index("node_modules/left-pad/index.js") is False
        assert _should_index("vendor/lib/thing.go") is False
        assert _should_index("dist/bundle.js") is False

    def test_unknown_extensions_are_skipped(self):
        assert _should_index("README") is False
        assert _should_index("assets/logo.png") is False
