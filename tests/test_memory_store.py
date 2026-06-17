"""
Tests for the MemoryStore SQLite storage engine.
"""

import os
import sys
import tempfile
import sqlite3
from pathlib import Path

# Add the src/ directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harness.memory_store import MemoryStore

def test_memory_store_in_memory():
    """Test that MemoryStore works with :memory: database."""
    store = MemoryStore(":memory:")
    assert store.db_path == ":memory:"
    
    # Check that tables are created
    cursor = store.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memories'")
    assert cursor.fetchone() is not None
    
    cursor = store.conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fts_memories'")
    assert cursor.fetchone() is not None
    
    store.close()

def test_memory_store_temp_file():
    """Test that MemoryStore works with a temporary database file and directory creation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "subdir", "test_memory.db")
        store = MemoryStore(db_path)
        assert os.path.exists(db_path)
        
        # Insert a memory
        row_id = store.add_memory("Hello, this is a test memory.", "test-wing", "test-room", {"author": "pytest"})
        assert row_id == 1
        
        # Retrieve it
        memory = store.get_memory(row_id)
        assert memory is not None
        assert memory["id"] == row_id
        assert memory["content"] == "Hello, this is a test memory."
        assert memory["wing"] == "test-wing"
        assert memory["room"] == "test-room"
        assert memory["metadata"] == {"author": "pytest"}
        assert memory["created_at"] is not None
        
        store.close()

def test_memory_store_add_get_delete():
    """Test standard add, get, and delete operations."""
    store = MemoryStore(":memory:")
    
    # Retrieve non-existent
    assert store.get_memory(999) is None
    
    # Add memory with no metadata
    id1 = store.add_memory("No metadata here", "general", "misc")
    assert id1 == 1
    
    memory1 = store.get_memory(id1)
    assert memory1 is not None
    assert memory1["content"] == "No metadata here"
    assert memory1["metadata"] is None
    
    # Delete memory
    assert store.delete_memory(id1) is True
    assert store.get_memory(id1) is None
    
    # Delete non-existent
    assert store.delete_memory(id1) is False
    
    store.close()

def test_memory_store_fts_trigger_sync():
    """Test that the FTS5 triggers keep the virtual table in sync."""
    store = MemoryStore(":memory:")
    
    # Insert two memories
    id1 = store.add_memory("Python programming language", "dev", "python")
    id2 = store.add_memory("Rust systems programming", "dev", "rust")
    
    # Search for 'programming'
    cursor = store.conn.execute(
        "SELECT rowid FROM fts_memories WHERE fts_memories MATCH 'programming'"
    )
    results = [row[0] for row in cursor.fetchall()]
    assert len(results) == 2
    assert id1 in results
    assert id2 in results
    
    # Search for 'Python'
    cursor = store.conn.execute(
        "SELECT rowid FROM fts_memories WHERE fts_memories MATCH 'Python'"
    )
    results = [row[0] for row in cursor.fetchall()]
    assert len(results) == 1
    assert results[0] == id1
    
    # Delete id1
    store.delete_memory(id1)
    
    # Search for 'Python' again (should be empty)
    cursor = store.conn.execute(
        "SELECT rowid FROM fts_memories WHERE fts_memories MATCH 'Python'"
    )
    results = [row[0] for row in cursor.fetchall()]
    assert len(results) == 0
    
    # Search for 'programming' again (should only have id2)
    cursor = store.conn.execute(
        "SELECT rowid FROM fts_memories WHERE fts_memories MATCH 'programming'"
    )
    results = [row[0] for row in cursor.fetchall()]
    assert len(results) == 1
    assert results[0] == id2
    
    store.close()

def test_search_memories_basic():
    """Test basic keyword searching using search_memories."""
    store = MemoryStore(":memory:")
    
    store.add_memory("Python is a beautiful programming language.", "dev", "python")
    store.add_memory("Rust is a systems programming language.", "dev", "rust")
    store.add_memory("The weather is nice today.", "personal", "weather")
    
    # Search for 'programming'
    results = store.search_memories("programming")
    assert len(results) == 2
    # Verify both matched memories contain 'programming'
    assert any("Python" in r["content"] for r in results)
    assert any("Rust" in r["content"] for r in results)
    
    # Search for 'weather'
    results = store.search_memories("weather")
    assert len(results) == 1
    assert results[0]["room"] == "weather"
    assert "weather" in results[0]["content"]
    
    store.close()

def test_search_memories_filtering():
    """Test filtering of search results by wing and room."""
    store = MemoryStore(":memory:")
    
    store.add_memory("Git is a distributed version control system.", "dev", "git")
    store.add_memory("Subversion is a centralized version control system.", "dev", "svn")
    store.add_memory("Version control is important for writing code.", "education", "git")
    
    # Search for 'version control' with no filters
    results = store.search_memories("version control")
    assert len(results) == 3
    
    # Filter by wing='dev'
    results_dev = store.search_memories("version control", wing="dev")
    assert len(results_dev) == 2
    assert all(r["wing"] == "dev" for r in results_dev)
    
    # Filter by room='git'
    results_git = store.search_memories("version control", room="git")
    assert len(results_git) == 2
    assert all(r["room"] == "git" for r in results_git)
    
    # Filter by wing='dev' and room='git'
    results_both = store.search_memories("version control", wing="dev", room="git")
    assert len(results_both) == 1
    assert results_both[0]["wing"] == "dev"
    assert results_both[0]["room"] == "git"
    
    # Filter with non-existent wing/room
    results_empty = store.search_memories("version control", wing="nonexistent")
    assert len(results_empty) == 0
    
    store.close()

def test_search_memories_ranking():
    """Test BM25 relevance ranking produces expected ordering."""
    store = MemoryStore(":memory:")
    
    # Document 1: contains query terms multiple times, relatively short
    id1 = store.add_memory("Python python python programming is fun and Python is great.", "dev", "python")
    # Document 2: contains query term once, longer document
    id2 = store.add_memory("This is a long document containing various things, including some discussion on programming.", "dev", "misc")
    # Document 3: does not contain query term
    id3 = store.add_memory("Completely unrelated text about cooking delicious meals.", "hobby", "cooking")
    
    results = store.search_memories("Python programming")
    
    # Document 3 should not be returned at all
    assert len(results) == 2
    assert id3 not in [r["id"] for r in results]
    
    # Document 1 should be ranked higher than Document 2
    assert results[0]["id"] == id1
    assert results[1]["id"] == id2
    assert results[0]["relevance_score"] > results[1]["relevance_score"]
    
    store.close()

def test_search_memories_syntax_error_fallback():
    """Test that query syntax errors are handled gracefully and fall back to sanitized query."""
    store = MemoryStore(":memory:")
    
    store.add_memory("Python programming language", "dev", "python")
    
    # Query with unmatched double quote (FTS5 syntax error)
    results1 = store.search_memories('Python "')
    assert len(results1) == 1
    assert "Python" in results1[0]["content"]
    
    # Query with invalid FTS5 keyword sequence
    results2 = store.search_memories('Python AND')
    assert len(results2) == 1
    assert "Python" in results2[0]["content"]
    
    store.close()

def test_search_memories_empty_query():
    """Test that empty queries or whitespace-only queries return an empty list immediately."""
    store = MemoryStore(":memory:")
    
    store.add_memory("Some content", "wing", "room")
    
    assert store.search_memories("") == []
    assert store.search_memories("   ") == []
    assert store.search_memories(None) == []
    
    store.close()
