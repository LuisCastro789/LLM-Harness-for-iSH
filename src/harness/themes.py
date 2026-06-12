"""
Theme system for ish-harness TUI.

Provides ANSI escape-code styling that works in iSH's VT100-compatible terminal.
Themes: dark (default), light, monokai, solarized.
"""

from dataclasses import dataclass


@dataclass
class Theme:
    name: str
    # ANSI escape sequences
    reset:       str = "\033[0m"
    bold:        str = "\033[1m"
    dim:         str = "\033[2m"
    italic:      str = "\033[3m"
    underline:   str = "\033[4m"

    # Semantic colours (foreground)
    prompt:      str = ""   # user prompt arrow
    user_label:  str = ""   # "You" label
    ai_label:    str = ""   # "AI" or provider label
    tool_label:  str = ""   # tool call header
    tool_result: str = ""   # tool result text
    info:        str = ""   # status / info messages
    warn:        str = ""   # warnings
    error:       str = ""   # errors
    success:     str = ""   # success confirmations
    muted:       str = ""   # secondary text (tokens, timing)
    code:        str = ""   # inline code / command text
    border:      str = ""   # box-drawing borders
    highlight:   str = ""   # selected/highlighted items

    def apply(self, code: str, text: str) -> str:
        """Wrap text with an ANSI code and reset."""
        return f"{code}{text}{self.reset}"


# ── ANSI colour shorthands ───────────────────────────────────────────────────

def _fg(n: int) -> str:
    """Standard 16-colour foreground."""
    return f"\033[{n}m"

def _fg256(n: int) -> str:
    """256-colour foreground."""
    return f"\033[38;5;{n}m"

def _bg256(n: int) -> str:
    """256-colour background."""
    return f"\033[48;5;{n}m"

BOLD = "\033[1m"
DIM  = "\033[2m"
RST  = "\033[0m"


# ── built-in themes ──────────────────────────────────────────────────────────

DARK = Theme(
    name="dark",
    prompt      = _fg(32) + BOLD,       # bright green
    user_label  = _fg(36) + BOLD,       # cyan
    ai_label    = _fg(35) + BOLD,       # magenta
    tool_label  = _fg(33) + BOLD,       # yellow
    tool_result = _fg256(244),          # grey
    info        = _fg(34),              # blue
    warn        = _fg(33),              # yellow
    error       = _fg(31) + BOLD,       # red
    success     = _fg(32),              # green
    muted       = _fg256(240) + DIM,    # dark grey
    code        = _fg256(117),          # light blue
    border      = _fg256(238),          # subtle grey
    highlight   = _fg256(220) + BOLD,   # gold
)

LIGHT = Theme(
    name="light",
    prompt      = _fg(28) + BOLD,       # dark green
    user_label  = _fg(26) + BOLD,       # dark cyan
    ai_label    = _fg(91) + BOLD,       # dark magenta
    tool_label  = _fg(130) + BOLD,      # dark orange
    tool_result = _fg256(238),          # dark grey
    info        = _fg(26),
    warn        = _fg(130),
    error       = _fg(160) + BOLD,
    success     = _fg(28),
    muted       = _fg256(244) + DIM,
    code        = _fg256(24),
    border      = _fg256(249),
    highlight   = _fg256(202) + BOLD,
)

MONOKAI = Theme(
    name="monokai",
    prompt      = _fg256(82)  + BOLD,   # monokai green
    user_label  = _fg256(81)  + BOLD,   # monokai blue
    ai_label    = _fg256(198) + BOLD,   # monokai pink
    tool_label  = _fg256(208) + BOLD,   # monokai orange
    tool_result = _fg256(245),
    info        = _fg256(81),
    warn        = _fg256(208),
    error       = _fg256(197) + BOLD,
    success     = _fg256(82),
    muted       = _fg256(241) + DIM,
    code        = _fg256(186),           # monokai yellow
    border      = _fg256(236),
    highlight   = _fg256(227) + BOLD,
)

SOLARIZED = Theme(
    name="solarized",
    prompt      = _fg256(64)  + BOLD,   # solarized green
    user_label  = _fg256(33)  + BOLD,   # solarized blue
    ai_label    = _fg256(125) + BOLD,   # solarized magenta
    tool_label  = _fg256(136) + BOLD,   # solarized yellow
    tool_result = _fg256(240),
    info        = _fg256(33),
    warn        = _fg256(136),
    error       = _fg256(160) + BOLD,
    success     = _fg256(64),
    muted       = _fg256(239) + DIM,
    code        = _fg256(37),           # solarized cyan
    border      = _fg256(235),
    highlight   = _fg256(166) + BOLD,   # solarized orange
)

THEMES = {
    "dark":      DARK,
    "light":     LIGHT,
    "monokai":   MONOKAI,
    "solarized": SOLARIZED,
}


def get_theme(name: str) -> Theme:
    return THEMES.get(name, DARK)
