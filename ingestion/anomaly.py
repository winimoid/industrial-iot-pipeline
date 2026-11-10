"""Rolling z-score anomaly detector. Pure Python, no I/O -> trivially unit-testable."""
from collections import defaultdict, deque
from statistics import fmean, pstdev


class RollingDetector:
    """Keeps the last `window` readings per (machine, sensor).

    A new value is judged against the PREVIOUS window and only then added to it.
    (If the value is added first, the largest reachable z-score is sqrt(window-1):
    exactly 3.0 for window=10, so a "> 3 sigma" rule could never fire.)
    """

    def __init__(self, window=10, threshold=3.0):
        if window < 3:
            raise ValueError("window must be >= 3")
        self.window = window
        self.threshold = threshold
        self._history = defaultdict(lambda: deque(maxlen=window))

    def check(self, machine, sensor, value):
        """Return {"value","mean","std","z"} if `value` is anomalous, else None."""
        history = self._history[(machine, sensor)]
        anomaly = None
        if len(history) == self.window:
            mean = fmean(history)
            std = pstdev(history, mean)
            if std > 0:
                z = abs(value - mean) / std
                if z > self.threshold:
                    anomaly = {"value": value, "mean": mean, "std": std, "z": z}
        history.append(value)
        return anomaly
