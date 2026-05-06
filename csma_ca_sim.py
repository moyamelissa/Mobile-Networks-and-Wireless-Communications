from __future__ import annotations

import argparse
import heapq
import math
import random
from collections import deque
from dataclasses import dataclass as _dataclass, field

# Le paramètre `slots` de `dataclass` n'existe qu'à partir de Python 3.10.
# Cette compatibilité permet de garder un seul code source pour la CI en 3.8/3.9
# et les environnements locaux plus récents ; si `slots` n'est pas disponible,
# on le retire simplement.
_DATACLASS_SUPPORTS_SLOTS = True
try:
    # On crée une dataclass de test pour savoir si l'interpréteur gère `slots`.
    _dataclass(slots=True)(type("_X", (), {}))
except TypeError:
    _DATACLASS_SUPPORTS_SLOTS = False


def dataclass_compat(**kwargs):
    if not _DATACLASS_SUPPORTS_SLOTS and "slots" in kwargs:
        kwargs = {k: v for k, v in kwargs.items() if k != "slots"}
    return _dataclass(**kwargs)
from pathlib import Path
from statistics import mean
from xml.sax.saxutils import escape
from typing import Optional


EVENT_ARRIVAL = "arrival"
EVENT_SLOT_TICK = "slot_tick"
EVENT_RTS_END = "rts_end"
EVENT_DATA_END = "data_end"


def next_slot_boundary(time_value: float, slot_time: float) -> float:
    if slot_time <= 0:
        raise ValueError("slot_time must be positive")
    scaled = (time_value - 1e-15) / slot_time
    slot_index = math.ceil(scaled)
    return max(0.0, slot_index * slot_time)


@dataclass_compat(slots=True)
class SimulationConfig:
    # Paramètres globaux de la simulation.
    # Ils regroupent les hypothèses MAC et temporelles qui pilotent tout le modèle.
    station_count: int = 8
    arrival_rate: float = 20.0
    simulation_time: float = 20.0
    packet_bits: int = 12000
    packet_duration: float = 0.001
    slot_time: float = 20e-6
    difs: float = 50e-6
    sifs: float = 10e-6
    wmin: int = 15
    wmax: int = 1023
    kmax: int = 15
    seed: Optional[int] = None
    rtscts: bool = False
    rts_duration: float = 200e-6
    cts_duration: float = 200e-6


@dataclass_compat(slots=True)
class PacketState:
    # Représente une trame en attente de transmission dans une station.
    # `arrival_time` sert à calculer le délai moyen, `attempts` à suivre les retransmissions.
    arrival_time: float
    attempts: int = 0


@dataclass_compat(slots=True)
class StationState:
    # État MAC d'une station.
    # `packet` garde la trame active, `queue` stocke les trames suivantes,
    # afin de ne pas perdre les arrivées lorsqu'une station est déjà occupée.
    # `contention_window`, `backoff` et `retries` modélisent l'accès au canal.
    # `nav_until` matérialise la réservation du médium imposée par RTS/CTS.
    station_id: int
    packet: Optional[PacketState] = None
    queue: deque[PacketState] = field(default_factory=deque)
    contention_window: int = 0
    backoff: int = 0
    retries: int = 0
    nav_until: float = 0.0


@dataclass_compat(slots=True)
class SimulationResult:
    # Résultats agrégés de la simulation, utilisés pour l'affichage et les graphiques.
    throughput_packets_per_s: float
    throughput_bits_per_s: float
    channel_utilization: float
    offered_load_packets_per_s: float
    collision_rate: float
    mean_delay_s: float
    generated_packets: int
    successful_packets: int
    dropped_packets: int
    total_attempts: int
    collided_packets: int


@dataclass_compat(slots=True)
class ExperimentPoint:
    # Un point de série expérimentale : une valeur de paramètre et les métriques associées.
    x_value: int
    throughput_packets_per_s: float
    throughput_bits_per_s: float
    collision_rate: float
    mean_delay_s: float


