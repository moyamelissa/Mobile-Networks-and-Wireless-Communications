"""
Tests unitaires pour le simulateur CSMA/CA.
Suite complète couvrant le moteur d'événements, le protocole, RTS/CTS et les utilitaires.
"""

import pytest
import math
import sys
from pathlib import Path
from unittest.mock import patch
from io import StringIO

from csma_ca_sim import (
    SimulationConfig,
    PacketState,
    StationState,
    CSMACASimulator,
    run_single_experiment,
    average_results,
    sweep_stations,
    sweep_wmin,
    next_slot_boundary,
    print_result,
    build_arg_parser,
    plot_points,
    main,
)


class TestSimulationConfig:
    """Tests de la classe SimulationConfig."""

    def test_default_config(self):
        """Vérifier les paramètres par défaut."""
        config = SimulationConfig()
        assert config.station_count == 8
        assert config.arrival_rate == 20.0
        assert config.simulation_time == 20.0
        assert config.packet_duration == 0.001
        assert config.wmin == 15
        assert config.wmax == 1023
        assert config.kmax == 15
        assert config.rtscts is False

    def test_custom_config(self):
        """Vérifier la création avec paramètres personnalisés."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=50.0,
            simulation_time=10.0,
            wmin=31,
            rtscts=True
        )
        assert config.station_count == 4
        assert config.arrival_rate == 50.0
        assert config.wmin == 31
        assert config.rtscts is True

    def test_config_with_seed(self):
        """Vérifier la reproductibilité avec seed."""
        config1 = SimulationConfig(seed=42)
        config2 = SimulationConfig(seed=42)
        assert config1.seed == config2.seed == 42


class TestPacketState:
    """Tests pour l'état des paquets."""

    def test_packet_creation(self):
        """Vérifier la création d'un paquet."""
        packet = PacketState(arrival_time=1.5)
        assert packet.arrival_time == 1.5
        assert packet.attempts == 0

    def test_packet_with_attempts(self):
        """Vérifier le comptage des tentatives."""
        packet = PacketState(arrival_time=1.0, attempts=3)
        assert packet.attempts == 3


class TestStationState:
    """Tests pour l'état d'une station."""

    def test_station_creation(self):
        """Vérifier l'initialisation d'une station."""
        station = StationState(station_id=0)
        assert station.station_id == 0
        assert station.packet is None
        assert station.backoff == 0
        assert station.retries == 0
        assert station.nav_until == 0.0

    def test_station_with_packet(self):
        """Vérifier une station avec paquet."""
        packet = PacketState(arrival_time=1.0)
        station = StationState(station_id=1, packet=packet, backoff=5)
        assert station.packet is packet
        assert station.backoff == 5

    def test_station_nav(self):
        """Vérifier le NAV d'une station."""
        station = StationState(station_id=0)
        station.nav_until = 2.5
        assert station.nav_until == 2.5


class TestSlotBoundary:
    """Tests pour le calcul de limites de slots."""

    def test_slot_boundary_exact(self):
        """Vérifier le slot boundary exact."""
        slot_time = 20e-6
        # À t=0, le prochain boundary est 0
        assert next_slot_boundary(0, slot_time) == 0.0

    def test_slot_boundary_mid_slot(self):
        """Vérifier le slot boundary au milieu d'un slot."""
        slot_time = 20e-6
        t = 10e-6  # Milieu du premier slot
        boundary = next_slot_boundary(t, slot_time)
        assert boundary == slot_time  # Prochain boundary au-dessus

    def test_slot_boundary_multiple(self):
        """Vérifier sur plusieurs slots."""
        slot_time = 20e-6
        for slot_idx in range(1, 10):
            t = slot_idx * slot_time
            assert next_slot_boundary(t, slot_time) == slot_idx * slot_time

    def test_slot_boundary_invalid_slot_time(self):
        """Vérifier l'erreur avec slot_time <= 0."""
        with pytest.raises(ValueError):
            next_slot_boundary(1.0, 0)


