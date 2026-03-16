import random
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Tuple


@dataclass
class Packet:
    packet_id: str
    sensor_id: int
    step_created: int
    measurement: float


class AttackRuntime:
    def __init__(self, attack_type: str, probability: float, duration: int, target_link: str):
        self.attack_type = attack_type
        self.probability = probability
        self.duration = duration
        self.target_link = target_link
        self.remaining = 0

    @property
    def active(self) -> bool:
        return self.remaining > 0

    def update(self) -> bool:
        previously_active = self.active
        if self.remaining > 0:
            self.remaining -= 1
        else:
            if random.random() < self.probability:
                self.remaining = self.duration
        return previously_active != self.active


class DoSAttackModule:
    def __init__(self, attack_profiles: List[Dict]):
        self.attacks: List[AttackRuntime] = [
            AttackRuntime(
                attack_type=a["attack_type"],
                probability=a["attack_probability"],
                duration=a["attack_duration"],
                target_link=a["target_link"],
            )
            for a in attack_profiles
        ]

    def update(self) -> List[Tuple[str, str, bool]]:
        transitions: List[Tuple[str, str, bool]] = []
        for attack in self.attacks:
            changed = attack.update()
            if changed:
                transitions.append((attack.attack_type, attack.target_link, attack.active))
        return transitions

    def current_status(self) -> Dict:
        active = [
            {
                "attack_type": a.attack_type,
                "target_link": a.target_link,
                "remaining": a.remaining,
            }
            for a in self.attacks
            if a.active
        ]
        return {
            "active": len(active) > 0,
            "active_attacks": active,
        }

    def effects_for_link(self, link: str) -> Dict[str, float]:
        effects = {
            "drop_probability": 0.0,
            "delay_probability": 0.0,
            "flood_factor": 1.0,
        }
        for attack in self.attacks:
            if not attack.active or attack.target_link != link:
                continue
            if attack.attack_type == "packet_drop":
                effects["drop_probability"] = min(0.95, effects["drop_probability"] + 0.35)
            elif attack.attack_type == "delay":
                effects["delay_probability"] = min(0.95, effects["delay_probability"] + 0.45)
            elif attack.attack_type == "bandwidth_flood":
                effects["flood_factor"] *= 0.35
        return effects


class RelayBufferManager:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.queue: Deque[Packet] = deque()

    def enqueue(self, packet: Packet) -> bool:
        if len(self.queue) >= self.capacity:
            return False
        self.queue.append(packet)
        return True

    def dequeue_many(self, max_items: int) -> List[Packet]:
        items: List[Packet] = []
        for _ in range(min(max_items, len(self.queue))):
            items.append(self.queue.popleft())
        return items

    def size(self) -> int:
        return len(self.queue)


