"""Simulateur à événements discrets du protocole CSMA/CA (IEEE 802.11, BEB, RTS/CTS optionnel).

Usage :
    python csma_ca_sim.py --stations 8 --arrival-rate 20 --simulation-time 20
    python csma_ca_sim.py --sweep-stations 2 20 2 --runs 3 --output resultats.svg

Graphiques : tools/plot.py — Expériences : tools/run_experiments.py
"""
from __future__ import annotations

import argparse
import heapq
import math
import random
from dataclasses import dataclass as _dataclass

# `slots` n'existe que depuis Python 3.10 — retiré silencieusement si absent.
_DATACLASS_SUPPORTS_SLOTS = True
try:
    _dataclass(slots=True)(type("_X", (), {}))
except TypeError:  # pragma: no cover
    _DATACLASS_SUPPORTS_SLOTS = False  # pragma: no cover


def dataclass_compat(**kwargs):
    """Décorateur @dataclass compatible 3.8+ (retire `slots` si non supporté)."""
    if not _DATACLASS_SUPPORTS_SLOTS and "slots" in kwargs:
        kwargs = {k: v for k, v in kwargs.items() if k != "slots"}
    return _dataclass(**kwargs)
from pathlib import Path
from statistics import mean, pstdev
from typing import Optional

from tools.plot import plot_points          # graphique SVG (tools/plot.py)
from tools.print_result import print_result  # affichage console (tools/print_result.py)
from tools.save_csv import save_csv          # export CSV (tools/save_csv.py)


# ---------------------------------------------------------------------------
# Types d'événements du moteur de simulation
# ---------------------------------------------------------------------------
EVENT_ARRIVAL  = "arrival"    # Arrivée d'un paquet dans une station
EVENT_SLOT_TICK = "slot_tick" # Tick de slot de backoff
EVENT_RTS_END  = "rts_end"    # Fin d'émission RTS (mode RTS/CTS)
EVENT_DATA_END = "data_end"   # Fin d'émission d'une trame de données


def next_slot_boundary(time_value: float, slot_time: float) -> float:
    """Retourne le plus petit multiple de slot_time >= time_value.

    Le décalage 1e-15 corrige les erreurs d'arrondi sur les flottants déjà alignés.
    Lève ValueError si slot_time <= 0.
    """
    if slot_time <= 0:
        raise ValueError("slot_time must be positive")
    scaled = (time_value - 1e-15) / slot_time
    slot_index = math.ceil(scaled)
    return max(0.0, slot_index * slot_time)


@dataclass_compat(slots=True)
class SimulationConfig:
    """Paramètres MAC et temporels de la simulation (défauts : IEEE 802.11b)."""
    station_count: int = 8        # Nombre de stations en compétition pour le canal
    arrival_rate: float = 20.0    # Taux d'arrivée par station (paquets/s) — processus de renouvellement
    simulation_time: float = 20.0 # Horizon de simulation (secondes)
    packet_bits: int = 12000      # Taille d'un paquet (bits) — 12 000 bits = 1 500 octets
    packet_duration: float = 0.001 # Durée de transmission d'un paquet (secondes)
    slot_time: float = 20e-6      # Durée d'un slot de backoff (secondes)
    difs: float = 50e-6           # DIFS : délai inter-trames distribué (secondes)
    sifs: float = 10e-6           # SIFS : délai inter-trames court (secondes)
    wmin: int = 15                # Fenêtre de contention minimale W_min
    wmax: int = 1023              # Fenêtre de contention maximale W_max
    kmax: int = 15                # Nombre maximal de tentatives avant abandon du paquet
    seed: Optional[int] = None    # Graine aléatoire (None = non déterministe)
    rtscts: bool = False          # Active le mécanisme RTS/CTS et le NAV si True
    rts_duration: float = 200e-6  # Durée d'une trame RTS (secondes)
    cts_duration: float = 200e-6  # Durée d'une trame CTS (secondes)


