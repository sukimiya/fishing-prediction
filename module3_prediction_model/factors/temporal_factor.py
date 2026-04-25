"""Time-related factors: time of day, season."""

from datetime import datetime

from module3_prediction_model.factors.base import BaseFactor


class TimeOfDayFactor(BaseFactor):
    """Score based on time of day.

    Dawn and dusk are prime feeding periods.
    """

    name = "time_of_day"
    category = "temporal"

    def __init__(self, weight: float = 0.15, dawn_hour: int = 6, dusk_hour: int = 18):
        super().__init__(weight)
        self.dawn_hour = dawn_hour
        self.dusk_hour = dusk_hour

    def score(self, hour: int = 12, sunrise: int = 6, sunset: int = 18, **kwargs) -> float:
        """Score based on hour of day.

        Args:
            hour: Current hour (0-23).
            sunrise: Sunrise hour (0-23).
            sunset: Sunset hour (0-23).

        Returns:
            Score in [0, 1].
        """
        # Dawn peak: sunrise ± 1 hour
        if sunrise - 1 <= hour <= sunrise + 1:
            return 1.0
        # Dusk peak: sunset - 1 to sunset + 1
        if sunset - 1 <= hour <= sunset + 1:
            return 1.0
        # Morning (after dawn prime): good but declining
        if sunrise + 1 < hour <= 11:
            return 0.7
        # Afternoon (before dusk prime): moderate
        if 12 <= hour <= sunset - 2:
            return 0.5
        # Night: low
        return 0.3


class SeasonFactor(BaseFactor):
    """Score based on season.

    Spring and autumn are best (spawning/pre-winter feeding).
    Summer midday is worst. Winter is poor for most species.
    """

    name = "season"
    category = "temporal"

    # Northern hemisphere monthly scores
    _MONTH_SCORES = {
        1: 0.2,  # Jan - deep winter
        2: 0.3,  # Feb
        3: 0.6,  # Mar - spring begins
        4: 0.8,  # Apr - prime spring
        5: 0.9,  # May - pre-spawn feeding
        6: 0.7,  # Jun - post-spawn
        7: 0.5,  # Jul - summer heat
        8: 0.6,  # Aug
        9: 0.8,  # Sep - autumn feeding
        10: 0.9, # Oct - prime autumn
        11: 0.6, # Nov
        12: 0.3, # Dec
    }

    def __init__(self, weight: float = 0.10):
        super().__init__(weight)

    def score(self, month: int = 6, **kwargs) -> float:
        return self._MONTH_SCORES.get(month, 0.5)