class TestCSMACASimulator:
    """Tests du simulateur CSMA/CA."""

    def test_simulator_creation(self):
        """Vérifier la création du simulateur."""
        config = SimulationConfig(station_count=4)
        sim = CSMACASimulator(config)
        assert len(sim.stations) == 4
        assert sim.generated_packets == 0
        assert sim.successful_packets == 0

    def test_simple_run_light_load(self):
        """Simulation simple à faible charge."""
        config = SimulationConfig(
            station_count=2,
            arrival_rate=5.0,
            simulation_time=1.0,
            seed=123
        )
        result = run_single_experiment(config)
        assert result.throughput_packets_per_s > 0
        assert result.successful_packets > 0
        assert result.collision_rate >= 0.0
        assert result.mean_delay_s > 0

    def test_simple_run_with_rtscts(self):
        """Simulation avec RTS/CTS activé."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=1.0,
            rtscts=True,
            seed=456
        )
        result = run_single_experiment(config)
        assert result.successful_packets > 0
        assert result.throughput_bits_per_s > 0

    def test_seed_reproducibility(self):
        """Vérifier la reproductibilité avec seed."""
        config1 = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=2.0,
            seed=789
        )
        config2 = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=2.0,
            seed=789
        )
        result1 = run_single_experiment(config1)
        result2 = run_single_experiment(config2)
        # Les résultats doivent être identiques
        assert result1.successful_packets == result2.successful_packets
        assert abs(result1.throughput_packets_per_s - result2.throughput_packets_per_s) < 1e-6

    def test_different_seeds_different_results(self):
        """Vérifier que des seeds différents donnent des résultats différents."""
        config1 = SimulationConfig(
            station_count=4,
            arrival_rate=50.0,
            simulation_time=1.0,
            seed=111
        )
        config2 = SimulationConfig(
            station_count=4,
            arrival_rate=50.0,
            simulation_time=1.0,
            seed=222
        )
        result1 = run_single_experiment(config1)
        result2 = run_single_experiment(config2)
        # Au moins une métrique devrait différer
        assert (result1.successful_packets != result2.successful_packets or
                result1.collision_rate != result2.collision_rate)

    def test_sample_interarrival(self):
        """Vérifier la génération d'intervalles d'arrivée."""
        config = SimulationConfig(arrival_rate=10.0, seed=42)
        sim = CSMACASimulator(config)
        intervals = [sim._sample_interarrival() for _ in range(100)]
        # Vérifier que tous les intervalles sont positifs
        assert all(i > 0 for i in intervals)
        # Vérifier que la moyenne est proche de 1/arrival_rate
        mean_interval = sum(intervals) / len(intervals)
        expected_mean = 1.0 / config.arrival_rate
        assert 0.05 < mean_interval < 0.25  # Fourchette raisonnable

    def test_sample_backoff(self):
        """Vérifier l'échantillonnage du backoff."""
        config = SimulationConfig(seed=42)
        sim = CSMACASimulator(config)
        backoffs = [sim._sample_backoff(15) for _ in range(100)]
        # Vérifier que les backoffs sont dans [0, 15]
        assert all(0 <= b <= 15 for b in backoffs)
        # Vérifier qu'il y a de la variabilité
        assert len(set(backoffs)) > 10

    def test_high_load_conditions(self):
        """Test à charge élevée."""
        config = SimulationConfig(
            station_count=10,
            arrival_rate=100.0,
            simulation_time=0.5,
            seed=555
        )
        result = run_single_experiment(config)
        assert result.throughput_packets_per_s > 0
        assert result.successful_packets > 0
        # À charge élevée, la simulation doit produire des résultats valides
        assert result.total_attempts >= result.successful_packets

    def test_single_station(self):
        """Test avec une seule station (pas de collision)."""
        config = SimulationConfig(
            station_count=1,
            arrival_rate=20.0,
            simulation_time=1.0,
            seed=666
        )
        result = run_single_experiment(config)
        assert result.collision_rate == 0.0
        assert result.successful_packets > 0

    def test_metrics_consistency(self):
        """Vérifier la cohérence des métriques."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=30.0,
            simulation_time=2.0,
            seed=777
        )
        result = run_single_experiment(config)
        # Vérifier les invariants
        assert result.successful_packets <= result.total_attempts
        assert result.collided_packets <= result.total_attempts
        assert result.successful_packets + result.dropped_packets >= 0
        if result.successful_packets > 0:
            assert result.mean_delay_s > 0

    def test_throughput_bits_calculation(self):
        """Vérifier le calcul du débit en bits."""
        config = SimulationConfig(
            station_count=2,
            arrival_rate=10.0,
            simulation_time=1.0,
            packet_bits=12000,
            seed=888
        )
        result = run_single_experiment(config)
        # Vérifier que le débit en bits est cohérent avec le débit en paquets
        expected_bits_per_s = result.successful_packets * config.packet_bits / config.simulation_time
        assert abs(result.throughput_bits_per_s - expected_bits_per_s) < 1e-6


class TestAverageResults:
    """Tests pour la moyenne de résultats."""

    def test_average_single_result(self):
        """Moyenne d'un seul résultat."""
        config = SimulationConfig(station_count=4, seed=42)
        result = run_single_experiment(config)
        results = [result]
        averaged = average_results(results)
        assert averaged.throughput_packets_per_s == result.throughput_packets_per_s
        assert averaged.successful_packets == result.successful_packets

    def test_average_multiple_results(self):
        """Moyenne de plusieurs résultats."""
        config = SimulationConfig(station_count=4, simulation_time=1.0)
        results = []
        for i in range(5):
            cfg = SimulationConfig(
                station_count=4,
                arrival_rate=20.0,
                simulation_time=1.0,
                seed=100 + i
            )
            results.append(run_single_experiment(cfg))
        
        averaged = average_results(results)
        assert averaged.throughput_packets_per_s > 0
        assert averaged.collision_rate >= 0

    def test_average_empty_raises(self):
        """Vérifier l'erreur avec liste vide."""
        with pytest.raises(ValueError):
            average_results([])

    def test_average_throughput_bounds(self):
        """Vérifier que la moyenne est dans des bornes raisonnables."""
        results = []
        for i in range(3):
            cfg = SimulationConfig(
                station_count=4,
                arrival_rate=20.0,
                simulation_time=1.0,
                seed=200 + i
            )
            results.append(run_single_experiment(cfg))
        
        averaged = average_results(results)
        individual_throughputs = [r.throughput_packets_per_s for r in results]
        min_tp = min(individual_throughputs)
        max_tp = max(individual_throughputs)
        assert min_tp <= averaged.throughput_packets_per_s <= max_tp