class CSMACASimulator:
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.random = random.Random(config.seed)
        self.stations = [StationState(station_id=index) for index in range(config.station_count)]

        self.event_queue: list[tuple[float, int, str, int, Optional[int]]] = []
        self.sequence = 0

        self.contenders: set[int] = set()
        self.current_transmission: Optional[set[int]] = None
        self.contention_open_time = 0.0
        self.scheduled_slot_tick_time: Optional[float] = None
        self.slot_tick_token = 0
        self.nav_until: float = 0.0

        self.generated_packets = 0
        self.successful_packets = 0
        self.dropped_packets = 0
        self.total_attempts = 0
        self.collided_packets = 0
        self.successful_bits = 0
        self.delay_sum = 0.0

    def run(self) -> SimulationResult:
        for station_id in range(self.config.station_count):
            first_arrival = self._sample_interarrival()
            if first_arrival <= self.config.simulation_time:
                self._push_event(first_arrival, EVENT_ARRIVAL, station_id)

        while self.event_queue:
            time_value, _, event_type, station_id, token = heapq.heappop(self.event_queue)

            if event_type == EVENT_SLOT_TICK:
                if token != self.slot_tick_token:
                    continue
                self.scheduled_slot_tick_time = None

            if event_type == EVENT_ARRIVAL:
                self._handle_arrival(time_value, station_id)
            elif event_type == EVENT_SLOT_TICK:
                self._handle_slot_tick(time_value)
            elif event_type == EVENT_RTS_END:
                self._handle_rts_end(time_value)
            elif event_type == EVENT_DATA_END:
                self._handle_data_end(time_value)
            else:
                raise RuntimeError(f"Unknown event type: {event_type}")

        throughput_packets_per_s = self.successful_packets / self.config.simulation_time if self.config.simulation_time > 0 else 0.0
        throughput_bits_per_s = self.successful_bits / self.config.simulation_time if self.config.simulation_time > 0 else 0.0
        channel_utilization = (self.successful_bits / (self.config.simulation_time * self.config.packet_bits)) if self.config.simulation_time > 0 and self.config.packet_bits > 0 else 0.0
        offered_load_packets_per_s = self.generated_packets / self.config.simulation_time if self.config.simulation_time > 0 else 0.0
        collision_rate = self.collided_packets / self.total_attempts if self.total_attempts > 0 else 0.0
        mean_delay_s = self.delay_sum / self.successful_packets if self.successful_packets > 0 else 0.0

        return SimulationResult(
            throughput_packets_per_s=throughput_packets_per_s,
            throughput_bits_per_s=throughput_bits_per_s,
            channel_utilization=channel_utilization,
            offered_load_packets_per_s=offered_load_packets_per_s,
            collision_rate=collision_rate,
            mean_delay_s=mean_delay_s,
            generated_packets=self.generated_packets,
            successful_packets=self.successful_packets,
            dropped_packets=self.dropped_packets,
            total_attempts=self.total_attempts,
            collided_packets=self.collided_packets,
        )

    def _push_event(self, time_value: float, event_type: str, station_id: int, token: Optional[int] = None) -> None:
        self.sequence += 1
        heapq.heappush(self.event_queue, (time_value, self.sequence, event_type, station_id, token))

    def _sample_interarrival(self) -> float:
        if self.config.arrival_rate <= 0:
            return math.inf
        return self.random.expovariate(self.config.arrival_rate)

    def _sample_backoff(self, contention_window: int) -> int:
        return self.random.randint(0, contention_window)

    def _prime_station_for_contention(self, station_id: int, current_time: float) -> None:
        station = self.stations[station_id]
        if station.packet is None:
            return

        station.contention_window = self.config.wmin
        station.retries = 0
        station.backoff = self._sample_backoff(station.contention_window)
        self.contenders.add(station_id)

        if self.current_transmission is None:
            self._schedule_slot_tick_if_needed(current_time)

    def _activate_next_queued_packet(self, station_id: int, current_time: float) -> None:
        station = self.stations[station_id]
        if station.packet is not None or not station.queue:
            return

        station.packet = station.queue.popleft()
        self._prime_station_for_contention(station_id, current_time)

    def _schedule_next_arrival(self, station_id: int, base_time: float) -> None:
        next_arrival = base_time + self._sample_interarrival()
        if next_arrival <= self.config.simulation_time:
            self._push_event(next_arrival, EVENT_ARRIVAL, station_id)

    def _schedule_slot_tick_if_needed(self, current_time: float) -> None:
        if self.current_transmission is not None or not self.contenders:
            return

        candidate = next_slot_boundary(max(current_time, self.contention_open_time), self.config.slot_time)
        if self.scheduled_slot_tick_time is not None and self.scheduled_slot_tick_time <= candidate:
            return

        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = candidate
        self._push_event(candidate, EVENT_SLOT_TICK, -1, self.slot_tick_token)

    def _start_transmission(self, current_time: float, station_ids: list[int]) -> None:
        if not station_ids:
            return

        self.current_transmission = set(station_ids)
        for station_id in station_ids:
            self.contenders.discard(station_id)
            self.stations[station_id].packet.attempts += 1  # type: ignore[union-attr]

        self.total_attempts += len(station_ids)
        if len(station_ids) > 1:
            # Collision logique : plusieurs stations ont atteint la transmission en même temps.
            release_time = current_time + self.config.packet_duration
        else:
            release_time = current_time + self.config.packet_duration + self.config.sifs

        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = None
        self._push_event(release_time, EVENT_DATA_END, -1)

    def _start_rts(self, current_time: float, station_ids: list[int]) -> None:
        if not station_ids:
            return

        self.current_transmission = set(station_ids)
        for station_id in station_ids:
            self.contenders.discard(station_id)
            self.stations[station_id].packet.attempts += 1  # type: ignore[union-attr]

        self.total_attempts += len(station_ids)
        rts_end = current_time + self.config.rts_duration
        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = None
        self._push_event(rts_end, EVENT_RTS_END, -1)

    def _handle_arrival(self, current_time: float, station_id: int) -> None:
        station = self.stations[station_id]
        self.generated_packets += 1
        packet = PacketState(arrival_time=current_time)

        if station.packet is None:
            station.packet = packet
            self._prime_station_for_contention(station_id, current_time)
            return

        station.queue.append(packet)

    def _handle_slot_tick(self, current_time: float) -> None:
        if self.current_transmission is not None or not self.contenders:
            return

        # Seules les stations hors NAV peuvent réellement contester le médium.
        active = [s for s in self.contenders if self.stations[s].nav_until <= current_time]

        ready_to_send = [station_id for station_id in active if self.stations[station_id].backoff == 0]
        if ready_to_send:
            if self.config.rtscts:
                self._start_rts(current_time, ready_to_send)
            else:
                self._start_transmission(current_time, ready_to_send)
            return

        for station_id in active:
            station = self.stations[station_id]
            if station.backoff > 0:
                station.backoff -= 1

        active_after = [station_id for station_id in active if self.stations[station_id].backoff == 0]
        if active_after:
            if self.config.rtscts:
                self._start_rts(current_time, active_after)
            else:
                self._start_transmission(current_time, active_after)
            return

        self._schedule_slot_tick_if_needed(current_time + self.config.slot_time)
    def _handle_rts_end(self, current_time: float) -> None:
        if self.current_transmission is None:
            return

        if len(self.current_transmission) > 1:
            # Collision RTS : on relance les stations concernées avec un nouveau backoff.
            affected_stations = list(self.current_transmission)
            self.collided_packets += len(affected_stations)
            self.current_transmission = None
            self.contention_open_time = current_time + self.config.difs

            for station_id in affected_stations:
                station = self.stations[station_id]
                station.retries += 1
                if station.retries > self.config.kmax:
                    self.dropped_packets += 1
                    station.packet = None
                    station.contention_window = self.config.wmin
                    station.retries = 0
                    self._schedule_next_arrival(station_id, current_time)
                    continue

                station.contention_window = min(2 * station.contention_window + 1, self.config.wmax)
                station.backoff = self._sample_backoff(station.contention_window)
                self.contenders.add(station_id)

            self._schedule_slot_tick_if_needed(current_time)
            return

        # RTS réussi : le point d'accès réserve ensuite le médium avant la donnée.
        station_id = next(iter(self.current_transmission))
        data_end_time = current_time + self.config.sifs + self.config.cts_duration + self.config.sifs + self.config.packet_duration

        # Toutes les autres stations placent leur NAV jusqu'à la fin de la trame.
        for s in range(len(self.stations)):
            if s == station_id:
                continue
            st = self.stations[s]
            if st.packet is not None:
                st.nav_until = data_end_time

        # On programme la fin de la transmission de données.
        self._push_event(data_end_time, EVENT_DATA_END, -1)

    def _handle_data_end(self, current_time: float) -> None:
        if self.current_transmission is None:
            return

        is_collision = len(self.current_transmission) > 1
        if not is_collision:
            station_id = next(iter(self.current_transmission))
            station = self.stations[station_id]
            self.successful_packets += 1
            self.successful_bits += self.config.packet_bits
            self.delay_sum += current_time - station.packet.arrival_time  # type: ignore[union-attr]
            station.packet = None
            station.contention_window = self.config.wmin
            station.retries = 0
            self.current_transmission = None
            self.contention_open_time = current_time + self.config.difs
            self._activate_next_queued_packet(station_id, current_time)
            self._schedule_next_arrival(station_id, current_time)
            self._schedule_slot_tick_if_needed(current_time)
            return

        # Collision de données : cas rare avec RTS/CTS, ou plusieurs émetteurs synchrones.
        affected_stations = list(self.current_transmission)
        self.current_transmission = None
        self.contention_open_time = current_time + self.config.difs

        for station_id in affected_stations:
            station = self.stations[station_id]
            station.retries += 1
            if station.retries > self.config.kmax:
                self.dropped_packets += 1
                station.packet = None
                station.contention_window = self.config.wmin
                station.retries = 0
                self._activate_next_queued_packet(station_id, current_time)
                self._schedule_next_arrival(station_id, current_time)
                continue

            station.contention_window = min(2 * station.contention_window + 1, self.config.wmax)
            station.backoff = self._sample_backoff(station.contention_window)
            self.contenders.add(station_id)

        self._schedule_slot_tick_if_needed(current_time)


