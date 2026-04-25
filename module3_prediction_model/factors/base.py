"""Abstract base class for all prediction factors.

Each factor maps raw environmental data → score in [0, 1],
where 1 = most favorable for fishing.
"""

from abc import ABC, abstractmethod


class BaseFactor(ABC):
    """A single scoring factor in the fish activity prediction model.

    Usage:
        factor = SomeFactor(weight=0.2)
        score = factor.score(temperature=25, pressure=1015)
    """

    def __init__(self, weight: float = 1.0):
        self.weight = weight

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier, e.g. 'temperature'."""

    @property
    @abstractmethod
    def category(self) -> str:
        """Factor category: 'weather' | 'temporal' | 'astronomical' | 'hydrological'."""

    @abstractmethod
    def score(self, **kwargs) -> float:
        """Compute factor contribution in [0, 1].

        Args:
            **kwargs: Factor-specific parameters (temperature, pressure, etc.)

        Returns:
            Float in [0, 1] where 1 = most favorable.
        """

    def describe(self, **kwargs) -> str:
        """Human-readable explanation of the score for this factor."""
        val = self.score(**kwargs)
        return f"{self.name}: {val:.2f}"

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.name} (w={self.weight})>"