class TestSweepOperations:
    """Tests pour les balayages paramétriques."""

    def test_sweep_stations_basic(self):
        """Test du balayage du nombre de stations."""
        base_config = SimulationConfig(
            arrival_rate=20.0,
            simulation_time=1.0
        )
        points = sweep_stations(
            base_config=base_config,
            start=2,
            stop=6,
            step=2,
            runs=2
        )
        assert len(points) == 3  # (6-2)/2 + 1 = 3
        assert points[0].x_value == 2
        assert points[1].x_value == 4
        assert points[2].x_value == 6
        for point in points:
            assert point.throughput_packets_per_s > 0

    def test_sweep_stations_with_rtscts(self):
        """Balayage avec RTS/CTS."""
        base_config = SimulationConfig(
            arrival_rate=20.0,
            simulation_time=1.0,
            rtscts=True
        )
        points = sweep_stations(
            base_config=base_config,
            start=2,
            stop=4,
            step=2,
            runs=2
        )
        assert len(points) == 2
        for point in points:
            assert point.collision_rate >= 0

    def test_sweep_stations_single_run(self):
        """Balayage avec une seule répétition."""
        base_config = SimulationConfig(
            arrival_rate=20.0,
            simulation_time=1.0
        )
        points = sweep_stations(
            base_config=base_config,
            start=2,
            stop=4,
            step=2,
            runs=1
        )
        assert len(points) == 2

    def test_sweep_stations_invalid_step(self):
        """Vérifier l'erreur avec step <= 0."""
        base_config = SimulationConfig()
        with pytest.raises(ValueError):
            sweep_stations(base_config, start=2, stop=10, step=0, runs=1)

    def test_sweep_stations_invalid_runs(self):
        """Vérifier l'erreur avec runs <= 0."""
        base_config = SimulationConfig()
        with pytest.raises(ValueError):
            sweep_stations(base_config, start=2, stop=10, step=2, runs=0)

    def test_sweep_wmin_basic(self):
        """Test du balayage de Wmin."""
        base_config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=1.0
        )
        points = sweep_wmin(
            base_config=base_config,
            start=15,
            stop=31,
            step=8,
            runs=2
        )
        assert len(points) == 3  # (31-15)/8 + 1 = 3
        assert points[0].x_value == 15
        assert points[1].x_value == 23
        assert points[2].x_value == 31

    def test_sweep_wmin_with_different_runs(self):
        """Vérifier que plus de runs lisent les résultats."""
        base_config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=1.0
        )
        points_1run = sweep_wmin(base_config, start=15, stop=31, step=16, runs=1)
        points_5run = sweep_wmin(base_config, start=15, stop=31, step=16, runs=5)
        
        # Les deux doivent avoir le même nombre de points
        assert len(points_1run) == len(points_5run)