def run_single_experiment(config: SimulationConfig) -> SimulationResult:
    simulator = CSMACASimulator(config)
    return simulator.run()


def average_results(results: list[SimulationResult]) -> SimulationResult:
    if not results:
        raise ValueError("results must not be empty")

    return SimulationResult(
        throughput_packets_per_s=mean(result.throughput_packets_per_s for result in results),
        throughput_bits_per_s=mean(result.throughput_bits_per_s for result in results),
        channel_utilization=mean(result.channel_utilization for result in results),
        offered_load_packets_per_s=mean(result.offered_load_packets_per_s for result in results),
        collision_rate=mean(result.collision_rate for result in results),
        mean_delay_s=mean(result.mean_delay_s for result in results),
        generated_packets=sum(result.generated_packets for result in results),
        successful_packets=sum(result.successful_packets for result in results),
        dropped_packets=sum(result.dropped_packets for result in results),
        total_attempts=sum(result.total_attempts for result in results),
        collided_packets=sum(result.collided_packets for result in results),
    )


def sweep_stations(
    base_config: SimulationConfig,
    start: int,
    stop: int,
    step: int,
    runs: int,
) -> list[ExperimentPoint]:
    if step <= 0:
        raise ValueError("step must be positive")
    if runs <= 0:
        raise ValueError("runs must be positive")

    points: list[ExperimentPoint] = []
    for station_count in range(start, stop + 1, step):
        run_results: list[SimulationResult] = []
        for repeat_index in range(runs):
            config = SimulationConfig(
                station_count=station_count,
                arrival_rate=base_config.arrival_rate,
                simulation_time=base_config.simulation_time,
                packet_bits=base_config.packet_bits,
                packet_duration=base_config.packet_duration,
                slot_time=base_config.slot_time,
                difs=base_config.difs,
                sifs=base_config.sifs,
                wmin=base_config.wmin,
                wmax=base_config.wmax,
                kmax=base_config.kmax,
                seed=None if base_config.seed is None else base_config.seed + repeat_index + station_count * 1000,
                rtscts=base_config.rtscts,
                rts_duration=base_config.rts_duration,
                cts_duration=base_config.cts_duration,
            )
            run_results.append(run_single_experiment(config))

        averaged = average_results(run_results)
        points.append(
            ExperimentPoint(
                x_value=station_count,
                throughput_packets_per_s=averaged.throughput_packets_per_s,
                throughput_bits_per_s=averaged.throughput_bits_per_s,
                collision_rate=averaged.collision_rate,
                mean_delay_s=averaged.mean_delay_s,
            )
        )

    return points


