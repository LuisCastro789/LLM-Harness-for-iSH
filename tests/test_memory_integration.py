"""
Integration tests for the iSH-Memory system and Harness Core.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add the src/ directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import harness.tools
from harness.tools import refresh_skills, build_skills_catalog, dispatch_tool
from harness.agent import AgentLoop, AgentSession
from harness.config import AgentConfig, ProviderConfig
from harness.providers import BaseProvider, LLMResponse
from harness.memory_store import MemoryStore


class MockProvider(BaseProvider):
    def __init__(self, cfg=None):
        if cfg is None:
            cfg = ProviderConfig()
        super().__init__(cfg)
        self.last_system_prompt = None

    def chat(self, messages, system=None, tools=None, stream_cb=None) -> LLMResponse:
        self.last_system_prompt = system
        return LLMResponse(content="Mock response", tool_calls=[])


def test_ish_memory_skill_discovery():
    """Verify that the ish-memory skill is successfully discovered and listed in the skills catalog."""
    refresh_skills()
    assert "ish-memory" in harness.tools.SKILLS_REGISTRY
    
    catalog = build_skills_catalog()
    assert "ish-memory" in catalog
    assert "Local-first verbatim memory system" in catalog


def test_activate_skill_ish_memory():
    """Verify that the activate_skill tool successfully activates and returns the content of SKILL.md for ish-memory."""
    refresh_skills()
    result = dispatch_tool("activate_skill", {"name": "ish-memory"})
    assert '<skill_content name="ish-memory">' in result
    assert "iSH-Memory Skill" in result
    assert "Memory Hierarchy" in result


def test_automatic_memory_recall_injection():
    """Verify that the automatic memory recall mechanism successfully queries the database and injects it into the prompt."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_recall.db")
        
        # Populate the database with test memories
        store = MemoryStore(db_path)
        try:
            store.add_memory("SQLite is a software library that provides a relational database management system.", "dev", "sqlite")
            store.add_memory("The Python language is extremely dynamic and expressive.", "dev", "python")
        finally:
            store.close()
            
        # Set environment variable to override the default path
        old_env = os.environ.get("HARNESS_MEMORY_DB")
        os.environ["HARNESS_MEMORY_DB"] = db_path
        
        try:
            # Set up the agent session and loop
            provider = MockProvider()
            cfg = AgentConfig()
            session = AgentSession(provider, cfg)
            loop = AgentLoop(session)
            
            # Run the loop with a query that matches the SQLite memory
            loop.run("Tell me about SQLite library")
            
            # Verify that the memory was recalled and injected into the dynamic system prompt
            prompt = provider.last_system_prompt
            assert prompt is not None
            assert "### Relevant Memories:" in prompt
            assert "- [dev/sqlite]: SQLite is a software library that provides a relational database management system." in prompt
            # Python memory shouldn't rank high enough or match the query as well
            assert "dev/python" not in prompt
            
        finally:
            # Restore environment variable
            if old_env is not None:
                os.environ["HARNESS_MEMORY_DB"] = old_env
            else:
                os.environ.pop("HARNESS_MEMORY_DB", None)
