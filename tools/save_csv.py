"""Sauvegarde CSV des résultats de simulation CSMA/CA."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from csma_ca_sim import ExperimentPoint, SimulationConfig, SimulationResult


def save_csv(
    points: Optional[list[ExperimentPoint]],
    result: Optional[SimulationResult],
    config: Optional[SimulationConfig],
    csv_path: Path,
) -> None:
    """Sauvegarde les résultats bruts dans un fichier CSV.

    Deux modes :
    - sweep (points non vide) : une ligne par valeur du paramètre balayé,
      avec les métriques moyennes et les écarts-types.
    - simulation unique (result/config non nuls) : une seule ligne avec
      tous les compteurs et métriques de SimulationResult.
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if points:
        fieldnames = [
            "x_value",
            "throughput_packets_per_s",
            "throughput_bits_per_s",
            "throughput_bits_std",
            "collision_rate",
            "collision_rate_std",
            "mean_delay_s",
            "mean_delay_std",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for p in points:
                writer.writerow({
                    "x_value": p.x_value,
                    "throughput_packets_per_s": p.throughput_packets_per_s,
                    "throughput_bits_per_s": p.throughput_bits_per_s,
                    "throughput_bits_std": p.throughput_bits_std,
                    "collision_rate": p.collision_rate,
                    "collision_rate_std": p.collision_rate_std,
                    "mean_delay_s": p.mean_delay_s,
                    "mean_delay_std": p.mean_delay_std,
                })
    elif result is not None and config is not None:
        fieldnames = [
            "station_count",
            "arrival_rate",
            "wmin",
            "wmax",
            "kmax",
            "throughput_packets_per_s",
            "throughput_bits_per_s",
            "channel_utilization",
            "offered_load_packets_per_s",
            "collision_rate",
            "mean_delay_s",
            "generated_packets",
            "successful_packets",
            "dropped_packets",
            "total_attempts",
            "collided_packets",
        ]
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow({
                "station_count": config.station_count,
                "arrival_rate": config.arrival_rate,
                "wmin": config.wmin,
                "wmax": config.wmax,
                "kmax": config.kmax,
                "throughput_packets_per_s": result.throughput_packets_per_s,
                "throughput_bits_per_s": result.throughput_bits_per_s,
                "channel_utilization": result.channel_utilization,
                "offered_load_packets_per_s": result.offered_load_packets_per_s,
                "collision_rate": result.collision_rate,
                "mean_delay_s": result.mean_delay_s,
                "generated_packets": result.generated_packets,
                "successful_packets": result.successful_packets,
                "dropped_packets": result.dropped_packets,
                "total_attempts": result.total_attempts,
                "collided_packets": result.collided_packets,
            })