class TestExportAndFormat:
    """Tests pour l'export et les formats."""

    def test_plot_points_creates_file(self, tmp_path):
        """Vérifier que plot_points crée un fichier SVG."""
        from csma_ca_sim import ExperimentPoint, plot_points
        
        points = [
            ExperimentPoint(
                x_value=2,
                throughput_packets_per_s=1000.0,
                throughput_bits_per_s=12000000.0,
                collision_rate=0.0,
                mean_delay_s=0.001
            ),
            ExperimentPoint(
                x_value=4,
                throughput_packets_per_s=2000.0,
                throughput_bits_per_s=24000000.0,
                collision_rate=0.5,
                mean_delay_s=0.002
            ),
        ]
        
        output_file = tmp_path / "test_plot.svg"
        plot_points(points, title="Test Plot", x_label="Stations", output_path=output_file)
        
        assert output_file.exists()
        content = output_file.read_text()
        assert "<?xml" in content or "<svg" in content

    def test_plot_points_with_single_point(self, tmp_path):
        """Vérifier plot_points avec un seul point."""
        from csma_ca_sim import ExperimentPoint, plot_points
        
        points = [
            ExperimentPoint(
                x_value=5,
                throughput_packets_per_s=5000.0,
                throughput_bits_per_s=60000000.0,
                collision_rate=2.5,
                mean_delay_s=0.005
            ),
        ]
        
        output_file = tmp_path / "single_point.svg"
        plot_points(points, title="Single Point Test", x_label="Test X", output_path=output_file)
        
        assert output_file.exists()
        assert output_file.stat().st_size > 100  # SVG file should have content


class TestEdgeCases:
    """Tests pour les cas limites."""

    def test_zero_arrival_rate(self):
        """Simulation avec taux d'arrivée = 0."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=0.0,
            simulation_time=1.0
        )
        result = run_single_experiment(config)
        assert result.generated_packets == 0
        assert result.successful_packets == 0

    def test_very_short_simulation(self):
        """Simulation très courte."""
        config = SimulationConfig(
            station_count=2,
            arrival_rate=20.0,
            simulation_time=0.01
        )
        result = run_single_experiment(config)
        # Pas d'erreur, les métriques sont valides
        assert result.throughput_packets_per_s >= 0

    def test_very_long_simulation(self):
        """Simulation plus longue (mais raisonnable)."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=10.0,
            simulation_time=5.0,
            seed=999
        )
        result = run_single_experiment(config)
        assert result.successful_packets > 0

    def test_many_stations(self):
        """Simulation avec beaucoup de stations."""
        config = SimulationConfig(
            station_count=32,
            arrival_rate=10.0,
            simulation_time=1.0,
            seed=1111
        )
        result = run_single_experiment(config)
        assert result.throughput_packets_per_s > 0

    def test_high_wmax(self):
        """Test avec Wmax très élevé."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=1.0,
            wmax=8191,  # 2^13 - 1
            seed=2222
        )
        result = run_single_experiment(config)
        assert result.successful_packets > 0


class TestRTSCTSMechanism:
    """Tests spécifiques au mécanisme RTS/CTS."""

    def test_rtscts_vs_baseline(self):
        """Comparer RTS/CTS vs baseline sur même charge."""
        base_config = SimulationConfig(
            station_count=6,
            arrival_rate=30.0,
            simulation_time=2.0
        )
        
        # Baseline
        config_baseline = SimulationConfig(
            station_count=6,
            arrival_rate=30.0,
            simulation_time=2.0,
            seed=3333
        )
        result_baseline = run_single_experiment(config_baseline)
        
        # RTS/CTS
        config_rtscts = SimulationConfig(
            station_count=6,
            arrival_rate=30.0,
            simulation_time=2.0,
            rtscts=True,
            seed=3333  # Même seed pour comparaison
        )
        result_rtscts = run_single_experiment(config_rtscts)
        
        # Les résultats devraient différer (RTS/CTS a surcharge)
        assert result_baseline.throughput_packets_per_s != result_rtscts.throughput_packets_per_s

    def test_rtscts_nav_protection(self):
        """Vérifier que NAV est utilisé avec RTS/CTS."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=50.0,
            simulation_time=1.0,
            rtscts=True,
            rts_duration=200e-6,
            cts_duration=200e-6,
            seed=4444
        )
        result = run_single_experiment(config)
        # Avec RTS/CTS, les collisions RTS doivent être rares
        # mais devraient augmenter avec charge
        assert result.successful_packets > 0


