"""
Breakpoint management for interactive debugging.
"""

from typing import Set


class BreakpointManager:
    """Manages breakpoints at key strategy execution points."""

    VALID_LOCATIONS = {"generate", "execute", "feedback"}

    def __init__(self):
        """Initialize breakpoint manager with no breakpoints enabled."""
        self._enabled_breakpoints: Set[str] = set()

    def enable(self, location: str) -> bool:
        """
        Enable a breakpoint at the specified location.

        Args:
            location: Breakpoint location (generate, execute, or feedback)

        Returns:
            True if breakpoint was enabled, False if location invalid
        """
        if location not in self.VALID_LOCATIONS:
            return False
        self._enabled_breakpoints.add(location)
        return True

    def disable(self, location: str) -> bool:
        """
        Disable a breakpoint at the specified location.

        Args:
            location: Breakpoint location (generate, execute, or feedback)

        Returns:
            True if breakpoint was disabled, False if location invalid
        """
        if location not in self.VALID_LOCATIONS:
            return False
        self._enabled_breakpoints.discard(location)
        return True

    def should_break(self, location: str) -> bool:
        """
        Check if execution should pause at the specified location.

        Args:
            location: Current execution location

        Returns:
            True if breakpoint is enabled at this location
        """
        return location in self._enabled_breakpoints

    def is_enabled(self, location: str) -> bool:
        """
        Check if a breakpoint is enabled at the specified location.

        Args:
            location: Breakpoint location to check

        Returns:
            True if breakpoint is enabled
        """
        return location in self._enabled_breakpoints

    def get_enabled(self) -> Set[str]:
        """
        Get set of all enabled breakpoint locations.

        Returns:
            Set of enabled breakpoint location names
        """
        return self._enabled_breakpoints.copy()

    def clear_all(self) -> None:
        """Disable all breakpoints."""
        self._enabled_breakpoints.clear()
