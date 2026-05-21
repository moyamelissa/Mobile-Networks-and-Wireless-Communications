"""Affichage console des résultats de simulation CSMA/CA."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from csma_ca_sim import SimulationConfig, SimulationResult


def print_result(config: SimulationConfig, result: SimulationResult) -> None:
    """Affiche la configuration et les métriques de simulation dans la console."""
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