@dataclass_compat(slots=True)
class PacketState:
    """Trame active dans une station (créée à l'arrivée, détruite après succès ou abandon)."""
    arrival_time: float  # Instant de génération du paquet — sert à calculer le délai moyen
    attempts: int = 0   # Nombre de tentatives de transmission déjà effectuées pour ce paquet


@dataclass_compat(slots=True)
class StationState:
    """État MAC d'une station : une seule trame active (None = inactive), compteurs BEB et NAV."""
    station_id: int                      # Identifiant unique de la station (index dans la liste)
    packet: Optional[PacketState] = None # Trame active (None = station inactive)
    contention_window: int = 0           # Fenêtre de contention courante W ∈ [W_min, W_max]
    backoff: int = 0                     # Compteur de backoff courant b ∈ [0, W]
    retries: int = 0                     # Nombre de tentatives échouées pour la trame courante (K)
    nav_until: float = 0.0               # Instant jusqu'auquel le médium est réservé (NAV)


@dataclass_compat(slots=True)
class SimulationResult:
    """Métriques agrégées retournées par run_single_experiment() et average_results()."""
    throughput_packets_per_s: float   # Débit en paquets transmis avec succès par seconde
    throughput_bits_per_s: float      # Débit binaire utile (bits/s)
    channel_utilization: float        # Fraction du temps où le canal transporte des données utiles
    offered_load_packets_per_s: float # Charge offerte totale (paquets générés / s)
    collision_rate: float             # Proportion des tentatives ayant abouti à une collision
    mean_delay_s: float               # Délai moyen entre génération et transmission réussie (s)
    generated_packets: int            # Nombre total de paquets générés durant la simulation
    successful_packets: int           # Nombre de paquets transmis avec succès
    dropped_packets: int              # Nombre de paquets abandonnés (K > K_max)
    total_attempts: int               # Nombre total de tentatives de transmission
    collided_packets: int             # Nombre de tentatives ayant abouti à une collision


@dataclass_compat(slots=True)
class ExperimentPoint:
    """Point de courbe : valeur du paramètre balayé + métriques moyennes et écarts-types (±σ)."""
    x_value: int                       # Valeur du paramètre balayé (ex. nombre de stations)
    throughput_packets_per_s: float    # Débit moyen (paquets/s)
    throughput_bits_per_s: float       # Débit binaire moyen (bits/s)
    collision_rate: float              # Taux de collision moyen
    mean_delay_s: float                # Délai moyen de transmission (secondes)
    throughput_bits_std: float = 0.0   # Écart-type du débit binaire entre les répétitions (bits/s)
    collision_rate_std: float = 0.0    # Écart-type du taux de collision entre les répétitions
    mean_delay_std: float = 0.0        # Écart-type du délai moyen entre les répétitions (secondes)


