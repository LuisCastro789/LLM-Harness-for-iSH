"""
SQLite-based storage engine for the iSH-Memory system.
Provides isolated storage, FTS5-based search indexing, and automatic synchronization triggers.
"""

import os
import sqlite3
import json
import re
import math
from typing import Optional, Dict, Any

class MemoryStore:
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the MemoryStore.
        
        Args:
            db_path: Path to the SQLite database file. Defaults to isolated development path.
        """
        if db_path is None:
            db_path = "/root/development/.harness_dev/memory.db"
        
        self.db_path = db_path
        
        # If not an in-memory database, ensure target directory exists
        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        
        self._init_db()
        
    def _init_db(self):
        """Initialize the schema and FTS5 triggers."""
        with self.conn:
            # Create the memories table
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    wing TEXT NOT NULL,
                    room TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Create the FTS5 virtual table
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS fts_memories USING fts5(
                    content,
                    content='memories',
                    content_rowid='id'
                );
            """)
            
            # Create triggers for automatic FTS synchronization
            self.conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                    INSERT INTO fts_memories(rowid, content) VALUES (new.id, new.content);
                END;
            """)
            
            self.conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                    INSERT INTO fts_memories(fts_memories, rowid, content) VALUES('delete', old.id, old.content);
                END;
            """)
            
            self.conn.execute("""
                CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                    INSERT INTO fts_memories(fts_memories, rowid, content) VALUES('delete', old.id, old.content);
                    INSERT INTO fts_memories(rowid, content) VALUES(new.id, new.content);
                END;
            """)

    def add_memory(self, content: str, wing: str, room: str, metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Insert a new memory and return its row ID.
        
        Args:
            content: Verbatim text content of the memory.
            wing: The high-level scope/wing (e.g., 'project', 'user').
            room: The specific topic/room (e.g., 'git', 'python').
            metadata: Optional dictionary of key-value metadata.
            
        Returns:
            The row ID of the inserted memory.
        """
        metadata_str = json.dumps(metadata) if metadata is not None else None
        with self.conn:
            cursor = self.conn.execute(
                "INSERT INTO memories (content, wing, room, metadata) VALUES (?, ?, ?, ?)",
                (content, wing, room, metadata_str)
            )
            return cursor.lastrowid

    def get_memory(self, row_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a memory by its ID.
        
        Args:
            row_id: The ID of the memory to retrieve.
            
        Returns:
            A dictionary containing the memory's fields, or None if not found.
        """
        cursor = self.conn.execute(
            "SELECT id, wing, room, content, metadata, created_at FROM memories WHERE id = ?",
            (row_id,)
        )
        row = cursor.fetchone()
        if row is None:
            return None
            
        metadata_dict = None
        if row["metadata"] is not None:
            try:
                metadata_dict = json.loads(row["metadata"])
            except json.JSONDecodeError:
                metadata_dict = {}
                
        return {
            "id": row["id"],
            "wing": row["wing"],
            "room": row["room"],
            "content": row["content"],
            "metadata": metadata_dict,
            "created_at": row["created_at"]
        }

    def delete_memory(self, row_id: int) -> bool:
        """
        Delete a memory by its ID.
        
        Args:
            row_id: The ID of the memory to delete.
            
        Returns:
            True if the memory was successfully deleted, False otherwise.
        """
        with self.conn:
            cursor = self.conn.execute(
                "DELETE FROM memories WHERE id = ?",
                (row_id,)
            )
            return cursor.rowcount > 0

    def _sanitize_fts_query(self, query: str) -> str:
        """Sanitize query for FTS5 by tokenizing and joining with OR, wrapping each word in double quotes."""
        words = re.findall(r'\w+', query)
        if not words:
            return ""
        # Wrap each word in double quotes and join with OR
        return " OR ".join(f'"{word}"' for word in words)

    def rank_memories(self, memories: list[dict], query: str) -> list[dict]:
        """
        Rank retrieved memories using a pure-Python BM25 algorithm.
        
        Args:
            memories: List of memory dictionaries to rank.
            query: The search query.
            
        Returns:
            The list of memories sorted by relevance score descending.
        """
        if not memories or not query:
            return memories
            
        def tokenize(text: str) -> list[str]:
            return re.findall(r'\w+', text.lower())
            
        query_terms = tokenize(query)
        if not query_terms:
            return memories
            
        # BM25 parameters
        k1 = 1.5
        b = 0.75
        
        # Calculate term frequencies and document lengths
        doc_terms_list = []
        doc_lengths = []
        for m in memories:
            terms = tokenize(m["content"])
            doc_terms_list.append(terms)
            doc_lengths.append(len(terms))
            
        N = len(memories)
        avgdl = sum(doc_lengths) / N if N > 0 else 1.0
        if avgdl == 0:
            avgdl = 1.0
            
        # Calculate Document Frequency (DF) for each query term in the retrieved set
        df = {}
        for term in query_terms:
            count = 0
            for terms in doc_terms_list:
                if term in terms:
                    count += 1
            df[term] = count
            
        # Calculate IDF for each query term
        idf = {}
        for term in query_terms:
            doc_freq = df[term]
            val = (N - doc_freq + 0.5) / (doc_freq + 0.5)
            idf[term] = math.log(max(0.0, val) + 1.0)
            
        # Score each memory
        scored_memories = []
        for i, m in enumerate(memories):
            terms = doc_terms_list[i]
            doc_len = doc_lengths[i]
            score = 0.0
            
            term_counts = {}
            for term in terms:
                term_counts[term] = term_counts.get(term, 0) + 1
                
            for term in query_terms:
                tf = term_counts.get(term, 0)
                if tf > 0:
                    numerator = tf * (k1 + 1)
                    denominator = tf + k1 * (1.0 - b + b * (doc_len / avgdl))
                    score += idf[term] * (numerator / denominator)
                    
            m_copy = m.copy()
            m_copy["relevance_score"] = score
            scored_memories.append(m_copy)
            
        # Sort by score descending, then by id descending to break ties consistently
        scored_memories.sort(key=lambda x: (x["relevance_score"], x["id"]), reverse=True)
        return scored_memories

    def search_memories(self, query: str, wing: Optional[str] = None, room: Optional[str] = None) -> list[dict]:
        """
        Search memories using SQLite FTS5 and rank them with pure-Python BM25.
        
        Args:
            query: The search query string.
            wing: Optional wing to filter by.
            room: Optional room to filter by.
            
        Returns:
            A list of matching memory dictionaries sorted by relevance.
        """
        if not query or not query.strip():
            return []
            
        # Build a safe FTS5 query by tokenizing and joining with OR, wrapping in double quotes
        fts_query = self._sanitize_fts_query(query)
        if not fts_query:
            return []
            
        sql = """
            SELECT m.id, m.wing, m.room, m.content, m.metadata, m.created_at
            FROM memories m
            JOIN fts_memories f ON m.id = f.rowid
            WHERE f.fts_memories MATCH ?
        """
        params = [fts_query]
        
        if wing is not None:
            sql += " AND m.wing = ?"
            params.append(wing)
            
        if room is not None:
            sql += " AND m.room = ?"
            params.append(room)
            
        try:
            cursor = self.conn.execute(sql, params)
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            # Fallback to a very simple single-word match if something still fails
            words = re.findall(r'\w+', query)
            if not words:
                return []
            # Try matching just the first word
            params[0] = f'"{words[0]}"'
            try:
                cursor = self.conn.execute(sql, params)
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                return []
            
        memories = []
        for row in rows:
            metadata_dict = None
            if row["metadata"] is not None:
                try:
                    metadata_dict = json.loads(row["metadata"])
                except json.JSONDecodeError:
                    metadata_dict = {}
                    
            memories.append({
                "id": row["id"],
                "wing": row["wing"],
                "room": row["room"],
                "content": row["content"],
                "metadata": metadata_dict,
                "created_at": row["created_at"]
            })
            
        # Rank the retrieved memories using BM25
        ranked = self.rank_memories(memories, query)
        return ranked

    def close(self):
        """Close the database connection."""
        self.conn.close()
