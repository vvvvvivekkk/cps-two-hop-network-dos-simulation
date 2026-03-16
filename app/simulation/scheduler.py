from collections import deque
from typing import Dict, List, Optional

import numpy as np


class TransmissionScheduler:
    def __init__(self, sensors: int):
        self.sensors = sensors
        self.delivery_history = [deque(maxlen=30) for _ in range(sensors)]

    def record_delivery(self, sensor_id: int, delivered: bool) -> None:
        self.delivery_history[sensor_id].append(1 if delivered else 0)

    def adaptive_weights(self) -> List[float]:
        weights: List[float] = []
        for history in self.delivery_history:
            if not history:
                weights.append(1.0)
                continue
            success_rate = sum(history) / len(history)
            weights.append(1.0 + (1.0 - success_rate))
        return weights

    def select_sensor(
        self,
        estimation_errors: List[float],
        priorities: List[float],
        bandwidth_available: int,
        attack_status: Dict,
    ) -> Optional[int]:
        if bandwidth_available <= 0:
            return None

        attack_penalty = 1.0
        if attack_status.get("active", False):
            attack_penalty = 0.85

        adaptive = self.adaptive_weights()
        scores = np.array(estimation_errors) * np.array(priorities) * np.array(adaptive) * attack_penalty
        selected = int(np.argmax(scores))
        return selected