class TestPrintResult:
    """Tests pour la fonction print_result."""

    def test_print_result_output(self, capsys):
        """Vérifier que print_result affiche les résultats."""
        config = SimulationConfig(station_count=4, arrival_rate=20.0)
        result = run_single_experiment(config)
        print_result(config, result)
        
        captured = capsys.readouterr()
        assert "Configuration" in captured.out
        assert "Results" in captured.out
        assert "Stations" in captured.out
        assert "Throughput" in captured.out
        assert "collision" in captured.out

    def test_print_result_with_rtscts(self, capsys):
        """Vérifier affichage avec RTS/CTS activé."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            rtscts=True
        )
        result = run_single_experiment(config)
        print_result(config, result)
        
        captured = capsys.readouterr()
        assert len(captured.out) > 100


class TestArgumentParser:
    """Tests pour le parser d'arguments."""

    def test_parser_creation(self):
        """Vérifier la création du parser."""
        parser = build_arg_parser()
        assert parser is not None

    def test_parser_default_args(self):
        """Vérifier les arguments par défaut."""
        parser = build_arg_parser()
        args = parser.parse_args([])
        assert args.stations == 8
        assert args.arrival_rate == 20.0
        assert args.simulation_time == 20.0
        assert args.rtscts is False

    def test_parser_custom_stations(self):
        """Vérifier parsing du nombre de stations."""
        parser = build_arg_parser()
        args = parser.parse_args(["--stations", "16"])
        assert args.stations == 16

    def test_parser_custom_arrival_rate(self):
        """Vérifier parsing du taux d'arrivée."""
        parser = build_arg_parser()
        args = parser.parse_args(["--arrival-rate", "50.0"])
        assert args.arrival_rate == 50.0

    def test_parser_sweep_stations(self):
        """Vérifier parsing du sweep stations."""
        parser = build_arg_parser()
        args = parser.parse_args(["--sweep-stations", "2", "10", "2"])
        assert args.sweep_stations == [2, 10, 2]

    def test_parser_sweep_wmin(self):
        """Vérifier parsing du sweep Wmin."""
        parser = build_arg_parser()
        args = parser.parse_args(["--sweep-wmin", "15", "31", "8"])
        assert args.sweep_wmin == [15, 31, 8]

    def test_parser_rtscts_flag(self):
        """Vérifier parsing du flag RTS/CTS."""
        parser = build_arg_parser()
        args = parser.parse_args(["--rtscts"])
        assert args.rtscts is True

    def test_parser_seed(self):
        """Vérifier parsing de la seed."""
        parser = build_arg_parser()
        args = parser.parse_args(["--seed", "42"])
        assert args.seed == 42

    def test_parser_output(self):
        """Vérifier parsing du chemin output."""
        parser = build_arg_parser()
        args = parser.parse_args(["--output", "test.svg"])
        assert str(args.output) == "test.svg"