class CSMACASimulator:
    """Moteur à événements discrets CSMA/CA. Instancier puis appeler run()."""

    def __init__(self, config: SimulationConfig):
        """Initialise le simulateur avec la configuration donnée."""
        self.config = config
        self.random = random.Random(config.seed)  # RNG isolé — reproductible via config.seed
        self.stations = [StationState(station_id=i) for i in range(config.station_count)]

        # Min-heap : (temps, séquence, type_événement, station_id, jeton)
        # Séquence monotone pour ordre stable à temps égaux.
        self.event_queue: list[tuple[float, int, str, int, Optional[int]]] = []
        self.sequence = 0

        self.contenders: set[int] = set()                      # Stations en phase de backoff
        self.current_transmission: Optional[set[int]] = None   # En transmission (None = libre ; len > 1 = collision)
        self.contention_open_time = 0.0                        # Ouverture de contention après DIFS
        self.scheduled_slot_tick_time: Optional[float] = None  # Prochain slot_tick prévu
        self.slot_tick_token = 0                               # Jeton d'invalidation des slot_ticks périmés

        # Compteurs cumulés — agrégés dans run()
        self.generated_packets = 0
        self.successful_packets = 0
        self.dropped_packets = 0
        self.total_attempts = 0
        self.collided_packets = 0
        self.successful_bits = 0
        self.delay_sum = 0.0

    def run(self) -> SimulationResult:
        """Planifie les premières arrivées, traite la file d'événements, retourne les métriques."""
        # Première arrivée de chaque station (loi exponentielle)
        for station_id in range(self.config.station_count):
            first_arrival = self._sample_interarrival()
            if first_arrival <= self.config.simulation_time:
                self._push_event(first_arrival, EVENT_ARRIVAL, station_id)

        # Boucle principale : traite les événements par ordre chronologique
        while self.event_queue:
            time_value, _, event_type, station_id, token = heapq.heappop(self.event_queue)

            if event_type == EVENT_SLOT_TICK:
                if token != self.slot_tick_token:
                    continue  # pragma: no cover
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

        # Métriques finales
        throughput_packets_per_s = self.successful_packets / self.config.simulation_time if self.config.simulation_time > 0 else 0.0
        throughput_bits_per_s = self.successful_bits / self.config.simulation_time if self.config.simulation_time > 0 else 0.0
        channel_utilization = (
            (self.successful_packets * self.config.packet_duration) / self.config.simulation_time
            if self.config.simulation_time > 0 and self.config.packet_duration > 0
            else 0.0
        )
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
        """Insère un événement dans la file (séquence monotone pour ordre stable à temps égaux)."""
        self.sequence += 1
        heapq.heappush(self.event_queue, (time_value, self.sequence, event_type, station_id, token))

    def _sample_interarrival(self) -> float:
        """Inter-arrivée ~ Exp(λ). Processus de renouvellement (non Poisson pur).
        Retourne inf si arrival_rate <= 0.
        """
        if self.config.arrival_rate <= 0:
            return math.inf
        return self.random.expovariate(self.config.arrival_rate)

    def _sample_backoff(self, contention_window: int) -> int:
        """Tire b ~ U[0, contention_window] (règle BEB IEEE 802.11)."""
        return self.random.randint(0, contention_window)

    def _prime_station_for_contention(self, station_id: int, current_time: float) -> None:
        """Initialise W=W_min, K=0, tire b et enregistre la station en contention."""
        station = self.stations[station_id]
        if station.packet is None:
            return  # Pas de paquet actif : rien à faire

        # W=W_min, K=0 pour le premier essai (IEEE 802.11)
        station.contention_window = self.config.wmin
        station.retries = 0
        station.backoff = self._sample_backoff(station.contention_window)
        self.contenders.add(station_id)

        # Déclenche le slot_tick si le canal est libre
        if self.current_transmission is None:
            self._schedule_slot_tick_if_needed(current_time)

    def _schedule_next_arrival(self, station_id: int, base_time: float) -> None:
        """Planifie la prochaine arrivée après résolution du paquet courant (dans l'horizon)."""
        next_arrival = base_time + self._sample_interarrival()
        if next_arrival <= self.config.simulation_time:
            self._push_event(next_arrival, EVENT_ARRIVAL, station_id)

    def _schedule_slot_tick_if_needed(self, current_time: float) -> None:
        """Planifie le prochain slot_tick si le canal est libre et des stations attendent.
        Le mécanisme de jeton invalide les slot_ticks périmés sans les retirer de la file.
        """
        if self.current_transmission is not None or not self.contenders:
            return  # Canal occupé ou aucune station en attente

        # Respecte la période DIFS post-transmission (contention_open_time)
        candidate = next_slot_boundary(max(current_time, self.contention_open_time), self.config.slot_time)
        if self.scheduled_slot_tick_time is not None and self.scheduled_slot_tick_time <= candidate:
            return  # Slot_tick antérieur déjà planifié

        # Invalide le slot_tick précédent via le jeton
        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = candidate
        self._push_event(candidate, EVENT_SLOT_TICK, -1, self.slot_tick_token)

    def _start_transmission(self, current_time: float, station_ids: list[int]) -> None:
        """Démarre une transmission DATA. Collision si len > 1 (sans SIFS) ; succès avec SIFS. Planifie DATA_END."""
        if not station_ids:
            return

        self.current_transmission = set(station_ids)
        for station_id in station_ids:
            self.contenders.discard(station_id)  # Quitte la phase de contention
            self.stations[station_id].packet.attempts += 1  # type: ignore[union-attr]

        self.total_attempts += len(station_ids)
        if len(station_ids) > 1:
            # Collision : trame corrompue, pas de SIFS
            release_time = current_time + self.config.packet_duration
        else:
            # Succès : SIFS avant ACK implicite
            release_time = current_time + self.config.packet_duration + self.config.sifs

        # Canal occupé — invalide les slot_ticks en attente
        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = None
        self._push_event(release_time, EVENT_DATA_END, -1)

    def _start_rts(self, current_time: float, station_ids: list[int]) -> None:
        """Démarre une émission RTS. Planifie RTS_END ; collision/succès résolus dans _handle_rts_end."""
        if not station_ids:
            return

        self.current_transmission = set(station_ids)
        for station_id in station_ids:
            self.contenders.discard(station_id)  # Quitte la phase de contention (entre en RTS)
            self.stations[station_id].packet.attempts += 1  # type: ignore[union-attr]

        self.total_attempts += len(station_ids)
        rts_end = current_time + self.config.rts_duration
        # Canal occupé durant l'émission RTS — invalide les slot_ticks
        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = None
        self._push_event(rts_end, EVENT_RTS_END, -1)

    def _handle_arrival(self, current_time: float, station_id: int) -> None:
        """Crée le PacketState, incrémente le compteur et amorce la contention (W, K, b)."""
        station = self.stations[station_id]
        if station.packet is not None:
            # Impossible avec la génération interne (paquet précédent non résolu)
            return

        self.generated_packets += 1
        station.packet = PacketState(arrival_time=current_time)
        self._prime_station_for_contention(station_id, current_time)

    def _handle_slot_tick(self, current_time: float) -> None:
        """Décrémente les backoffs des stations actives (hors NAV) et déclenche la transmission si b=0."""
        if self.current_transmission is not None or not self.contenders:
            return  # Canal occupé ou aucune station en contention

        # Stations hors NAV uniquement
        active = [s for s in self.contenders if self.stations[s].nav_until <= current_time]

        # Étape 1 : b=0 déjà atteint — transmission immédiate
        ready_to_send = [station_id for station_id in active if self.stations[station_id].backoff == 0]
        if ready_to_send:
            if self.config.rtscts:
                self._start_rts(current_time, ready_to_send)
            else:
                self._start_transmission(current_time, ready_to_send)
            return

        # Étape 2 : décrémentation
        for station_id in active:
            station = self.stations[station_id]
            if station.backoff > 0:
                station.backoff -= 1

        # Étape 3 : b=0 après décrémentation
        active_after = [station_id for station_id in active if self.stations[station_id].backoff == 0]
        if active_after:
            if self.config.rtscts:
                self._start_rts(current_time, active_after)
            else:
                self._start_transmission(current_time, active_after)
            return

        # Étape 4 : aucune station prête — prochain slot
        self._schedule_slot_tick_if_needed(current_time + self.config.slot_time)
    def _handle_rts_end(self, current_time: float) -> None:
        """Fin RTS : collision → BEB ou abandon ; succès → NAV sur les autres stations + planifie DATA_END."""
        if self.current_transmission is None:
            return

        if len(self.current_transmission) > 1:
            # Collision RTS
            affected_stations = list(self.current_transmission)
            self.collided_packets += len(affected_stations)
            self.current_transmission = None
            self.contention_open_time = current_time + self.config.difs  # Attente DIFS avant re-contention

            for station_id in affected_stations:
                station = self.stations[station_id]
                station.retries += 1
                if station.retries > self.config.kmax:
                    # K_max dépassé : paquet abandonné
                    self.dropped_packets += 1
                    station.packet = None
                    station.contention_window = self.config.wmin
                    station.retries = 0
                    self._schedule_next_arrival(station_id, current_time)
                    continue

                # BEB : W ← min(2W+1, W_max)
                station.contention_window = min(2 * station.contention_window + 1, self.config.wmax)
                station.backoff = self._sample_backoff(station.contention_window)
                self.contenders.add(station_id)

            self._schedule_slot_tick_if_needed(current_time)
            return

        # RTS réussi : une seule station
        station_id = next(iter(self.current_transmission))
        # Chronologie : RTS_end + SIFS + CTS + SIFS + DATA
        data_end_time = current_time + self.config.sifs + self.config.cts_duration + self.config.sifs + self.config.packet_duration

        # NAV : autres stations bloquent leur backoff jusqu'à la fin de la transmission
        for s in range(len(self.stations)):
            if s == station_id:
                continue
            st = self.stations[s]
            if st.packet is not None:
                st.nav_until = data_end_time

        self._push_event(data_end_time, EVENT_DATA_END, -1)

    def _handle_data_end(self, current_time: float) -> None:
        """Fin DATA : succès → enregistre métriques, libère station ; collision → BEB ou abandon."""
        if self.current_transmission is None:
            return

        is_collision = len(self.current_transmission) > 1
        if not is_collision:
            # Transmission réussie
            station_id = next(iter(self.current_transmission))
            station = self.stations[station_id]
            self.successful_packets += 1
            self.successful_bits += self.config.packet_bits
            self.delay_sum += current_time - station.packet.arrival_time  # type: ignore[union-attr]
            station.packet = None
            station.contention_window = self.config.wmin
            station.retries = 0
            self.current_transmission = None
            self.contention_open_time = current_time + self.config.difs  # Prochaine contention après DIFS
            self._schedule_next_arrival(station_id, current_time)
            self._schedule_slot_tick_if_needed(current_time)
            return

        # Collision DATA (rare avec RTS/CTS ; possible sans)
        affected_stations = list(self.current_transmission)
        self.collided_packets += len(affected_stations)
        self.current_transmission = None
        self.contention_open_time = current_time + self.config.difs

        for station_id in affected_stations:
            station = self.stations[station_id]
            station.retries += 1
            if station.retries > self.config.kmax:
                    # K_max dépassé : paquet abandonné
                    self.dropped_packets += 1
                    station.packet = None
                    station.contention_window = self.config.wmin
                    station.retries = 0
                    self._schedule_next_arrival(station_id, current_time)
                    continue

                # BEB : W ← min(2W+1, W_max)
            station.backoff = self._sample_backoff(station.contention_window)
            self.contenders.add(station_id)

        self._schedule_slot_tick_if_needed(current_time)


