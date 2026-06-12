"""
ish-harness: TUI-based agentic LLM harness for iSH on iOS.
Entry point.
"""

import sys
from harness.app import HarnessApp


def main():
    app = HarnessApp()
    app.run()


if __name__ == "__main__":
    main()