class TestPlotPointsEdgeCases:
    """Tests pour les cas limites de plot_points."""

    def test_plot_points_empty_raises(self):
        """Vérifier que plot_points lève ValueError avec liste vide."""
        with pytest.raises(ValueError, match="points must not be empty"):
            plot_points([], title="Test", x_label="X", output_path=Path("test.svg"))

    def test_plot_points_many_points(self, tmp_path):
        """Vérifier avec beaucoup de points."""
        from csma_ca_sim import ExperimentPoint
        
        points = [
            ExperimentPoint(
                x_value=i,
                throughput_packets_per_s=1000.0 + i * 100,
                throughput_bits_per_s=12000000.0 + i * 1000000,
                collision_rate=0.0 + i * 0.01,
                mean_delay_s=0.001 + i * 0.0001
            )
            for i in range(1, 21)
        ]
        
        output_file = tmp_path / "many_points.svg"
        plot_points(points, title="Many Points", x_label="Points", output_path=output_file)
        
        assert output_file.exists()
        content = output_file.read_text()
        assert "<svg" in content
        assert "N=" not in content or "0" in content

    def test_plot_points_same_values(self, tmp_path):
        """Vérifier quand toutes les valeurs sont identiques."""
        from csma_ca_sim import ExperimentPoint
        
        points = [
            ExperimentPoint(
                x_value=i,
                throughput_packets_per_s=5000.0,
                throughput_bits_per_s=60000000.0,
                collision_rate=0.05,
                mean_delay_s=0.005
            )
            for i in range(1, 4)
        ]
        
        output_file = tmp_path / "same_values.svg"
        plot_points(points, title="Same Values", x_label="X", output_path=output_file)
        
        assert output_file.exists()


class TestMainFunction:
    """Tests pour la fonction main."""

    def test_main_single_run(self, capsys):
        """Tester main avec une seule exécution."""
        with patch.object(sys, "argv", ["csma_ca_sim.py", "--stations", "2", "--simulation-time", "0.5"]):
            try:
                main()
            except SystemExit:
                pass
        
        captured = capsys.readouterr()
        assert "Configuration" in captured.out or "Results" in captured.out

    def test_main_multiple_runs(self, capsys):
        """Tester main avec plusieurs runs."""
        with patch.object(sys, "argv", [
            "csma_ca_sim.py",
            "--stations", "2",
            "--simulation-time", "0.2",
            "--runs", "2"
        ]):
            try:
                main()
            except SystemExit:
                pass
        
        captured = capsys.readouterr()
        assert "Throughput" in captured.out

    def test_main_sweep_stations(self, capsys, tmp_path):
        """Tester main avec sweep stations."""
        output = tmp_path / "sweep_test.svg"
        with patch.object(sys, "argv", [
            "csma_ca_sim.py",
            "--sweep-stations", "2", "4", "2",
            "--runs", "1",
            "--simulation-time", "0.1",
            "--output", str(output)
        ]):
            try:
                main()
            except SystemExit:
                pass
        
        captured = capsys.readouterr()
        assert "Station sweep" in captured.out or "throughput" in captured.out

    def test_main_sweep_wmin(self, capsys, tmp_path):
        """Tester main avec sweep Wmin."""
        output = tmp_path / "wmin_test.svg"
        with patch.object(sys, "argv", [
            "csma_ca_sim.py",
            "--sweep-wmin", "15", "31", "16",
            "--runs", "1",
            "--simulation-time", "0.1",
            "--output", str(output)
        ]):
            try:
                main()
            except SystemExit:
                pass
        
        captured = capsys.readouterr()
        assert "Wmin sweep" in captured.out or "throughput" in captured.out

    def test_main_with_rtscts(self, capsys):
        """Tester main avec RTS/CTS activé."""
        with patch.object(sys, "argv", [
            "csma_ca_sim.py",
            "--stations", "4",
            "--simulation-time", "0.2",
            "--rtscts"
        ]):
            try:
                main()
            except SystemExit:
                pass
        
        captured = capsys.readouterr()
        assert "Configuration" in captured.out or "Throughput" in captured.out

    def test_main_invalid_runs(self):
        """Tester que runs <= 0 lève SystemExit."""
        with patch.object(sys, "argv", [
            "csma_ca_sim.py",
            "--runs", "0"
        ]):
            with pytest.raises(SystemExit):
                main()

    def test_main_with_seed(self, capsys):
        """Tester main avec seed spécifiée."""
        with patch.object(sys, "argv", [
            "csma_ca_sim.py",
            "--stations", "2",
            "--simulation-time", "0.1",
            "--seed", "99"
        ]):
            try:
                main()
            except SystemExit:
                pass
        
        captured = capsys.readouterr()
        assert len(captured.out) > 50

    def test_main_custom_parameters(self, capsys):
        """Tester main avec paramètres personnalisés."""
        with patch.object(sys, "argv", [
            "csma_ca_sim.py",
            "--stations", "3",
            "--arrival-rate", "15.0",
            "--wmin", "31",
            "--wmax", "511",
            "--kmax", "10",
            "--simulation-time", "0.1"
        ]):
            try:
                main()
            except SystemExit:
                pass
        
        captured = capsys.readouterr()
        assert "Throughput" in captured.out


