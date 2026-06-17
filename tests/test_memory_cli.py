"""
Tests for the iSH-Memory Command Line Interface (CLI).
"""

import os
import sys
import subprocess
import tempfile
import json
from pathlib import Path

# Resolve path to the CLI script
CLI_PATH = str(Path(__file__).parent.parent / "src/tools/custom_tools/ish-memory/scripts/memory_cli.py")

def run_cli(args, env=None):
    """Helper to run the CLI script with given arguments and environment."""
    cmd = [sys.executable, CLI_PATH] + args
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return result

def test_cli_help():
    """Verify that the CLI help option works and exits with code 0."""
    res = run_cli(["-h"])
    assert res.returncode == 0
    assert "iSH-Memory Command Line Interface" in res.stdout

def test_cli_add_and_get():
    """Verify adding and then retrieving a memory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Add memory
        content = "This is a CLI test memory."
        res = run_cli(["--db", db_path, "add", content, "--wing", "test-wing", "--room", "test-room"])
        assert res.returncode == 0
        assert "Memory added successfully. ID: 1" in res.stdout
        
        # Get memory
        res_get = run_cli(["--db", db_path, "get", "1"])
        assert res_get.returncode == 0
        assert "ID: 1" in res_get.stdout
        assert "Wing: test-wing" in res_get.stdout
        assert "Room: test-room" in res_get.stdout
        assert f"Content: {content}" in res_get.stdout
        assert "Metadata: None" in res_get.stdout

def test_cli_add_with_metadata():
    """Verify adding a memory with valid/invalid metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Invalid JSON
        res = run_cli(["--db", db_path, "add", "content", "--wing", "w", "--room", "r", "--metadata", "{invalid_json}"])
        assert res.returncode != 0
        assert "Error: Invalid JSON for metadata" in res.stderr
        
        # Valid JSON
        metadata = {"version": 3, "tags": ["test", "cli"]}
        res = run_cli(["--db", db_path, "add", "content", "--wing", "w", "--room", "r", "--metadata", json.dumps(metadata)])
        assert res.returncode == 0
        assert "Memory added successfully. ID: 1" in res.stdout
        
        # Get memory and verify metadata
        res_get = run_cli(["--db", db_path, "get", "1"])
        assert res_get.returncode == 0
        # Check that metadata is printed in JSON format
        assert '"version": 3' in res_get.stdout
        assert '"tags": ["test", "cli"]' in res_get.stdout

def test_cli_search():
    """Verify searching memories via CLI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Add a couple of memories
        run_cli(["--db", db_path, "add", "Python programming language", "--wing", "dev", "--room", "python"])
        run_cli(["--db", db_path, "add", "Rust systems programming", "--wing", "dev", "--room", "rust"])
        
        # Search for "programming"
        res = run_cli(["--db", db_path, "search", "programming"])
        assert res.returncode == 0
        assert "ID: 1" in res.stdout
        assert "ID: 2" in res.stdout
        assert "Python programming language" in res.stdout
        assert "Rust systems programming" in res.stdout
        
        # Search with wing filter
        res_filter = run_cli(["--db", db_path, "search", "programming", "--wing", "dev", "--room", "rust"])
        assert res_filter.returncode == 0
        assert "ID: 2" in res_filter.stdout
        assert "ID: 1" not in res_filter.stdout
        
        # Search non-existent
        res_none = run_cli(["--db", db_path, "search", "nonexistent_query"])
        assert res_none.returncode == 0
        assert "No matching memories found." in res_none.stdout

def test_cli_get_nonexistent():
    """Verify getting a non-existent memory fails gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        res = run_cli(["--db", db_path, "get", "999"])
        assert res.returncode != 0
        assert "Error: Memory with ID 999 not found." in res.stderr

def test_cli_delete():
    """Verify deleting a memory works."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        
        # Add memory
        run_cli(["--db", db_path, "add", "To be deleted", "--wing", "test", "--room", "test"])
        
        # Delete memory
        res = run_cli(["--db", db_path, "delete", "1"])
        assert res.returncode == 0
        assert "Memory with ID 1 deleted successfully." in res.stdout
        
        # Verify it's gone
        res_get = run_cli(["--db", db_path, "get", "1"])
        assert res_get.returncode != 0
        
        # Delete non-existent
        res_del_nonexistent = run_cli(["--db", db_path, "delete", "999"])
        assert res_del_nonexistent.returncode != 0
        assert "Error: Memory with ID 999 not found." in res_del_nonexistent.stderr

def test_cli_env_override():
    """Verify that HARNESS_MEMORY_DB environment variable overrides the default database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "env_test.db")
        
        # Prepare environment
        custom_env = os.environ.copy()
        custom_env["HARNESS_MEMORY_DB"] = db_path
        
        # Add memory without passing --db
        res = run_cli(["add", "Env test memory", "--wing", "env", "--room", "env"], env=custom_env)
        assert res.returncode == 0
        assert "Memory added successfully. ID: 1" in res.stdout
        
        # Verify the database file was created at db_path
        assert os.path.exists(db_path)
