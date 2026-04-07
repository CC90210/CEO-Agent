"""
ReplSkin — Unified REPL Interface for CLI-Anything tools.
Adapted from HKUDS/CLI-Anything for Business-Empire-Agent.

Usage:
    from cli_templates.repl_skin import ReplSkin
    skin = ReplSkin(app_name="my-tool", prompt_symbol=">")
    skin.success("Operation completed")
    skin.error("Something went wrong")
    skin.table(headers=["Name", "Value"], rows=[["key", "val"]])
"""

import os
import sys

# Respect NO_COLOR environment variable (https://no-color.org/)
_NO_COLOR = os.environ.get("NO_COLOR") is not None or not sys.stdout.isatty()


class ReplSkin:
    """Consistent terminal interface for all CLI-Anything tools."""

    # ANSI color codes
    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "red": "\033[31m",
        "blue": "\033[34m",
        "cyan": "\033[36m",
        "magenta": "\033[35m",
    }

    def __init__(self, app_name: str = "cli-anything", prompt_symbol: str = ">"):
        self.app_name = app_name
        self.prompt_symbol = prompt_symbol

    def _color(self, text: str, color: str) -> str:
        if _NO_COLOR:
            return text
        c = self.COLORS.get(color, "")
        reset = self.COLORS["reset"]
        return f"{c}{text}{reset}"

    def _bold(self, text: str) -> str:
        if _NO_COLOR:
            return text
        return f"{self.COLORS['bold']}{text}{self.COLORS['reset']}"

    def success(self, message: str) -> None:
        prefix = self._color("✓", "green")
        print(f"  {prefix} {message}")

    def error(self, message: str) -> None:
        prefix = self._color("✗", "red")
        print(f"  {prefix} {message}", file=sys.stderr)

    def warning(self, message: str) -> None:
        prefix = self._color("⚠", "yellow")
        print(f"  {prefix} {message}")

    def info(self, message: str) -> None:
        prefix = self._color("ℹ", "blue")
        print(f"  {prefix} {message}")

    def header(self, title: str) -> None:
        line = "─" * (len(title) + 4)
        print(f"\n  {self._bold(title)}")
        print(f"  {self._color(line, 'dim')}")

    def prompt(self) -> str:
        """Display prompt and return user input."""
        try:
            from prompt_toolkit import prompt as pt_prompt
            return pt_prompt(f"{self.app_name} {self.prompt_symbol} ")
        except ImportError:
            return input(f"{self.app_name} {self.prompt_symbol} ")

    def table(self, headers: list[str], rows: list[list[str]], max_width: int = 80) -> None:
        """Display a formatted table with box-drawing characters."""
        if not rows:
            self.info("No data to display.")
            return

        # Calculate column widths
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                if i < len(col_widths):
                    col_widths[i] = max(col_widths[i], len(str(cell)))

        # Clamp to max_width
        total = sum(col_widths) + (len(col_widths) * 3) + 1
        if total > max_width:
            scale = (max_width - len(col_widths) * 3 - 1) / sum(col_widths)
            col_widths = [max(3, int(w * scale)) for w in col_widths]

        def format_row(cells, sep="│"):
            parts = []
            for i, cell in enumerate(cells):
                w = col_widths[i] if i < len(col_widths) else 10
                parts.append(f" {str(cell)[:w]:<{w}} ")
            return f"  {sep}" + f"{sep}".join(parts) + f"{sep}"

        def separator(left, mid, right, fill="─"):
            parts = [fill * (w + 2) for w in col_widths]
            return f"  {left}" + f"{mid}".join(parts) + f"{right}"

        # Print table
        print(separator("┌", "┬", "┐"))
        print(format_row([self._bold(h) for h in headers]))
        print(separator("├", "┼", "┤"))
        for row in rows:
            # Pad row if needed
            padded = list(row) + [""] * (len(headers) - len(row))
            print(format_row(padded))
        print(separator("└", "┴", "┘"))

    def divider(self) -> None:
        print(f"  {self._color('─' * 40, 'dim')}")

    def banner(self, text: str, version: str = "") -> None:
        """Display app banner on startup."""
        ver = f" v{version}" if version else ""
        print(f"\n  {self._bold(self._color(text, 'cyan'))}{self._color(ver, 'dim')}")
        self.divider()