class TwoHopCommunicationManager:
    def __init__(self, relay_capacity: int, base_bandwidth_packets: int):
        self.relay = RelayBufferManager(relay_capacity)
        self.base_bandwidth_packets = base_bandwidth_packets

        self.pending_hop1: Deque[Tuple[int, Packet]] = deque()
        self.pending_hop2: Deque[Tuple[int, Packet]] = deque()

        self.stats = {
            "sent": 0,
            "dropped": 0,
            "delayed": 0,
            "delivered": 0,
            "bytes": 0,
            "total_delay_steps": 0,
        }
        self.recent_drop_window: Deque[int] = deque(maxlen=50)
        self.recent_delay_window: Deque[int] = deque(maxlen=50)

    def available_bandwidth(self, attack_module: DoSAttackModule, link: str) -> int:
        effects = attack_module.effects_for_link(link)
        effective = int(max(0, round(self.base_bandwidth_packets * effects["flood_factor"])))
        return effective

    def _apply_link_effects(
        self,
        packet: Packet,
        attack_module: DoSAttackModule,
        link: str,
        current_step: int,
    ) -> Tuple[bool, int]:
        effects = attack_module.effects_for_link(link)
        if random.random() < effects["drop_probability"]:
            self.stats["dropped"] += 1
            self.recent_drop_window.append(1)
            self.recent_delay_window.append(0)
            return False, 0

        delay_steps = 0
        if random.random() < effects["delay_probability"]:
            delay_steps = random.randint(1, 3)
            self.stats["delayed"] += 1

        self.recent_drop_window.append(0)
        self.recent_delay_window.append(delay_steps)
        return True, delay_steps

    def send_sensor_packet(
        self,
        packet: Packet,
        attack_module: DoSAttackModule,
        current_step: int,
    ) -> Dict:
        self.stats["sent"] += 1
        self.stats["bytes"] += 64
        ok, delay_steps = self._apply_link_effects(packet, attack_module, "Hop1", current_step)
        if not ok:
            return {"event": "drop", "link": "Hop1", "delay_steps": 0, "dropped": True}

        if delay_steps > 0:
            self.pending_hop1.append((current_step + delay_steps, packet))
        else:
            accepted = self.relay.enqueue(packet)
            if not accepted:
                self.stats["dropped"] += 1
                self.recent_drop_window.append(1)
                return {"event": "buffer_overflow", "link": "Hop1", "delay_steps": 0, "dropped": True}

        return {"event": "forwarded", "link": "Hop1", "delay_steps": delay_steps, "dropped": False}

    def _flush_hop1_delays(self, current_step: int) -> None:
        while self.pending_hop1 and self.pending_hop1[0][0] <= current_step:
            _, packet = self.pending_hop1.popleft()
            accepted = self.relay.enqueue(packet)
            if not accepted:
                self.stats["dropped"] += 1
                self.recent_drop_window.append(1)

    def _flush_hop2_delays(self, current_step: int, delivered: List[Packet]) -> None:
        while self.pending_hop2 and self.pending_hop2[0][0] <= current_step:
            _, packet = self.pending_hop2.popleft()
            delivered.append(packet)
            self.stats["delivered"] += 1

    def relay_to_estimator(self, attack_module: DoSAttackModule, current_step: int) -> List[Packet]:
        self._flush_hop1_delays(current_step)

        delivered: List[Packet] = []
        budget = self.available_bandwidth(attack_module, "Hop2")
        for packet in self.relay.dequeue_many(budget):
            ok, delay_steps = self._apply_link_effects(packet, attack_module, "Hop2", current_step)
            if not ok:
                continue
            if delay_steps > 0:
                self.pending_hop2.append((current_step + delay_steps, packet))
                self.stats["total_delay_steps"] += delay_steps
            else:
                delivered.append(packet)
                self.stats["delivered"] += 1

        self._flush_hop2_delays(current_step, delivered)
        return delivered

    def get_detection_snapshot(self) -> Dict:
        drop_rate = sum(self.recent_drop_window) / len(self.recent_drop_window) if self.recent_drop_window else 0.0
        avg_delay = sum(self.recent_delay_window) / len(self.recent_delay_window) if self.recent_delay_window else 0.0
        return {
            "drop_rate": drop_rate,
            "avg_delay": avg_delay,
            "dos_detected": drop_rate > 0.30 or avg_delay > 1.2,
        }

    def metrics_snapshot(self) -> Dict:
        sent = self.stats["sent"]
        delivered = self.stats["delivered"]
        dropped = self.stats["dropped"]
        pdr = (delivered / sent) if sent else 1.0
        loss_pct = (dropped / sent * 100.0) if sent else 0.0
        throughput = delivered
        bandwidth_usage = self.stats["bytes"] / max(1, sent)
        detection = self.get_detection_snapshot()
        return {
            "packet_delivery_ratio": pdr,
            "packet_loss_percentage": loss_pct,
            "throughput": throughput,
            "bandwidth_usage": bandwidth_usage,
            "relay_queue_size": self.relay.size(),
            "drop_rate": detection["drop_rate"],
            "avg_delay": detection["avg_delay"],
            "dos_detected": detection["dos_detected"],
        }