def run_single_experiment(config: SimulationConfig) -> SimulationResult:
    """Crée et lance un CSMACASimulator ; retourne les métriques."""
    simulator = CSMACASimulator(config)
    return simulator.run()


def average_results(results: list[SimulationResult]) -> SimulationResult:
    """Moyenne des métriques continues, somme des compteurs entiers. Lève ValueError si vide."""
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
    """Balaye N de start à stop par pas step, `runs` répétitions par point.

    Retourne une liste d'ExperimentPoint (moyenne ± σ). Lève ValueError si step/runs <= 0.
    """
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
        throughput_bits_std = pstdev(r.throughput_bits_per_s for r in run_results)
        collision_rate_std = pstdev(r.collision_rate for r in run_results)
        mean_delay_std = pstdev(r.mean_delay_s for r in run_results)
        points.append(
            ExperimentPoint(
                x_value=station_count,
                throughput_packets_per_s=averaged.throughput_packets_per_s,
                throughput_bits_per_s=averaged.throughput_bits_per_s,
                throughput_bits_std=throughput_bits_std,
                collision_rate=averaged.collision_rate,
                collision_rate_std=collision_rate_std,
                mean_delay_s=averaged.mean_delay_s,
                mean_delay_std=mean_delay_std,
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
    """Balaye W_min de start à stop par pas step, `runs` répétitions par point.

    W_max est ajusté à max(wmax, wmin) pour maintenir wmin <= wmax.
    Lève ValueError si step/runs <= 0.
    """
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
        throughput_bits_std = pstdev(r.throughput_bits_per_s for r in run_results)
        collision_rate_std = pstdev(r.collision_rate for r in run_results)
        mean_delay_std = pstdev(r.mean_delay_s for r in run_results)
        points.append(
            ExperimentPoint(
                x_value=wmin,
                throughput_packets_per_s=averaged.throughput_packets_per_s,
                throughput_bits_per_s=averaged.throughput_bits_per_s,
                throughput_bits_std=throughput_bits_std,
                collision_rate=averaged.collision_rate,
                collision_rate_std=collision_rate_std,
                mean_delay_s=averaged.mean_delay_s,
                mean_delay_std=mean_delay_std,
            )
        )

    return points


def sweep_kmax(
    base_config: SimulationConfig,
    start: int,
    stop: int,
    step: int,
    runs: int,
) -> list[ExperimentPoint]:
    """Balaye K_max de start à stop par pas step, `runs` répétitions par point.

    K_max faible → abandons rapides ; K_max élevé → BEB converge, délai plus long.
    Lève ValueError si step/runs <= 0.
    """
    if step <= 0:
        raise ValueError("step must be positive")
    if runs <= 0:
        raise ValueError("runs must be positive")

    points: list[ExperimentPoint] = []
    for kmax in range(start, stop + 1, step):
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
                wmin=base_config.wmin,
                wmax=base_config.wmax,
                kmax=kmax,
                seed=None if base_config.seed is None else base_config.seed + repeat_index + kmax * 1000,
                rtscts=base_config.rtscts,
                rts_duration=base_config.rts_duration,
                cts_duration=base_config.cts_duration,
            )
            run_results.append(run_single_experiment(config))

        averaged = average_results(run_results)
        throughput_bits_std = pstdev(r.throughput_bits_per_s for r in run_results)
        collision_rate_std = pstdev(r.collision_rate for r in run_results)
        mean_delay_std = pstdev(r.mean_delay_s for r in run_results)
        points.append(
            ExperimentPoint(
                x_value=kmax,
                throughput_packets_per_s=averaged.throughput_packets_per_s,
                throughput_bits_per_s=averaged.throughput_bits_per_s,
                throughput_bits_std=throughput_bits_std,
                collision_rate=averaged.collision_rate,
                collision_rate_std=collision_rate_std,
                mean_delay_s=averaged.mean_delay_s,
                mean_delay_std=mean_delay_std,
            )
        )

    return points


def build_arg_parser() -> argparse.ArgumentParser:
    """Construit le parseur CLI (paramètres SimulationConfig + balayages paramétriques)."""
    parser = argparse.ArgumentParser(description="Simulateur à événements discrets du protocole CSMA/CA avec backoff exponentiel binaire")
    # --- Paramètres de la simulation ---
    parser.add_argument("--stations", type=int, default=8, help="Nombre de stations en compétition pour le canal")
    parser.add_argument("--arrival-rate", type=float, default=20.0, help="Taux d'arrivée par station (paquets/s) — processus de renouvellement, non un Poisson pur")
    parser.add_argument("--simulation-time", type=float, default=20.0, help="Horizon de simulation (secondes)")
    parser.add_argument("--packet-bits", type=int, default=12000, help="Taille d'un paquet (bits) — 12 000 bits = 1 500 octets")
    parser.add_argument("--packet-duration", type=float, default=0.001, help="Durée de transmission d'un paquet (secondes)")
    parser.add_argument("--slot-time", type=float, default=20e-6, help="Durée d'un slot de backoff (secondes)")
    parser.add_argument("--difs", type=float, default=50e-6, help="DIFS : délai inter-trames distribué (secondes)")
    parser.add_argument("--sifs", type=float, default=10e-6, help="SIFS : délai inter-trames court (secondes)")
    # --- Paramètres du protocole CSMA/CA ---
    parser.add_argument("--wmin", type=int, default=15, help="Fenêtre de contention minimale W_min")
    parser.add_argument("--wmax", type=int, default=1023, help="Fenêtre de contention maximale W_max")
    parser.add_argument("--kmax", type=int, default=15, help="Nombre maximal de tentatives avant abandon du paquet")
    # --- Contrôle de la simulation ---
    parser.add_argument("--seed", type=int, default=None, help="Graine aléatoire pour la reproductibilité (None = non déterministe)")
    parser.add_argument("--runs", type=int, default=1, help="Nombre de répétitions (résultats moyennés pour réduire la variance)")
    parser.add_argument("--output", type=Path, default=Path("csma_ca_results.svg"), help="Chemin du fichier SVG généré")
    parser.add_argument("--csv", type=Path, default=None, help="Chemin optionnel pour sauvegarder les résultats bruts en CSV")
    # --- Mode RTS/CTS ---
    parser.add_argument("--rtscts", action="store_true", help="Active le mécanisme RTS/CTS avec réservation NAV")
    parser.add_argument("--rts-duration", type=float, default=200e-6, help="Durée d'une trame RTS (secondes)")
    parser.add_argument("--cts-duration", type=float, default=200e-6, help="Durée d'une trame CTS (secondes)")
    parser.add_argument("--title", type=str, default=None, help="Titre personnalisé du graphique SVG (remplace le titre généré automatiquement)")

    # --- Balayages paramétriques (mutuellement exclusifs) ---
    sweep_group = parser.add_mutually_exclusive_group()
    sweep_group.add_argument("--sweep-stations", nargs=3, type=int, metavar=("START", "STOP", "STEP"), help="Balayage du nombre de stations (début fin pas)")
    sweep_group.add_argument("--sweep-wmin", nargs=3, type=int, metavar=("START", "STOP", "STEP"), help="Balayage de la fenêtre de contention minimale W_min (début fin pas)")
    sweep_group.add_argument("--sweep-kmax", nargs=3, type=int, metavar=("START", "STOP", "STEP"), help="Balayage du nombre maximal de tentatives K_max (début fin pas)")

    return parser


def main() -> None:
    """Point d'entrée CLI : parse les arguments, lance la simulation ou le balayage, affiche et sauvegarde."""
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
        plot_points(points, args.title, "Nombre de stations", args.output)
        print(f"Plot saved to {args.output}")
        if args.csv is not None:
            save_csv(points, None, None, args.csv)
            print(f"CSV saved to {args.csv}")
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
        plot_points(points, args.title, "Fenêtre de contention minimale (Wmin)", args.output)
        print(f"Plot saved to {args.output}")
        if args.csv is not None:
            save_csv(points, None, None, args.csv)
            print(f"CSV saved to {args.csv}")
        return

    if args.sweep_kmax is not None:
        start, stop, step = args.sweep_kmax
        points = sweep_kmax(config, start, stop, step, args.runs)
        print("Kmax sweep")
        for point in points:
            print(
                f"Kmax={point.x_value:3d} | throughput={point.throughput_bits_per_s:12.2f} bits/s | "
                f"collision={point.collision_rate * 100:6.2f} % | delay={point.mean_delay_s * 1000:8.4f} ms"
            )
        plot_points(points, args.title, "Nombre maximal de tentatives K_max", args.output)
        print(f"Plot saved to {args.output}")
        if args.csv is not None:
            save_csv(points, None, None, args.csv)
            print(f"CSV saved to {args.csv}")
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
    if args.csv is not None:
        save_csv(None, result, config, args.csv)
        print(f"CSV saved to {args.csv}")


if __name__ == "__main__":  # pragma: no cover
    main()  # pragma: no cover