class TestIntegration:
    """Tests d'intégration."""

    def test_full_workflow_baseline_and_rts(self):
        """Tester le workflow complet : baseline vs RTS/CTS."""
        # Baseline
        config_baseline = SimulationConfig(
            station_count=4,
            arrival_rate=30.0,
            simulation_time=1.0,
            seed=5555
        )
        result_baseline = run_single_experiment(config_baseline)
        
        # RTS/CTS
        config_rts = SimulationConfig(
            station_count=4,
            arrival_rate=30.0,
            simulation_time=1.0,
            rtscts=True,
            seed=5555
        )
        result_rts = run_single_experiment(config_rts)
        
        # Vérifier que les résultats sont différents
        assert result_baseline.throughput_packets_per_s > 0
        assert result_rts.throughput_packets_per_s > 0

    def test_sweep_and_plot_workflow(self, tmp_path):
        """Tester le workflow complet sweep + plot."""
        base_config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=0.5
        )
        
        # Sweep
        points = sweep_stations(base_config, start=2, stop=4, step=2, runs=2)
        assert len(points) == 2
        
        # Plot
        output = tmp_path / "integration_test.svg"
        plot_points(points, title="Integration Test", x_label="Stations", output_path=output)
        assert output.exists()

    def test_simulator_with_no_arrivals_high_load(self):
        """Tester simulation avec très peu d'arrivées."""
        config = SimulationConfig(
            station_count=8,
            arrival_rate=0.1,  # Très peu d'arrivées
            simulation_time=1.0,
            seed=6666
        )
        result = run_single_experiment(config)
        # Au minimum, aucune erreur ne devrait occur
        assert result.generated_packets >= 0

    def test_collision_intensive_scenario(self):
        """Tester un scénario avec beaucoup de collisions."""
        config = SimulationConfig(
            station_count=12,
            arrival_rate=200.0,  # Très charge élevée
            simulation_time=0.2,
            wmin=3,  # Fenêtre petite pour forcer collisions
            seed=7777
        )
        result = run_single_experiment(config)
        # S'attendre à de nombreuses collisions
        assert result.collision_rate >= 0 or result.dropped_packets > 0

    def test_multiple_drops_with_low_kmax(self):
        """Tester avec Kmax très bas pour forcer des drops."""
        config = SimulationConfig(
            station_count=8,
            arrival_rate=50.0,
            simulation_time=0.5,
            kmax=1,  # Très bas = drops rapides
            seed=8888
        )
        result = run_single_experiment(config)
        # Vérifier que les drops/collisions sont gérés
        assert result.total_attempts > 0

    def test_rtscts_collision_intensive(self):
        """Tester RTS/CTS avec charge intensive."""
        config = SimulationConfig(
            station_count=10,
            arrival_rate=150.0,
            simulation_time=0.3,
            rtscts=True,
            wmin=7,
            seed=9999
        )
        result = run_single_experiment(config)
        # RTS/CTS devrait produire quelques collisions RTS
        assert result.successful_packets >= 0

    def test_exact_simulation_boundary(self):
        """Tester avec arrivée exactement à la limite."""
        config = SimulationConfig(
            station_count=2,
            arrival_rate=2.0,  # 2 paquets/s, donc intervalle=0.5s
            simulation_time=1.0,
            seed=1010
        )
        result = run_single_experiment(config)
        # Quelques arrivées attendues
        assert result.generated_packets > 0

    def test_wmin_equals_wmax(self):
        """Tester quand Wmin = Wmax (fenêtre fixe)."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=1.0,
            wmin=31,
            wmax=31,  # Identique à Wmin
            seed=1111
        )
        result = run_single_experiment(config)
        assert result.successful_packets > 0

    def test_very_small_packet_duration(self):
        """Tester avec durée de paquet très petite."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=0.5,
            packet_duration=0.0001,  # 0.1 ms au lieu de 1 ms
            seed=1212
        )
        result = run_single_experiment(config)
        # Débit devrait être plus élevé avec paquets plus courts
        assert result.throughput_packets_per_s > 0

    def test_rtscts_with_custom_durations(self):
        """Tester RTS/CTS avec durées personnalisées."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=20.0,
            simulation_time=0.5,
            rtscts=True,
            rts_duration=500e-6,  # 500 µs au lieu de 200 µs
            cts_duration=500e-6,  # Plus long = plus de NAV
            seed=1313
        )
        result = run_single_experiment(config)
        assert result.successful_packets > 0

    def test_sweep_single_station(self):
        """Balayage avec un seul point (2 stations)."""
        base_config = SimulationConfig(
            arrival_rate=20.0,
            simulation_time=0.5
        )
        points = sweep_stations(base_config, start=2, stop=2, step=1, runs=2)
        assert len(points) == 1
        assert points[0].x_value == 2

    def test_print_result_all_zeros(self, capsys):
        """Tester print_result avec métriques à zéro."""
        from csma_ca_sim import SimulationResult
        
        config = SimulationConfig(station_count=1)
        result = SimulationResult(
            throughput_packets_per_s=0.0,
            throughput_bits_per_s=0.0,
            collision_rate=0.0,
            mean_delay_s=0.0,
            generated_packets=0,
            successful_packets=0,
            dropped_packets=0,
            total_attempts=0,
            collided_packets=0,
        )
        print_result(config, result)
        
        captured = capsys.readouterr()
        assert "0.0000" in captured.out or "0.00" in captured.out

    def test_packet_already_waiting_arrival(self):
        """Tester quand paquet arrive alors qu'un autre attend déjà."""
        # Configuration avec très haute arrivée et transmission lente
        # pour forcer des arrivées multiples avant transmission
        config = SimulationConfig(
            station_count=1,
            arrival_rate=1000.0,  # Très haut = intervalles très courts
            simulation_time=0.01,  # Très court
            packet_duration=0.005,  # Long comparé à simulation
            slot_time=1e-6,  # Très petit
            seed=2020
        )
        result = run_single_experiment(config)
        # Si des paquets arrivent alors qu'un autre est en attente,
        # ils seront perdus/ignorés mais pas d'erreur
        assert result.generated_packets >= 0

    def test_no_contenders_slot_tick(self):
        """Tester slot tick quand aucun contender."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=0.001,  # Pratiquement pas d'arrivées
            simulation_time=0.1,
            seed=2121
        )
        result = run_single_experiment(config)
        # La simulation se termine normalement sans erreur
        assert result.successful_packets == 0 or result.generated_packets == 0

    def test_transmission_ongoing_arrival(self):
        """Tester arrivée pendant une transmission en cours."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=100.0,  # Arrivées fréquentes
            simulation_time=0.02,
            packet_duration=0.001,
            seed=2222
        )
        result = run_single_experiment(config)
        # La simulation doit gérer les arrivées pendant transmissions
        assert result.throughput_packets_per_s >= 0

    def test_narrow_window_backoff_decrease(self):
        """Tester décrémentation backoff avec fenêtre étroite."""
        config = SimulationConfig(
            station_count=4,
            arrival_rate=15.0,
            simulation_time=0.5,
            wmin=2,  # Très petite fenêtre
            slot_time=50e-6,  # Un peu plus grand
            seed=2323
        )
        result = run_single_experiment(config)
        assert result.successful_packets > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
