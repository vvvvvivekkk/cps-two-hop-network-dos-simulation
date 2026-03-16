import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        ddl = """
        CREATE TABLE IF NOT EXISTS attacks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            step INTEGER,
            attack_type TEXT,
            target_link TEXT,
            active INTEGER,
            note TEXT
        );

        CREATE TABLE IF NOT EXISTS packet_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            step INTEGER,
            sensor_id INTEGER,
            packet_id TEXT,
            event TEXT,
            link TEXT,
            delay_steps INTEGER,
            dropped INTEGER
        );

        CREATE TABLE IF NOT EXISTS estimation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            step INTEGER,
            sensor_id INTEGER,
            true_state REAL,
            estimated_state REAL,
            estimation_error REAL,
            covariance REAL
        );

        CREATE TABLE IF NOT EXISTS network_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            step INTEGER,
            packet_delivery_ratio REAL,
            packet_loss_percentage REAL,
            bandwidth_usage REAL,
            throughput REAL,
            relay_queue_size INTEGER,
            drop_rate REAL,
            avg_delay REAL
        );

        CREATE TABLE IF NOT EXISTS sensor_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            step INTEGER,
            sensor_id INTEGER,
            true_state REAL,
            measurement REAL
        );
        """
        with self._lock:
            with self._conn() as conn:
                conn.executescript(ddl)
                conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> None:
        with self._lock:
            with self._conn() as conn:
                conn.execute(sql, params)
                conn.commit()

    def fetch_all(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._lock:
            with self._conn() as conn:
                rows = conn.execute(sql, params).fetchall()
                return [dict(r) for r in rows]

    def log_attack(self, step: int, attack_type: str, target_link: str, active: bool, note: str = "") -> None:
        self.execute(
            "INSERT INTO attacks(step, attack_type, target_link, active, note) VALUES (?, ?, ?, ?, ?)",
            (step, attack_type, target_link, int(active), note),
        )

    def log_packet(
        self,
        step: int,
        sensor_id: int,
        packet_id: str,
        event: str,
        link: str,
        delay_steps: int,
        dropped: bool,
    ) -> None:
        self.execute(
            """INSERT INTO packet_logs(step, sensor_id, packet_id, event, link, delay_steps, dropped)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (step, sensor_id, packet_id, event, link, delay_steps, int(dropped)),
        )

    def log_estimation(
        self,
        step: int,
        sensor_id: int,
        true_state: float,
        estimated_state: float,
        estimation_error: float,
        covariance: float,
    ) -> None:
        self.execute(
            """INSERT INTO estimation_results(step, sensor_id, true_state, estimated_state, estimation_error, covariance)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (step, sensor_id, true_state, estimated_state, estimation_error, covariance),
        )

    def log_metric(
        self,
        step: int,
        pdr: float,
        loss_pct: float,
        bandwidth_usage: float,
        throughput: float,
        relay_queue_size: int,
        drop_rate: float,
        avg_delay: float,
    ) -> None:
        self.execute(
            """INSERT INTO network_metrics(step, packet_delivery_ratio, packet_loss_percentage, bandwidth_usage,
               throughput, relay_queue_size, drop_rate, avg_delay)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (step, pdr, loss_pct, bandwidth_usage, throughput, relay_queue_size, drop_rate, avg_delay),
        )

    def log_sensor_data(self, step: int, sensor_id: int, true_state: float, measurement: float) -> None:
        self.execute(
            "INSERT INTO sensor_data(step, sensor_id, true_state, measurement) VALUES (?, ?, ?, ?)",
            (step, sensor_id, true_state, measurement),
        )

    def latest_metrics(self, limit: int = 200) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM network_metrics ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    def latest_estimations(self, limit: int = 500) -> List[Dict[str, Any]]:
        return self.fetch_all(
            "SELECT * FROM estimation_results ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    def latest_logs(self, limit: int = 300) -> Dict[str, List[Dict[str, Any]]]:
        return {
            "packet_logs": self.fetch_all("SELECT * FROM packet_logs ORDER BY id DESC LIMIT ?", (limit,)),
            "attacks": self.fetch_all("SELECT * FROM attacks ORDER BY id DESC LIMIT ?", (limit,)),
        }
