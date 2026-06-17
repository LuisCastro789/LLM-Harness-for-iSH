#!/usr/bin/env python3
"""
iSH-Memory Command Line Interface.
Provides CLI access to add, search, get, and delete memories.
"""

import os
import sys
import json
import argparse

# Dynamically resolve path to src directory to import harness.memory_store
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "../../../../"))
sys.path.insert(0, src_dir)

try:
    from harness.memory_store import MemoryStore
except ImportError as e:
    print(f"Error importing MemoryStore: {e}", file=sys.stderr)
    print(f"Resolved src_dir: {src_dir}", file=sys.stderr)
    print(f"sys.path: {sys.path}", file=sys.stderr)
    sys.exit(1)

def get_db_path(args):
    if args.db:
        return args.db
    env_db = os.environ.get("HARNESS_MEMORY_DB")
    if env_db:
        return env_db
    return os.path.expanduser("~/.harness/memory.db")

def cmd_add(args):
    db_path = get_db_path(args)
    metadata = None
    if args.metadata:
        try:
            metadata = json.loads(args.metadata)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON for metadata: {e}", file=sys.stderr)
            sys.exit(1)
            
    store = MemoryStore(db_path)
    try:
        mem_id = store.add_memory(
            content=args.content,
            wing=args.wing,
            room=args.room,
            metadata=metadata
        )
        print(f"Memory added successfully. ID: {mem_id}")
    finally:
        store.close()

def cmd_search(args):
    db_path = get_db_path(args)
    store = MemoryStore(db_path)
    try:
        results = store.search_memories(
            query=args.query,
            wing=args.wing,
            room=args.room
        )
        if not results:
            print("No matching memories found.")
            return
            
        for r in results:
            score = r.get("relevance_score", 0.0)
            print(f"ID: {r['id']} | Score: {score:.4f} | Wing: {r['wing']} | Room: {r['room']}")
            print(f"Content: {r['content']}")
            if r['metadata']:
                print(f"Metadata: {json.dumps(r['metadata'])}")
            print("-" * 40)
    finally:
        store.close()

def cmd_get(args):
    db_path = get_db_path(args)
    store = MemoryStore(db_path)
    try:
        memory = store.get_memory(args.id)
        if not memory:
            print(f"Error: Memory with ID {args.id} not found.", file=sys.stderr)
            sys.exit(1)
            
        print(f"ID: {memory['id']}")
        print(f"Wing: {memory['wing']}")
        print(f"Room: {memory['room']}")
        print(f"Created At: {memory['created_at']}")
        print(f"Content: {memory['content']}")
        print(f"Metadata: {json.dumps(memory['metadata']) if memory['metadata'] else 'None'}")
    finally:
        store.close()

def cmd_delete(args):
    db_path = get_db_path(args)
    store = MemoryStore(db_path)
    try:
        success = store.delete_memory(args.id)
        if success:
            print(f"Memory with ID {args.id} deleted successfully.")
        else:
            print(f"Error: Memory with ID {args.id} not found.", file=sys.stderr)
            sys.exit(1)
    finally:
        store.close()

def main():
    parser = argparse.ArgumentParser(description="iSH-Memory Command Line Interface")
    parser.add_argument("--db", help="Path to the SQLite database file (overrides default and env var)")
    
    subparsers = parser.add_subparsers(dest="command", required=True, help="Subcommands")
    
    # Add command
    parser_add = subparsers.add_parser("add", help="Add a new memory")
    parser_add.add_argument("content", help="The verbatim content of the memory")
    parser_add.add_argument("--wing", required=True, help="The wing category")
    parser_add.add_argument("--room", required=True, help="The room category")
    parser_add.add_argument("--metadata", help="Optional JSON string containing metadata")
    parser_add.set_defaults(func=cmd_add)
    
    # Search command
    parser_search = subparsers.add_parser("search", help="Search memories")
    parser_search.add_argument("query", help="The search query string")
    parser_search.add_argument("--wing", help="Optional wing to filter by")
    parser_search.add_argument("--room", help="Optional room to filter by")
    parser_search.set_defaults(func=cmd_search)
    
    # Get command
    parser_get = subparsers.add_parser("get", help="Retrieve a memory by ID")
    parser_get.add_argument("id", type=int, help="The unique integer ID of the memory")
    parser_get.set_defaults(func=cmd_get)
    
    # Delete command
    parser_delete = subparsers.add_parser("delete", help="Delete a memory by ID")
    parser_delete.add_argument("id", type=int, help="The unique integer ID of the memory")
    parser_delete.set_defaults(func=cmd_delete)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