def sweep_wmin(
    base_config: SimulationConfig,
    start: int,
    stop: int,
    step: int,
    runs: int,
) -> list[ExperimentPoint]:
    if step <= 0:
        raise ValueError("step must be positive")
    if runs <= 0:
        raise ValueError("runs must be positive")

    points: list[ExperimentPoint] = []
    for wmin in range(start, stop + 1, step):
        run_results: list[SimulationResult] = []
        for repeat_index in range(runs):
            config = SimulationConfig(
                station_count=base_config.station_count,
                arrival_rate=base_config.arrival_rate,
                simulation_time=base_config.simulation_time,
                packet_bits=base_config.packet_bits,
                packet_duration=base_config.packet_duration,
                slot_time=base_config.slot_time,
                difs=base_config.difs,
                sifs=base_config.sifs,
                wmin=wmin,
                wmax=max(base_config.wmax, wmin),
                kmax=base_config.kmax,
                seed=None if base_config.seed is None else base_config.seed + repeat_index + wmin * 1000,
                rtscts=base_config.rtscts,
                rts_duration=base_config.rts_duration,
                cts_duration=base_config.cts_duration,
            )
            run_results.append(run_single_experiment(config))

        averaged = average_results(run_results)
        points.append(
            ExperimentPoint(
                x_value=wmin,
                throughput_packets_per_s=averaged.throughput_packets_per_s,
                throughput_bits_per_s=averaged.throughput_bits_per_s,
                collision_rate=averaged.collision_rate,
                mean_delay_s=averaged.mean_delay_s,
            )
        )

    return points


