"""Rolling z-score anomaly detector. Pure Python, no I/O -> trivially unit-testable."""
from collections import defaultdict, deque
from statistics import fmean, pstdev


class RollingDetector:
    """Keeps the last window readings

    A new value is judged against the PREVIOUS window BEFORE to be added to it.
    we want to detect as anomaly when it trigger the more than 3 times std deviation rule
    """

    def __init__(self, window=10, threshold=3.0):
        if window < 3:
            raise ValueError("window must be >= 3")
        self.window = window
        self.threshold = threshold
        # we create a default dict (create key if not exist) of deque (that remove the oldest
        # value when maxlen is reached)
        self._history = defaultdict(lambda: deque(maxlen=window))

    def check(self, machine, sensor, value):
        """Return {"value","mean","std","z"} if `value` is anomalous else None"""
        history = self._history[(machine, sensor)]
        anomaly = None
        if len(history) == self.window:
            mean = fmean(history)  # mean of the window numer of last readings
            std = pstdev(history, mean)  # standard deviation how far the readings are from the mean
            if std > 0:
                z = abs(value - mean) / std  # zscore : the readings are far of how many std from mean ?
                if z > self.threshold:  # if is outlier we consider it an anomaly
                    anomaly = {"value": value, "mean": mean, "std": std, "z": z}
        history.append(value)
        return anomaly
