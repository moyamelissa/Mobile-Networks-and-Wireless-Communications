"""Affichage console des résultats de simulation CSMA/CA."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from csma_ca_sim import SimulationConfig, SimulationResult


def print_result(config: SimulationConfig, result: SimulationResult) -> None:
    """Affiche la configuration et les métriques de simulation dans la console."""
    print("Configuration")
    print(f"  Stations                    : {config.station_count}")
    print(f"  Taux d'arrivée / station    : {config.arrival_rate:.4f} paquets/s")
    print(f"  Durée de simulation         : {config.simulation_time:.4f} s")
    print(f"  Durée de transmission       : {config.packet_duration:.6f} s")
    print(f"  Taille du paquet            : {config.packet_bits} bits")
    print(f"  Durée d'un slot             : {config.slot_time:.8f} s")
    print(f"  DIFS / SIFS                 : {config.difs:.8f} s / {config.sifs:.8f} s")
    print(f"  Wmin / Wmax / Kmax          : {config.wmin} / {config.wmax} / {config.kmax}")
    print()
    print("Résultats")
    print(f"  Débit                       : {result.throughput_packets_per_s:.4f} paquets/s")
    print(f"  Débit binaire               : {result.throughput_bits_per_s:.4f} bits/s")
    print(f"  Utilisation du canal        : {result.channel_utilization * 100:.2f} %")
    print(f"  Charge offerte              : {result.offered_load_packets_per_s:.4f} paquets/s")
    print(f"  Taux de collision moyen     : {result.collision_rate * 100:.2f} %")
    print(f"  Délai moyen de transmission : {result.mean_delay_s * 1000:.4f} ms")
    print(f"  Paquets générés             : {result.generated_packets}")
    print(f"  Paquets transmis            : {result.successful_packets}")
    print(f"  Paquets abandonnés          : {result.dropped_packets}")
    print(f"  Tentatives totales          : {result.total_attempts}")
    print(f"  Tentatives en collision     : {result.collided_packets}")