def print_result(config: SimulationConfig, result: SimulationResult) -> None:
    print("Configuration")
    print(f"  Stations              : {config.station_count}")
    print(f"  Arrival rate/station   : {config.arrival_rate:.4f} packets/s")
    print(f"  Simulated time         : {config.simulation_time:.4f} s")
    print(f"  Packet duration        : {config.packet_duration:.6f} s")
    print(f"  Packet size            : {config.packet_bits} bits")
    print(f"  Slot time              : {config.slot_time:.8f} s")
    print(f"  DIFS / SIFS            : {config.difs:.8f} s / {config.sifs:.8f} s")
    print(f"  Wmin / Wmax / Kmax     : {config.wmin} / {config.wmax} / {config.kmax}")
    print()
    print("Results")
    print(f"  Throughput             : {result.throughput_packets_per_s:.4f} packets/s")
    print(f"  Throughput             : {result.throughput_bits_per_s:.4f} bits/s")
    print(f"  Channel utilization    : {result.channel_utilization * 100:.2f} %")
    print(f"  Offered load           : {result.offered_load_packets_per_s:.4f} packets/s")
    print(f"  Mean collision rate    : {result.collision_rate * 100:.2f} %")
    print(f"  Mean transmission delay: {result.mean_delay_s * 1000:.4f} ms")
    print(f"  Generated packets      : {result.generated_packets}")
    print(f"  Successful packets     : {result.successful_packets}")
    print(f"  Dropped packets        : {result.dropped_packets}")
    print(f"  Total attempts         : {result.total_attempts}")
    print(f"  Collided packets       : {result.collided_packets}")


