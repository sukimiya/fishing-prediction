"""Astronomical factors: moon phase, solunar periods."""

import math

from module3_prediction_model.factors.base import BaseFactor


class MoonPhaseFactor(BaseFactor):
    """Score based on moon phase.

    Based on solunar theory: new moon and full moon = best activity.
    First/third quarter = worst.
    """

    name = "moon_phase"
    category = "astronomical"

    def score(self, moon_phase: float = 0.5, **kwargs) -> float:
        """Score based on moon phase.

        Args:
            moon_phase: Moon phase in [0, 1] where 0 = new moon, 0.5 = full moon.

        Returns:
            Score in [0, 1].
        """
        # Distance from nearest new or full moon
        distance = min(moon_phase, 1 - moon_phase, abs(moon_phase - 0.5))
        # Convert: 0 distance = best (score 1.0), 0.25 = worst (score 0.3)
        score = 1.0 - (distance / 0.25) * 0.7
        return max(0.3, min(1.0, score))


class SolunarFactor(BaseFactor):
    """Score based on major/minor solunar periods.

    During major periods (moon overhead/underfoot) fish feed more actively.
    """

    name = "solunar"
    category = "astronomical"

    def score(self, minutes_since_major: float = 999, **kwargs) -> float:
        """Score based on proximity to major solunar period.

        Args:
            minutes_since_major: Minutes since last major period start.
                                 999 means no major period data available.

        Returns:
            Score in [0, 1].
        """
        if minutes_since_major == 999:
            return 0.5  # neutral if no data

        # Major period lasts about 2 hours (120 minutes)
        if minutes_since_major <= 120:
            return 1.0
        if minutes_since_major <= 180:
            return 0.7
        return 0.3
