# let's evaluate the detector and see how many false positive and negatives it trigger

import argparse
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parent  # we find the parent folder of this file
# we add our simulator and our subscriber to paths
sys.path[:0] = [str(ROOT / "simulator"), str(ROOT / "ingestion")]

from ingestion.anomaly import RollingDetector
from simulator.sensor_sim import MACHINES, generate_reading


def evaluate(window, threshold, ticks, seed):
    rng = random.Random(seed)
    detector = RollingDetector(window, threshold)
    tp = fp = fn = tn = 0

    # start evaluation
    for i in range(ticks):
        for m in MACHINES:
            msg = generate_reading(m, rng=rng)
            # for each sensor of each machine
            for sensor, value in msg["sensors"].items():
                # check if the value of that sensor is anomalous
                flagged = detector.check(m, sensor, value) is not None
                # it's true if the sensor we declared injected is the same we detected anomalous
                truth = msg["injected_sensor"] == sensor

                # it is true positive if we injected and it was detected
                tp += flagged and truth
                # it is false positive if it detected anomalous but we didn't inject anything
                fp += flagged and not truth
                # it is false negative if we injected but it didn't detect it
                fn += (not flagged) and truth
                # it is true negative if we didn't inject and it didn't detect also
                tn += (not flagged) and (not truth)

    # now we can calculate precision and recall and f1 score
    # precision = tp / (tp + fp) within all the positive detected how many was really positive
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    # recall = tp / (tp + fn) within all the positive in the data how much our model detected
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    #f1 score is harmonic mean : 2 * (precision * recall) / (precision + recall)
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) else 0.0

    # we calculate false alarm rate
    hours = ticks * 2 / 3600  # one reading last arond 2 seconds
    fa = fp / (hours * len(MACHINES))  # number of false alarm per machine per hour

    return precision, recall, f1, fa

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticks", type=int, default=20000, help="represent rounds per config (1 round = 5 machines)")
    ap.add_argument("--seed", type=int, default=42, help="default seed is 42")

    a = ap.parse_args()

    # now we evaluate our model with 4 windows : 10 20 30 and 60 last sensor readings to decide if anomalous
    # we also use 4 different treshold : if the last reading is 2.5 3 3.5 or 4 times the standard deviation it is 
    # considered anomalous like outlier 
    print("| window | threshold | precision | recall |     F1 | false alarms / machine / hour |")
    print("|-------:|----------:|----------:|-------:|-------:|------------------------------:|")

    for window in (10, 20, 30, 60):
        for threshold in (2.5, 3, 3.5, 4):
            prec, rec, f1, fa = evaluate(window, threshold, a.ticks, a.seed)
            # >6 , >9 and >29 means pad to 6 9 29 to have a good looking formatting in cmd
            print(f"| {window:>6} | {threshold:>9} | {prec:>9.3f} | {rec:>6.3f} | {f1:>6.3f} | {fa:>29.1f} |")