def plot_points(points: list[ExperimentPoint], title: str, x_label: str, output_path: Path) -> None:
    if not points:
        raise ValueError("points must not be empty")

    width = 980
    height = 1160
    panel_width = 880
    panel_height = 270
    left = 50
    top_margin = 80
    panel_gap = 60
    inner_left = 90
    inner_right = 35
    inner_top = 35
    inner_bottom = 48

    x_values = [point.x_value for point in points]
    throughput_bits = [point.throughput_bits_per_s for point in points]
    collision_rates = [point.collision_rate * 100 for point in points]
    mean_delays = [point.mean_delay_s * 1000 for point in points]

    def scale_x(index: int, count: int) -> float:
        plot_w = panel_width - inner_left - inner_right
        if count == 1:
            return left + inner_left + plot_w / 2
        return left + inner_left + (plot_w * index / (count - 1))

    def scale_y(value: float, minimum: float, maximum: float, panel_top: float) -> float:
        plot_h = panel_height - inner_top - inner_bottom
        if math.isclose(minimum, maximum):
            return panel_top + inner_top + plot_h / 2
        return panel_top + inner_top + (maximum - value) * plot_h / (maximum - minimum)

    def format_ticks(minimum: float, maximum: float, count: int = 5) -> list[float]:
        if math.isclose(minimum, maximum):
            return [minimum]
        step = (maximum - minimum) / (count - 1)
        return [minimum + step * index for index in range(count)]

    def panel_svg(panel_top: float, panel_title: str, y_label: str, series: list[tuple[list[float], str, str]]) -> str:
        y_min = min(min(values) for values, _, _ in series)
        y_max = max(max(values) for values, _, _ in series)
        if math.isclose(y_min, y_max):
            y_min = 0.0
            y_max = y_max + 1.0
        y_padding = (y_max - y_min) * 0.08 or 1.0
        y_min = max(0.0, y_min - y_padding)
        y_max = y_max + y_padding

        elements: list[str] = []
        elements.append(f'<rect x="{left}" y="{panel_top}" width="{panel_width}" height="{panel_height}" rx="18" fill="#fbfbfd" stroke="#d9dce3"/>')
        elements.append(f'<text x="{left + 18}" y="{panel_top + 26}" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" fill="#1f2937">{escape(panel_title)}</text>')
        elements.append(f'<text x="{left + 18}" y="{panel_top + 50}" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#4b5563">{escape(y_label)}</text>')

        plot_left = left + inner_left
        plot_top = panel_top + inner_top
        plot_w = panel_width - inner_left - inner_right
        plot_h = panel_height - inner_top - inner_bottom

        elements.append(f'<line x1="{plot_left}" y1="{plot_top + plot_h}" x2="{plot_left + plot_w}" y2="{plot_top + plot_h}" stroke="#334155" stroke-width="1.2"/>')
        elements.append(f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_top + plot_h}" stroke="#334155" stroke-width="1.2"/>')

        for tick_value in format_ticks(y_min, y_max):
            y = scale_y(tick_value, y_min, y_max, panel_top)
            elements.append(f'<line x1="{plot_left - 5}" y1="{y}" x2="{plot_left}" y2="{y}" stroke="#334155" stroke-width="1"/>')
            elements.append(f'<text x="{plot_left - 10}" y="{y + 4}" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#475569">{tick_value:.2f}</text>')

        for idx, x_value in enumerate(x_values):
            x = scale_x(idx, len(x_values))
            elements.append(f'<line x1="{x}" y1="{plot_top + plot_h}" x2="{x}" y2="{plot_top + plot_h + 5}" stroke="#334155" stroke-width="1"/>')
            elements.append(f'<text x="{x}" y="{plot_top + plot_h + 20}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#475569">{x_value}</text>')

        for series_index, (values, color, label) in enumerate(series):
            coords = []
            for idx, value in enumerate(values):
                x = scale_x(idx, len(x_values))
                y = scale_y(value, y_min, y_max, panel_top)
                coords.append(f"{x:.2f},{y:.2f}")
            elements.append(f'<polyline fill="none" stroke="{color}" stroke-width="3" points="{" ".join(coords)}"/>')
            for idx, value in enumerate(values):
                x = scale_x(idx, len(x_values))
                y = scale_y(value, y_min, y_max, panel_top)
                elements.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4.5" fill="{color}" stroke="#ffffff" stroke-width="1"/>')
            legend_x = left + panel_width - 170
            legend_y = panel_top + 26 + series_index * 22
            elements.append(f'<rect x="{legend_x}" y="{legend_y - 12}" width="10" height="10" fill="{color}"/>')
            elements.append(f'<text x="{legend_x + 16}" y="{legend_y - 3}" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#334155">{escape(label)}</text>')

        return "\n".join(elements)

    throughput_panel = panel_svg(
        top_margin,
        "Throughput",
        "Bits/s",
        [
            (throughput_bits, "#dc2626", "Bits/s"),
        ],
    )
    collision_panel = panel_svg(
        top_margin + panel_height + panel_gap,
        "Collision rate",
        "Collision rate (%)",
        [(collision_rates, "#dc2626", "Collision rate")],
    )
    delay_panel = panel_svg(
        top_margin + (panel_height + panel_gap) * 2,
        "Transmission delay",
        "Delay (ms)",
        [(mean_delays, "#059669", "Mean delay")],
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f8fafc"/>
      <stop offset="100%" stop-color="#eef2ff"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <text x="{width / 2}" y="40" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="24" font-weight="700" fill="#111827">{escape(title)}</text>
  <text x="{width / 2}" y="64" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="12" fill="#475569">{escape(x_label)}</text>
  {throughput_panel}
  {collision_panel}
  {delay_panel}
  <text x="{width - 24}" y="{height - 18}" text-anchor="end" font-family="Arial, Helvetica, sans-serif" font-size="11" fill="#64748b">Generated by csma_ca_sim.py</text>
</svg>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discrete-event CSMA/CA simulator with exponential backoff")
    parser.add_argument("--stations", type=int, default=8, help="Number of stations")
    parser.add_argument("--arrival-rate", type=float, default=20.0, help="Poisson arrival rate per station (packets/s)")
    parser.add_argument("--simulation-time", type=float, default=20.0, help="Simulation horizon in seconds")
    parser.add_argument("--packet-bits", type=int, default=12000, help="Packet size in bits")
    parser.add_argument("--packet-duration", type=float, default=0.001, help="Packet transmission duration in seconds")
    parser.add_argument("--slot-time", type=float, default=20e-6, help="Slot time in seconds")
    parser.add_argument("--difs", type=float, default=50e-6, help="DIFS in seconds")
    parser.add_argument("--sifs", type=float, default=10e-6, help="SIFS in seconds")
    parser.add_argument("--wmin", type=int, default=15, help="Minimum contention window")
    parser.add_argument("--wmax", type=int, default=1023, help="Maximum contention window")
    parser.add_argument("--kmax", type=int, default=15, help="Maximum retransmissions before drop")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--runs", type=int, default=1, help="Number of repetitions to average")
    parser.add_argument("--output", type=Path, default=Path("csma_ca_results.svg"), help="Plot output path")
    parser.add_argument("--rtscts", action="store_true", help="Enable RTS/CTS handshake and NAV")
    parser.add_argument("--rts-duration", type=float, default=200e-6, help="RTS duration in seconds")
    parser.add_argument("--cts-duration", type=float, default=200e-6, help="CTS duration in seconds")

    sweep_group = parser.add_mutually_exclusive_group()
    sweep_group.add_argument("--sweep-stations", nargs=3, type=int, metavar=("START", "STOP", "STEP"), help="Sweep the number of stations")
    sweep_group.add_argument("--sweep-wmin", nargs=3, type=int, metavar=("START", "STOP", "STEP"), help="Sweep the minimum contention window")

    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    config = SimulationConfig(
        station_count=args.stations,
        arrival_rate=args.arrival_rate,
        simulation_time=args.simulation_time,
        packet_bits=args.packet_bits,
        packet_duration=args.packet_duration,
        slot_time=args.slot_time,
        difs=args.difs,
        sifs=args.sifs,
        wmin=args.wmin,
        wmax=args.wmax,
        kmax=args.kmax,
        seed=args.seed,
        rtscts=args.rtscts,
        rts_duration=args.rts_duration,
        cts_duration=args.cts_duration,
    )

    if args.runs <= 0:
        raise SystemExit("--runs must be positive")

    if args.sweep_stations is not None:
        start, stop, step = args.sweep_stations
        points = sweep_stations(config, start, stop, step, args.runs)
        print("Station sweep")
        for point in points:
            print(
                f"N={point.x_value:3d} | throughput={point.throughput_bits_per_s:12.2f} bits/s | "
                f"collision={point.collision_rate * 100:6.2f} % | delay={point.mean_delay_s * 1000:8.4f} ms"
            )
        plot_points(points, "CSMA/CA: impact of station count", "Number of stations", args.output)
        print(f"Plot saved to {args.output}")
        return

    if args.sweep_wmin is not None:
        start, stop, step = args.sweep_wmin
        points = sweep_wmin(config, start, stop, step, args.runs)
        print("Wmin sweep")
        for point in points:
            print(
                f"Wmin={point.x_value:3d} | throughput={point.throughput_bits_per_s:12.2f} bits/s | "
                f"collision={point.collision_rate * 100:6.2f} % | delay={point.mean_delay_s * 1000:8.4f} ms"
            )
        plot_points(points, "CSMA/CA: impact of Wmin", "Minimum contention window", args.output)
        print(f"Plot saved to {args.output}")
        return

    if args.runs == 1:
        result = run_single_experiment(config)
    else:
        run_results = [
            run_single_experiment(
                SimulationConfig(
                    station_count=config.station_count,
                    arrival_rate=config.arrival_rate,
                    simulation_time=config.simulation_time,
                    packet_bits=config.packet_bits,
                    packet_duration=config.packet_duration,
                    slot_time=config.slot_time,
                    difs=config.difs,
                    sifs=config.sifs,
                    wmin=config.wmin,
                    wmax=config.wmax,
                    kmax=config.kmax,
                    seed=None if config.seed is None else config.seed + index,
                    rtscts=config.rtscts,
                    rts_duration=config.rts_duration,
                    cts_duration=config.cts_duration,
                )
            )
            for index in range(args.runs)
        ]
        result = average_results(run_results)

    print_result(config, result)


if __name__ == "__main__":
    main()