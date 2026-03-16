import threading
import time
import uuid
from typing import Dict, List

import numpy as np
from scipy import stats

from app.core.database import DatabaseManager
from app.models.schemas import AttackProfile, StartSimulationRequest
from app.simulation.kalman import ScalarKalmanFilter
from app.simulation.network import DoSAttackModule, Packet, TwoHopCommunicationManager
from app.simulation.scheduler import TransmissionScheduler


DEFAULT_ATTACKS = [
    {
        "attack_type": "packet_drop",
        "attack_probability": 0.12,
        "attack_duration": 8,
        "target_link": "Hop1",
    },
    {
        "attack_type": "delay",
        "attack_probability": 0.10,
        "attack_duration": 10,
        "target_link": "Hop2",
    },
    {
        "attack_type": "bandwidth_flood",
        "attack_probability": 0.08,
        "attack_duration": 7,
        "target_link": "Hop2",
    },
]


class SimulationEngine:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self._thread = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self.running = False
        self.step = 0
        self.last_payload = {
            "network": {},
            "attacks": {},
            "estimation": [],
        }

    def start(self, config: StartSimulationRequest) -> Dict:
        with self._lock:
            if self.running:
                return {"status": "running", "message": "Simulation already running"}

            self.config = config
            self.sensors = config.sensors
            self.step_interval_sec = config.step_interval_sec

            self.a = 1.0
            self.h = 1.0
            self.q = 0.05
            self.r = 0.20

            self.true_states = np.zeros(self.sensors)
            self.measurements = np.zeros(self.sensors)
            self.priorities = np.linspace(1.0, 1.6, self.sensors)

            self.filters = [
                ScalarKalmanFilter(self.a, self.h, self.q, self.r, x0=0.0, p0=1.0)
                for _ in range(self.sensors)
            ]

            profiles = config.attack_profiles or [AttackProfile(**p) for p in DEFAULT_ATTACKS]
            self.attack_module = DoSAttackModule([p.model_dump() for p in profiles])
            self.scheduler = TransmissionScheduler(self.sensors)
            self.network = TwoHopCommunicationManager(
                relay_capacity=config.relay_buffer_size,
                base_bandwidth_packets=config.base_bandwidth_packets,
            )

            self.step = 0
            self._stop_event.clear()
            self.running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

            return {"status": "ok", "message": "Simulation started"}

    def stop(self) -> Dict:
        with self._lock:
            if not self.running:
                return {"status": "stopped", "message": "Simulation is not running"}
            self._stop_event.set()
            self.running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        return {"status": "ok", "message": "Simulation stopped"}

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.step += 1

            transitions = self.attack_module.update()
            for attack_type, target_link, active in transitions:
                note = "activated" if active else "deactivated"
                self.db.log_attack(self.step, attack_type, target_link, active, note)

            process_noise = np.random.normal(0.0, np.sqrt(self.q), self.sensors)
            measurement_noise = np.random.normal(0.0, np.sqrt(self.r), self.sensors)

            self.true_states = self.a * self.true_states + process_noise
            self.measurements = self.h * self.true_states + measurement_noise

            for i in range(self.sensors):
                self.filters[i].predict()
                self.db.log_sensor_data(
                    self.step,
                    i,
                    float(self.true_states[i]),
                    float(self.measurements[i]),
                )

            est_errors = [abs(float(self.true_states[i]) - self.filters[i].x) for i in range(self.sensors)]
            if len(est_errors) > 1:
                z_scores = stats.zscore(est_errors)
                anomaly_index = float(np.max(np.abs(z_scores)))
            else:
                anomaly_index = 0.0

            hop1_bandwidth = self.network.available_bandwidth(self.attack_module, "Hop1")
            attack_status = self.attack_module.current_status()
            selected = self.scheduler.select_sensor(
                estimation_errors=est_errors,
                priorities=self.priorities.tolist(),
                bandwidth_available=hop1_bandwidth,
                attack_status=attack_status,
            )

            if selected is not None:
                packet = Packet(
                    packet_id=str(uuid.uuid4()),
                    sensor_id=selected,
                    step_created=self.step,
                    measurement=float(self.measurements[selected]),
                )
                sensor_event = self.network.send_sensor_packet(packet, self.attack_module, self.step)
                self.db.log_packet(
                    self.step,
                    selected,
                    packet.packet_id,
                    sensor_event["event"],
                    sensor_event["link"],
                    sensor_event["delay_steps"],
                    sensor_event["dropped"],
                )
                self.scheduler.record_delivery(selected, not sensor_event["dropped"])

            delivered = self.network.relay_to_estimator(self.attack_module, self.step)
            for packet in delivered:
                self.filters[packet.sensor_id].update(packet.measurement)
                total_delay = self.step - packet.step_created
                self.db.log_packet(
                    self.step,
                    packet.sensor_id,
                    packet.packet_id,
                    "delivered",
                    "Hop2",
                    total_delay,
                    False,
                )
                self.scheduler.record_delivery(packet.sensor_id, True)

            estimation_rows: List[Dict] = []
            for i in range(self.sensors):
                error = abs(float(self.true_states[i]) - self.filters[i].x)
                row = {
                    "step": self.step,
                    "sensor_id": i,
                    "true_state": float(self.true_states[i]),
                    "estimated_state": float(self.filters[i].x),
                    "estimation_error": float(error),
                    "covariance": float(self.filters[i].p),
                }
                estimation_rows.append(row)
                self.db.log_estimation(
                    self.step,
                    i,
                    row["true_state"],
                    row["estimated_state"],
                    row["estimation_error"],
                    row["covariance"],
                )

            metrics = self.network.metrics_snapshot()
            self.db.log_metric(
                self.step,
                metrics["packet_delivery_ratio"],
                metrics["packet_loss_percentage"],
                metrics["bandwidth_usage"],
                metrics["throughput"],
                metrics["relay_queue_size"],
                metrics["drop_rate"],
                metrics["avg_delay"],
            )

            self.last_payload = {
                "network": {
                    "running": self.running,
                    "step": self.step,
                    "relay_queue_size": metrics["relay_queue_size"],
                    "throughput": metrics["throughput"],
                    "packet_delivery_ratio": metrics["packet_delivery_ratio"],
                    "packet_loss_percentage": metrics["packet_loss_percentage"],
                    "bandwidth_usage": metrics["bandwidth_usage"],
                    "dos_detected": metrics["dos_detected"],
                    "drop_rate": metrics["drop_rate"],
                    "avg_delay": metrics["avg_delay"],
                    "hop1_bandwidth_available": hop1_bandwidth,
                    "hop2_bandwidth_available": self.network.available_bandwidth(self.attack_module, "Hop2"),
                    "error_anomaly_index": anomaly_index,
                },
                "attacks": attack_status,
                "estimation": estimation_rows,
            }

            time.sleep(self.step_interval_sec)

    def network_status(self) -> Dict:
        return self.last_payload.get("network", {"running": self.running, "step": self.step})

    def attack_status(self) -> Dict:
        payload = self.last_payload.get("attacks", self.attack_module.current_status() if self.running else {})
        detection = self.network.get_detection_snapshot() if self.running else {}
        payload["detection"] = detection
        return payload

    def estimation_data(self, limit: int = 200) -> Dict:
        return {
            "live": self.last_payload.get("estimation", []),
            "history": self.db.latest_estimations(limit=limit),
        }

    def network_metrics(self, limit: int = 200) -> Dict:
        return {
            "live": self.last_payload.get("network", {}),
            "history": self.db.latest_metrics(limit=limit),
        }

    def logs(self, limit: int = 200) -> Dict:
        return self.db.latest_logs(limit=limit)
