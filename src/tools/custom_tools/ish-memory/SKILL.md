---
name: ish-memory
description: "Local-first verbatim memory system utilizing SQLite and FTS5 for fast, relevance-ranked keyword search. Use this skill when the user asks to store or search memories."
license: Apache-2.0
metadata:
  version: "1.0"
  author: ish-harness-agent
---

# iSH-Memory Skill

iSH-Memory is an ultra-lightweight, local-first verbatim memory system designed specifically for resource-constrained environments like Alpine Linux inside the iOS iSH app. It uses SQLite FTS5 for fast keyword search and a pure-Python BM25 algorithm for relevance-ranked retrieval.

## Memory Hierarchy

Memories are organized hierarchically to allow precise targeting and context-efficient retrieval:
- **Wing**: The high-level context or scope (e.g., `user`, `project`, `system`).
- **Room**: A specific topic, task, or area of interest (e.g., `git`, `python`, `deployment`).
- **Content**: The verbatim text snippet, conversation segment, or structured facts to remember.

## Command Line Interface (CLI)

The `memory_cli.py` script provides a command-line interface to interact with the memory system.

### Database File Location
By default, the CLI uses the production database path `~/.harness/memory.db`. You can override this behavior in two ways:
1. Setting the `HARNESS_MEMORY_DB` environment variable.
2. Passing the `--db` option to any command.

### Usage and Commands

#### 1. Add a Memory
Add a new memory to the store.
```bash
python3 scripts/memory_cli.py add "SQLite triggers automatically sync FTS5 virtual tables." --wing development --room sqlite --metadata '{"author": "assistant", "phase": 3}'
```
- **Arguments**:
  - `content` (positional, required): The verbatim content to store.
  - `--wing` (required): The wing category.
  - `--room` (required): The room category.
  - `--metadata` (optional): A valid JSON string containing key-value metadata.

#### 2. Search Memories
Search for memories using SQLite FTS5 and pure-Python BM25 relevance ranking.
```bash
python3 scripts/memory_cli.py search "FTS5 triggers" --wing development --room sqlite
```
- **Arguments**:
  - `query` (positional, required): The search query string.
  - `--wing` (optional): Filter results by a specific wing.
  - `--room` (optional): Filter results by a specific room.

#### 3. Get a Memory
Retrieve and display a memory by its unique row ID in a clean format.
```bash
python3 scripts/memory_cli.py get 1
```
- **Arguments**:
  - `id` (positional, required): The unique integer ID of the memory.

#### 4. Delete a Memory
Delete a memory from the database by its unique row ID.
```bash
python3 scripts/memory_cli.py delete 1
```
- **Arguments**:
  - `id` (positional, required): The unique integer ID of the memory to delete.
