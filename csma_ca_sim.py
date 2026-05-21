"""Simulateur à événements discrets du protocole CSMA/CA.

Ce module implémente la logique MAC du protocole CSMA/CA (Carrier Sense Multiple
Access with Collision Avoidance) tel que défini par le standard IEEE 802.11.
Il supporte le mode de base et une extension RTS/CTS avec mécanisme NAV.

Usage typique (ligne de commande) :
    python csma_ca_sim.py --stations 8 --arrival-rate 20 --simulation-time 20
    python csma_ca_sim.py --sweep-stations 2 20 2 --runs 3 --output resultats.svg

Structure principale :
    SimulationConfig  — paramètres de la simulation (fenêtres, temporisations, etc.)
    StationState      — état MAC d'une station individuelle
    CSMACASimulator   — moteur à événements discrets
    run_single_experiment / average_results / sweep_* — utilitaires d'expérimentation
    plot_points       — génération de graphiques SVG
    main              — point d'entrée en ligne de commande
"""
from __future__ import annotations

import argparse
import csv
import heapq
import math
import random
from dataclasses import dataclass as _dataclass

# Le paramètre `slots` de `dataclass` n'existe qu'à partir de Python 3.10.
# Cette compatibilité permet de garder un seul code source pour la CI en 3.8/3.9
# et les environnements locaux plus récents ; si `slots` n'est pas disponible,
# on le retire simplement.
_DATACLASS_SUPPORTS_SLOTS = True
try:
    # On crée une dataclass de test pour savoir si l'interpréteur gère `slots`.
    _dataclass(slots=True)(type("_X", (), {}))
except TypeError:  # pragma: no cover
    _DATACLASS_SUPPORTS_SLOTS = False  # pragma: no cover


def dataclass_compat(**kwargs):
    """Crée un décorateur @dataclass compatible Python 3.8+ en retirant `slots` si nécessaire."""
    if not _DATACLASS_SUPPORTS_SLOTS and "slots" in kwargs:
        kwargs = {k: v for k, v in kwargs.items() if k != "slots"}
    return _dataclass(**kwargs)
from pathlib import Path
from statistics import mean, pstdev
from xml.sax.saxutils import escape
from typing import Optional


# ---------------------------------------------------------------------------
# Constantes — types d'événements du moteur de simulation
# ---------------------------------------------------------------------------
# Chaque constante identifie un type d'événement inséré dans la file de priorité.
# Utiliser des constantes nommées (plutôt que des entiers) rend le code lisible
# et facilite le débogage.
EVENT_ARRIVAL  = "arrival"    # Arrivée d'un nouveau paquet dans une station
EVENT_SLOT_TICK = "slot_tick" # Déclenchement d'un slot de backoff
EVENT_RTS_END  = "rts_end"    # Fin de l'émission d'une trame RTS (mode RTS/CTS)
EVENT_DATA_END = "data_end"   # Fin de l'émission d'une trame de données


def next_slot_boundary(time_value: float, slot_time: float) -> float:
    """Retourne le prochain instant aligné sur une borne de slot.

    Le décalage de 1e-15 s évite qu'un instant déjà exactement aligné
    (flottant) soit arrondi au slot suivant à cause des erreurs de précision.

    Args:
        time_value: Instant courant (en secondes).
        slot_time:  Durée d'un slot (en secondes, doit être > 0).

    Returns:
        Le plus petit multiple de slot_time supérieur ou égal à time_value.

    Raises:
        ValueError: Si slot_time <= 0.
    """
    if slot_time <= 0:
        raise ValueError("slot_time must be positive")
    scaled = (time_value - 1e-15) / slot_time
    slot_index = math.ceil(scaled)
    return max(0.0, slot_index * slot_time)


@dataclass_compat(slots=True)
class SimulationConfig:
    """Paramètres globaux de la simulation.

    Regroupe toutes les hypothèses MAC et temporelles qui pilotent le modèle.
    Les valeurs par défaut correspondent au standard IEEE 802.11b.
    """
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
    """Représente une trame en attente de transmission dans une station.

    Une instance est créée à chaque arrivée de paquet et détruite après
    transmission réussie ou abandon (K > K_max).
    """
    arrival_time: float  # Instant de génération du paquet — sert à calculer le délai moyen
    attempts: int = 0   # Nombre de tentatives de transmission déjà effectuées pour ce paquet


@dataclass_compat(slots=True)
class StationState:
    """État MAC d'une station individuelle.

    Le sujet impose qu'une station MAC ne garde qu'une seule trame à la fois :
    `packet` est None quand la station est inactive, ou contient l'unique trame
    en cours de transmission (attente de succès ou d'abandon).
    `contention_window`, `backoff` et `retries` pilotent l'algorithme BEB.
    `nav_until` matérialise la réservation du médium par le mécanisme NAV (RTS/CTS).
    """
    station_id: int                      # Identifiant unique de la station (index dans la liste)
    packet: Optional[PacketState] = None # Trame active (None = station inactive)
    contention_window: int = 0           # Fenêtre de contention courante W ∈ [W_min, W_max]
    backoff: int = 0                     # Compteur de backoff courant b ∈ [0, W]
    retries: int = 0                     # Nombre de tentatives échouées pour la trame courante (K)
    nav_until: float = 0.0               # Instant jusqu'auquel le médium est réservé (NAV)


@dataclass_compat(slots=True)
class SimulationResult:
    """Résultats agrégés produits à la fin d'une simulation.

    Retourné par run_single_experiment() et average_results().
    Utilisé pour l'affichage console (print_result) et les graphiques (plot_points).
    """
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
    """Un point de courbe expérimentale : une valeur de paramètre et les métriques associées.

    Produit par sweep_stations(), sweep_wmin() et sweep_kmax() ; consommé par plot_points().
    Les champs *_std contiennent l'écart-type calculé sur les `runs` répétitions,
    permettant de tracer des barres d'erreur (±1σ) sur les graphiques.
    """
    x_value: int                       # Valeur du paramètre balayé (ex. nombre de stations)
    throughput_packets_per_s: float    # Débit moyen (paquets/s)
    throughput_bits_per_s: float       # Débit binaire moyen (bits/s)
    collision_rate: float              # Taux de collision moyen
    mean_delay_s: float                # Délai moyen de transmission (secondes)
    throughput_bits_std: float = 0.0   # Écart-type du débit binaire entre les répétitions (bits/s)
    collision_rate_std: float = 0.0    # Écart-type du taux de collision entre les répétitions
    mean_delay_std: float = 0.0        # Écart-type du délai moyen entre les répétitions (secondes)


class CSMACASimulator:
    """Moteur à événements discrets du protocole CSMA/CA.

    Gère la file de priorité des événements, l'état de chaque station,
    l'état global du canal et les compteurs de métriques.
    Instancier puis appeler run() pour obtenir un SimulationResult.
    """

    def __init__(self, config: SimulationConfig):
        """Initialise le simulateur avec la configuration donnée.

        Args:
            config: Paramètres de la simulation (voir SimulationConfig).
        """
        self.config = config
        # Générateur aléatoire isolé — garantit la reproductibilité via config.seed.
        self.random = random.Random(config.seed)
        # Une instance StationState par station participant à la contention.
        self.stations = [StationState(station_id=index) for index in range(config.station_count)]

        # File de priorité (min-heap) : chaque entrée est un tuple
        # (temps, sequence, type_événement, station_id, jeton).
        # Le numéro de séquence monotone brise les égalités de temps de façon déterministe.
        self.event_queue: list[tuple[float, int, str, int, Optional[int]]] = []
        self.sequence = 0  # Compteur global pour le numéro de séquence des événements

        # Ensemble des identifiants de stations actuellement en phase de backoff actif.
        self.contenders: set[int] = set()
        # Ensemble des stations engagées dans la transmission en cours (None si canal libre).
        # Si len > 1, une collision est en cours.
        self.current_transmission: Optional[set[int]] = None
        # Instant à partir duquel la contention peut reprendre (après DIFS).
        self.contention_open_time = 0.0
        # Instant planifié pour le prochain slot_tick (None si aucun planifié).
        self.scheduled_slot_tick_time: Optional[float] = None
        # Jeton permettant d'invalider les événements slot_tick périmés sans les retirer de la file.
        self.slot_tick_token = 0

        # Compteurs de métriques — cumulés au fil des événements, agrégés dans run().
        self.generated_packets = 0   # Paquets générés par les stations
        self.successful_packets = 0  # Paquets transmis avec succès
        self.dropped_packets = 0     # Paquets abandonnés après K_max tentatives
        self.total_attempts = 0      # Tentatives de transmission totales
        self.collided_packets = 0    # Tentatives ayant abouti à une collision
        self.successful_bits = 0     # Bits utiles transmis (pour le débit binaire)
        self.delay_sum = 0.0         # Somme des délais individuels (pour la moyenne)

    def run(self) -> SimulationResult:
        """Lance la simulation et retourne les métriques agrégées.

        1. Planifie la première arrivée de paquet pour chaque station.
        2. Traite les événements en ordre chronologique jusqu'à épuisement de la file.
        3. Calcule et retourne les métriques de performance.

        Returns:
            SimulationResult contenant débit, taux de collision, délai moyen, etc.
        """
        # Planification des premières arrivées : chaque station commence avec
        # un premier paquet tiré selon la loi exponentielle de paramètre arrival_rate.
        for station_id in range(self.config.station_count):
            first_arrival = self._sample_interarrival()
            if first_arrival <= self.config.simulation_time:
                self._push_event(first_arrival, EVENT_ARRIVAL, station_id)

        # Boucle principale : dépile et traite chaque événement en ordre chronologique.
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

        # --- Calcul des métriques finales ---
        # Débit en paquets et en bits : rapporte les succès à la durée de simulation.
        throughput_packets_per_s = self.successful_packets / self.config.simulation_time if self.config.simulation_time > 0 else 0.0
        throughput_bits_per_s = self.successful_bits / self.config.simulation_time if self.config.simulation_time > 0 else 0.0
        # Utilisation du canal : fraction du temps effectivement occupé par des données utiles.
        channel_utilization = (
            (self.successful_packets * self.config.packet_duration) / self.config.simulation_time
            if self.config.simulation_time > 0 and self.config.packet_duration > 0
            else 0.0
        )
        # Charge offerte : paquets générés par unité de temps (inclut succès + abandons).
        offered_load_packets_per_s = self.generated_packets / self.config.simulation_time if self.config.simulation_time > 0 else 0.0
        # Taux de collision : proportion des tentatives ayant abouti à un conflit.
        collision_rate = self.collided_packets / self.total_attempts if self.total_attempts > 0 else 0.0
        # Délai moyen : moyenne des délais individuels (génération → succès).
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
        """Insère un événement dans la file de priorité.

        Le numéro de séquence monotone garantit un ordre stable lorsque deux
        événements partagent le même instant (tri secondaire déterministe).
        """
        self.sequence += 1
        heapq.heappush(self.event_queue, (time_value, self.sequence, event_type, station_id, token))

    def _sample_interarrival(self) -> float:
        """Tire un intervalle inter-arrivée selon la loi exponentielle de paramètre arrival_rate.

        Les inter-arrivées sont exponentielles de paramètre λ = arrival_rate, mais comme une station
        suspend la génération pendant le traitement d'un paquet, le processus d'arrivée global
        est un processus de renouvellement — non un Poisson pur — conformément à l'hypothèse du sujet.
        Retourne math.inf si arrival_rate <= 0, ce qui désactive les arrivées.
        """
        if self.config.arrival_rate <= 0:
            return math.inf
        return self.random.expovariate(self.config.arrival_rate)

    def _sample_backoff(self, contention_window: int) -> int:
        """Tire un compteur de backoff b uniformément dans [0, contention_window].

        Conforme à la règle IEEE 802.11 : b = U[0, W] où W est la fenêtre courante.
        """
        return self.random.randint(0, contention_window)

    def _prime_station_for_contention(self, station_id: int, current_time: float) -> None:
        """Initialise les compteurs d'une station et l'enregistre comme contendante.

        Appelé à l'arrivée d'un nouveau paquet. Réinitialise W à W_min, K à 0,
        tire un backoff initial et déclenche le prochain slot_tick si le canal est libre.
        """
        station = self.stations[station_id]
        if station.packet is None:
            return  # Sécurité : ne rien faire si la station n'a pas de paquet actif

        # Initialisation conforme à IEEE 802.11 : W_min et K=0 pour le premier essai.
        station.contention_window = self.config.wmin
        station.retries = 0
        station.backoff = self._sample_backoff(station.contention_window)
        self.contenders.add(station_id)

        # Déclenche le slot_tick seulement si aucune transmission n'est en cours.
        if self.current_transmission is None:
            self._schedule_slot_tick_if_needed(current_time)

    def _schedule_next_arrival(self, station_id: int, base_time: float) -> None:
        """Planifie la prochaine arrivée de paquet pour une station.

        Conforme à l'hypothèse du sujet : la station ne génère un nouveau paquet
        qu'après résolution (succès ou abandon) du paquet précédent.
        L'événement n'est pas planifié si l'instant calculé dépasse l'horizon de simulation.
        """
        next_arrival = base_time + self._sample_interarrival()
        if next_arrival <= self.config.simulation_time:
            self._push_event(next_arrival, EVENT_ARRIVAL, station_id)

    def _schedule_slot_tick_if_needed(self, current_time: float) -> None:
        """Planifie le prochain événement slot_tick si les conditions le permettent.

        Un slot_tick ne peut être planifié que si :
        - aucune transmission n'est en cours (canal libre), et
        - au moins une station est en phase de backoff actif.

        Le mécanisme de jeton (slot_tick_token) permet d'invalider les slot_ticks
        planifiés précédemment sans les retirer physiquement de la file de priorité.
        Un slot_tick périmé (jeton obsolète) est simplement ignoré à la dépile.
        """
        if self.current_transmission is not None or not self.contenders:
            return  # Canal occupé ou aucune station en attente : pas de slot_tick nécessaire

        # Le prochain slot doit respecter la période DIFS post-transmission (contention_open_time).
        candidate = next_slot_boundary(max(current_time, self.contention_open_time), self.config.slot_time)
        if self.scheduled_slot_tick_time is not None and self.scheduled_slot_tick_time <= candidate:
            return  # Un slot_tick déjà planifié à un instant antérieur est suffisant

        # Invalide tout slot_tick précédent en incrémentant le jeton.
        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = candidate
        self._push_event(candidate, EVENT_SLOT_TICK, -1, self.slot_tick_token)

    def _start_transmission(self, current_time: float, station_ids: list[int]) -> None:
        """Démarre une transmission de données (mode sans RTS/CTS).

        Si plusieurs stations transmettent simultanément (len > 1), c'est une collision :
        la trame se termine sans SIFS car aucun ACK ne suivra.
        Si une seule station transmet, on ajoute le SIFS pour modéliser l'ACK implicite.
        Dans tous les cas, un événement DATA_END est planifié en fin de trame.
        """
        if not station_ids:
            return

        self.current_transmission = set(station_ids)
        for station_id in station_ids:
            self.contenders.discard(station_id)  # La station quitte la phase de contention
            self.stations[station_id].packet.attempts += 1  # type: ignore[union-attr]

        self.total_attempts += len(station_ids)
        if len(station_ids) > 1:
            # Collision logique : plusieurs stations ont atteint b=0 simultanément.
            # Pas de SIFS car la trame est corrompue — aucun ACK ne sera envoyé.
            release_time = current_time + self.config.packet_duration
        else:
            # Transmission unique réussie : on ajoute le SIFS (délai avant ACK implicite).
            release_time = current_time + self.config.packet_duration + self.config.sifs

        # Invalide tout slot_tick planifié : le canal est maintenant occupé.
        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = None
        self._push_event(release_time, EVENT_DATA_END, -1)

    def _start_rts(self, current_time: float, station_ids: list[int]) -> None:
        """Démarre l'émission d'une trame RTS (mode RTS/CTS activé).

        Identique à _start_transmission mais planifie un événement RTS_END
        au lieu de DATA_END. La résolution collision/succès est traitée dans
        _handle_rts_end, qui décidera ensuite si la donnée peut être transmise.
        """
        if not station_ids:
            return

        self.current_transmission = set(station_ids)
        for station_id in station_ids:
            self.contenders.discard(station_id)  # La station entre en phase RTS
            self.stations[station_id].packet.attempts += 1  # type: ignore[union-attr]

        self.total_attempts += len(station_ids)
        rts_end = current_time + self.config.rts_duration
        # Invalide les slot_ticks pendant l'émission du RTS.
        self.slot_tick_token += 1
        self.scheduled_slot_tick_time = None
        self._push_event(rts_end, EVENT_RTS_END, -1)

    def _handle_arrival(self, current_time: float, station_id: int) -> None:
        """Traite l'arrivée d'un nouveau paquet dans une station.

        Crée une instance PacketState, incrémente le compteur global et amorce
        la procédure de contention (initialisation de W, K et b) via
        _prime_station_for_contention.
        Ignoré si la station possède déjà un paquet actif (ne devrait pas arriver
        avec la génération interne, mais protège contre les cas pathologiques).
        """
        station = self.stations[station_id]
        if station.packet is not None:
            # Cas théoriquement impossible avec la génération interne : la station ne doit
            # pas produire une nouvelle trame tant que la précédente n'est pas résolue.
            return

        self.generated_packets += 1
        station.packet = PacketState(arrival_time=current_time)
        self._prime_station_for_contention(station_id, current_time)

    def _handle_slot_tick(self, current_time: float) -> None:
        """Traite un événement slot_tick : décrémente les backoffs et déclenche les transmissions.

        Logique en trois étapes :
        1. Si une ou plusieurs stations ont déjà b=0 avant décrémentation, elles transmettent.
        2. Sinon, décrémente b de 1 pour toutes les stations actives (hors NAV).
        3. Si après décrémentation une ou plusieurs stations atteignent b=0, elles transmettent.
        4. Sinon, planifie le slot suivant.

        La double vérification (avant et après décrémentation) gère correctement le cas
        où b=0 était déjà atteint lors du déclenchement initial de la contention.
        """
        if self.current_transmission is not None or not self.contenders:
            return  # Canal occupé ou aucune station en contention : slot ignoré

        # Seules les stations hors NAV peuvent réellement contester le médium.
        # Les stations sous NAV (mode RTS/CTS) sont exclues de la décrémentation.
        active = [s for s in self.contenders if self.stations[s].nav_until <= current_time]

        # Étape 1 : stations déjà à b=0 — elles transmettent immédiatement.
        ready_to_send = [station_id for station_id in active if self.stations[station_id].backoff == 0]
        if ready_to_send:
            if self.config.rtscts:
                self._start_rts(current_time, ready_to_send)
            else:
                self._start_transmission(current_time, ready_to_send)
            return

        # Étape 2 : décrémentation du backoff pour toutes les stations actives.
        for station_id in active:
            station = self.stations[station_id]
            if station.backoff > 0:
                station.backoff -= 1

        # Étape 3 : stations qui atteignent b=0 après décrémentation.
        active_after = [station_id for station_id in active if self.stations[station_id].backoff == 0]
        if active_after:
            if self.config.rtscts:
                self._start_rts(current_time, active_after)
            else:
                self._start_transmission(current_time, active_after)
            return

        # Étape 4 : aucune station prête — planifie le slot suivant.
        self._schedule_slot_tick_if_needed(current_time + self.config.slot_time)
    def _handle_rts_end(self, current_time: float) -> None:
        """Traite la fin d'une émission RTS (mode RTS/CTS).

        Deux cas :
        - Collision RTS (len > 1) : applique le BEB à chaque station concernée,
          ou abandonne le paquet si K > K_max.
        - RTS réussi (len = 1) : le point d'accès envoie un CTS, toutes les autres
          stations bloquent leur backoff via le NAV, puis la donnée est transmise.
        """
        if self.current_transmission is None:
            return

        if len(self.current_transmission) > 1:
            # --- Collision RTS : plusieurs stations ont émis simultanément ---
            affected_stations = list(self.current_transmission)
            self.collided_packets += len(affected_stations)
            self.current_transmission = None
            # Les stations doivent attendre DIFS avant de pouvoir re-contester.
            self.contention_open_time = current_time + self.config.difs

            for station_id in affected_stations:
                station = self.stations[station_id]
                station.retries += 1
                if station.retries > self.config.kmax:
                    # K_max dépassé : paquet abandonné, réinitialisation complète.
                    self.dropped_packets += 1
                    station.packet = None
                    station.contention_window = self.config.wmin
                    station.retries = 0
                    self._schedule_next_arrival(station_id, current_time)
                    continue

                # BEB : W ← min(2W+1, W_max), nouveau tirage de backoff.
                station.contention_window = min(2 * station.contention_window + 1, self.config.wmax)
                station.backoff = self._sample_backoff(station.contention_window)
                self.contenders.add(station_id)

            self._schedule_slot_tick_if_needed(current_time)
            return

        # --- RTS réussi : une seule station a émis ---
        station_id = next(iter(self.current_transmission))
        # Chronologie : RTS_end + SIFS + CTS + SIFS + DATA
        data_end_time = current_time + self.config.sifs + self.config.cts_duration + self.config.sifs + self.config.packet_duration

        # Mécanisme NAV : toutes les autres stations bloquent leur backoff
        # jusqu'à la fin prévue de la transmission de données.
        for s in range(len(self.stations)):
            if s == station_id:
                continue
            st = self.stations[s]
            if st.packet is not None:
                st.nav_until = data_end_time  # Réservation du médium via NAV

        # On programme la fin de la transmission de données.
        self._push_event(data_end_time, EVENT_DATA_END, -1)

    def _handle_data_end(self, current_time: float) -> None:
        """Traite la fin d'une transmission de données.

        Deux cas :
        - Succès (len = 1) : enregistre le paquet, calcule le délai, libère la station,
          ouvre la prochaine fenêtre de contention après DIFS.
        - Collision (len > 1) : applique le BEB à chaque station concernée
          (mode sans RTS/CTS) ou abandonne si K > K_max.
          Avec RTS/CTS, ce cas est rare car le NAV protège la transmission.
        """
        if self.current_transmission is None:
            return

        is_collision = len(self.current_transmission) > 1
        if not is_collision:
            # --- Transmission réussie ---
            station_id = next(iter(self.current_transmission))
            station = self.stations[station_id]
            self.successful_packets += 1
            self.successful_bits += self.config.packet_bits
            # Délai individuel : temps entre génération et fin de transmission réussie.
            self.delay_sum += current_time - station.packet.arrival_time  # type: ignore[union-attr]
            station.packet = None
            # Réinitialisation des compteurs de contention après succès.
            station.contention_window = self.config.wmin
            station.retries = 0
            self.current_transmission = None
            # La prochaine contention ne peut débuter qu'après DIFS.
            self.contention_open_time = current_time + self.config.difs
            self._schedule_next_arrival(station_id, current_time)
            self._schedule_slot_tick_if_needed(current_time)
            return

        # --- Collision de données : cas rare avec RTS/CTS, ou plusieurs émetteurs synchrones ---
        affected_stations = list(self.current_transmission)
        self.collided_packets += len(affected_stations)  # Chaque station impliquée compte comme une collision
        self.current_transmission = None
        self.contention_open_time = current_time + self.config.difs

        for station_id in affected_stations:
            station = self.stations[station_id]
            station.retries += 1
            if station.retries > self.config.kmax:
                # K_max dépassé : paquet abandonné, réinitialisation complète.
                self.dropped_packets += 1
                station.packet = None
                station.contention_window = self.config.wmin
                station.retries = 0
                self._schedule_next_arrival(station_id, current_time)
                continue

            # BEB : W ← min(2W+1, W_max), nouveau tirage de backoff.
            station.contention_window = min(2 * station.contention_window + 1, self.config.wmax)
            station.backoff = self._sample_backoff(station.contention_window)
            self.contenders.add(station_id)

        self._schedule_slot_tick_if_needed(current_time)


def run_single_experiment(config: SimulationConfig) -> SimulationResult:
    """Crée un simulateur, lance une simulation et retourne les métriques.

    Fonction utilitaire qui encapsule la création de CSMACASimulator et l'appel à run().
    """
    simulator = CSMACASimulator(config)
    return simulator.run()


def average_results(results: list[SimulationResult]) -> SimulationResult:
    """Calcule la moyenne de plusieurs SimulationResult.

    Les compteurs entiers (paquets générés, tentatives, etc.) sont sommés.
    Les métriques continues (débit, taux, délai) sont moyennées.
    Utilisé pour réduire les fluctuations statistiques lors de runs multiples.

    Raises:
        ValueError: Si la liste results est vide.
    """
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
    """Balaye le nombre de stations de start à stop (inclus) par pas de step.

    Pour chaque valeur, exécute `runs` simulations avec des graines différentes
    et retourne la moyenne des métriques sous forme de liste d'ExperimentPoint.

    Args:
        base_config: Configuration de référence (les autres paramètres sont conservés).
        start:       Nombre de stations minimal.
        stop:        Nombre de stations maximal (inclus).
        step:        Pas d'incrémentation (doit être > 0).
        runs:        Nombre de répétitions par configuration (doit être > 0).

    Returns:
        Liste d'ExperimentPoint triée par x_value croissant.

    Raises:
        ValueError: Si step <= 0 ou runs <= 0.
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
    """Balaye la fenêtre de contention minimale W_min de start à stop par pas de step.

    Identique à sweep_stations mais fait varier wmin au lieu du nombre de stations.
    W_max est automatiquement ajusté à max(base_config.wmax, wmin) pour garantir
    wmin <= wmax à tout instant.

    Args:
        base_config: Configuration de référence.
        start:       Valeur minimale de W_min.
        stop:        Valeur maximale de W_min (incluse).
        step:        Pas d'incrémentation (doit être > 0).
        runs:        Nombre de répétitions par configuration (doit être > 0).

    Returns:
        Liste d'ExperimentPoint triée par x_value croissant.

    Raises:
        ValueError: Si step <= 0 ou runs <= 0.
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
    """Balaye le nombre maximal de tentatives K_max de start à stop par pas de step.

    Pour chaque valeur de K_max, exécute `runs` simulations avec des graines différentes
    et retourne la moyenne des métriques sous forme de liste d'ExperimentPoint.
    Un K_max faible provoque des abandons rapides (faible délai, paquets perdus) ;
    un K_max élevé laisse le BEB converger au prix d'un délai plus long.

    Args:
        base_config: Configuration de référence.
        start:       Valeur minimale de K_max.
        stop:        Valeur maximale de K_max (incluse).
        step:        Pas d'incrémentation (doit être > 0).
        runs:        Nombre de répétitions par configuration (doit être > 0).

    Returns:
        Liste d'ExperimentPoint triée par x_value croissant.

    Raises:
        ValueError: Si step <= 0 ou runs <= 0.
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


def print_result(config: SimulationConfig, result: SimulationResult) -> None:
    """Affiche la configuration et les métriques de simulation dans la console.

    Produit un bloc lisible avec les paramètres utilisés et les résultats obtenus.
    """
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


def save_csv(
    points: list[ExperimentPoint] | None,
    result: SimulationResult | None,
    config: SimulationConfig | None,
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


def plot_points(points: list[ExperimentPoint], title: str, x_label: str, output_path: Path) -> None:
    """Génère un graphique SVG à trois panneaux (débit, taux de collision, délai moyen).

    Le SVG est auto-contenu (pas de dépendance externe) et s'affiche directement
    dans un navigateur ou peut être intégré dans un rapport PDF.

    Args:
        points:      Liste de points expérimentaux (un par valeur de paramètre).
        title:       Titre principal affiché en haut du graphique.
        x_label:     Libellé de l'axe des abscisses commun aux trois panneaux.
        output_path: Chemin du fichier SVG de sortie (les dossiers sont créés si nécessaire).

    Raises:
        ValueError: Si points est vide.
    """
    if not points:
        raise ValueError("points must not be empty")

    width = 980
    height = 1190
    panel_width = 880
    panel_height = 280
    left = 50
    top_margin = 80
    panel_gap = 55
    inner_left = 95
    inner_right = 30
    inner_top = 55
    inner_bottom = 52

    # Blue/purple light-theme palette: (stroke, area-top-opacity, area-bot-opacity)
    PALETTE = [
        ("#6366f1", "0.14", "0.0"),   # indigo  — throughput
        ("#a855f7", "0.12", "0.0"),   # purple  — collision
        ("#0ea5e9", "0.11", "0.0"),   # sky     — delay
    ]

    x_values = [point.x_value for point in points]
    throughput_bits = [point.throughput_bits_per_s for point in points]
    collision_rates = [point.collision_rate * 100 for point in points]
    mean_delays = [point.mean_delay_s * 1000 for point in points]
    throughput_bits_stds = [point.throughput_bits_std for point in points]
    collision_stds = [point.collision_rate_std * 100 for point in points]
    delay_stds = [point.mean_delay_std * 1000 for point in points]

    def scale_x(index: int, count: int) -> float:
        """Convertit l'indice d'un point en coordonnée X SVG.

        Distribue uniformément les points sur la largeur utile du panneau.
        Retourne le centre horizontal si count == 1 (un seul point de données).
        """
        plot_w = panel_width - inner_left - inner_right
        if count == 1:
            return left + inner_left + plot_w / 2
        return left + inner_left + (plot_w * index / (count - 1))

    def scale_y(value: float, minimum: float, maximum: float, panel_top: float) -> float:
        """Convertit une valeur de données en coordonnée Y SVG (axe inversé : haut = maximum).

        Retourne le centre vertical du panneau si minimum == maximum (axe dégénéré),
        afin d'éviter une division par zéro.
        """
        plot_h = panel_height - inner_top - inner_bottom
        if math.isclose(minimum, maximum):  # pragma: no cover
            return panel_top + inner_top + plot_h / 2  # pragma: no cover
        return panel_top + inner_top + (maximum - value) * plot_h / (maximum - minimum)

    def format_ticks(minimum: float, maximum: float, count: int = 5) -> list[float]:
        """Calcule les valeurs des graduations régulièrement espacées sur l'axe Y.

        Retourne `count` valeurs de minimum à maximum inclus.
        Si minimum == maximum (axe dégénéré), retourne [minimum] pour éviter une erreur.
        """
        if math.isclose(minimum, maximum):  # pragma: no cover
            return [minimum]  # pragma: no cover
        step = (maximum - minimum) / (count - 1)
        return [minimum + step * index for index in range(count)]

    def smooth_curve(coords: list[tuple[float, float]]) -> str:
        """Génère un chemin SVG lissé à partir d'une liste de points (x, y).

        Utilise l'algorithme de spline de Catmull-Rom converti en courbes de Bézier
        cubiques : les tangentes en chaque point sont calculées à partir des voisins
        (P_{i-1} et P_{i+1}), ce qui produit une courbe C1 continue et visuellement
        douce sans nécessiter de bibliothèque externe.
        Retourne la chaîne de commande SVG au format « M... C... ».
        """
        if len(coords) < 2:
            return f"M{coords[0][0]:.2f},{coords[0][1]:.2f}"
        n = len(coords)
        parts = [f"M{coords[0][0]:.2f},{coords[0][1]:.2f}"]
        for i in range(n - 1):
            p0 = coords[max(0, i - 1)]
            p1 = coords[i]
            p2 = coords[i + 1]
            p3 = coords[min(n - 1, i + 2)]
            cp1x = p1[0] + (p2[0] - p0[0]) / 6
            cp1y = p1[1] + (p2[1] - p0[1]) / 6
            cp2x = p2[0] - (p3[0] - p1[0]) / 6
            cp2y = p2[1] - (p3[1] - p1[1]) / 6
            parts.append(f"C{cp1x:.2f},{cp1y:.2f} {cp2x:.2f},{cp2y:.2f} {p2[0]:.2f},{p2[1]:.2f}")
        return " ".join(parts)

    # Defs are accumulated here; panel_svg appends per-series area gradients.
    defs_parts: list[str] = [
        '<linearGradient id="svgBg" x1="0" y1="0" x2="0" y2="1" gradientUnits="objectBoundingBox">',
        '  <stop offset="0%" stop-color="#ffffff"/>',
        '  <stop offset="100%" stop-color="#f5f3ff"/>',
        '</linearGradient>',
        '<radialGradient id="topGlow" cx="50%" cy="0%" r="60%">',
        '  <stop offset="0%" stop-color="#6366f1" stop-opacity="0.05"/>',
        '  <stop offset="100%" stop-color="#6366f1" stop-opacity="0"/>',
        '</radialGradient>',
    ]

    def panel_svg(panel_index: int, panel_top: float, panel_title: str, y_label: str,
                  series: list[tuple[list[float], list[float], int, str]],
                  x_label_text: str = "") -> str:
        """Génère le SVG complet d'un panneau de graphique pour une métrique donnée.

        Trace la carte de fond, les axes, les lignes de grille, les courbes lissées,
        les barres d'erreur (±1σ) et les points de données pour chaque série fournie.
        Les dégradés de zone sont enregistrés dans `defs_parts` (accessible en closure).

        Args:
            panel_index: Indice du panneau (0=débit, 1=collision, 2=délai) — utilisé
                         pour générer des identifiants SVG uniques (gradients, etc.).
            panel_top:   Coordonnée Y du bord supérieur du panneau (pixels SVG).
            panel_title: Titre affiché en haut à gauche du panneau.
            y_label:     Libellé de l'unité affiché sous le titre (ex. "bits/s", "%", "ms").
            series:      Liste de séries à tracer ; chaque élément est un tuple
                         (valeurs, écarts-types, indice_palette, légende).

        Returns:
            Chaîne SVG (sans balise racine) représentant le panneau complet.
        """
        y_min = min(min(values) for values, _, _, _ in series)
        y_max = max(max(values) for values, _, _, _ in series)
        if math.isclose(y_min, y_max):
            y_min = 0.0
            y_max = y_max + 1.0
        y_padding = (y_max - y_min) * 0.10 or 1.0
        y_min = max(0.0, y_min - y_padding)
        y_max = y_max + y_padding

        plot_left = left + inner_left
        plot_top = panel_top + inner_top
        plot_w = panel_width - inner_left - inner_right
        plot_h = panel_height - inner_top - inner_bottom
        plot_bottom = plot_top + plot_h

        el: list[str] = []

        # Card
        el.append(
            f'<rect x="{left}" y="{panel_top}" width="{panel_width}" height="{panel_height}"'
            f' rx="14" fill="#ffffff" stroke="rgba(99,102,241,0.18)" stroke-width="1.2"'
            f' filter="drop-shadow(0 2px 8px rgba(99,102,241,0.08))"/>'
        )
        # Accent top bar
        el.append(
            f'<rect x="{left + 24}" y="{panel_top}" width="48" height="3"'
            f' rx="2" fill="rgba(99,102,241,0.55)"/>'
        )
        # Panel title
        el.append(
            f'<text x="{left + 20}" y="{panel_top + 32}"'
            f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
            f' font-size="15" font-weight="700" fill="#1e1b4b" letter-spacing="0.3">'
            f'{escape(panel_title)}</text>'
        )
        # y-label (unit)
        el.append(
            f'<text x="{left + 20}" y="{panel_top + 50}"'
            f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
            f' font-size="10" fill="#6b7280">{escape(y_label)}</text>'
        )

        # Horizontal grid lines
        for tick_value in format_ticks(y_min, y_max):
            y = scale_y(tick_value, y_min, y_max, panel_top)
            el.append(
                f'<line x1="{plot_left}" y1="{y:.2f}" x2="{plot_left + plot_w}" y2="{y:.2f}"'
                f' stroke="rgba(99,102,241,0.08)" stroke-width="1" stroke-dasharray="4,4"/>'
            )

        # Axes
        el.append(
            f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_left + plot_w}" y2="{plot_bottom}"'
            f' stroke="#d1d5db" stroke-width="1"/>'
        )
        el.append(
            f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}"'
            f' stroke="#d1d5db" stroke-width="1"/>'
        )

        # Y-axis labels
        for tick_value in format_ticks(y_min, y_max):
            y = scale_y(tick_value, y_min, y_max, panel_top)
            el.append(
                f'<text x="{plot_left - 8}" y="{y + 4:.2f}" text-anchor="end"'
                f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
                f' font-size="10" fill="#6b7280">{tick_value:.2f}</text>'
            )

        # X-axis labels
        for idx, x_value in enumerate(x_values):
            x = scale_x(idx, len(x_values))
            el.append(
                f'<line x1="{x:.2f}" y1="{plot_bottom}" x2="{x:.2f}" y2="{plot_bottom + 4}"'
                f' stroke="#d1d5db" stroke-width="1"/>'
            )
            el.append(
                f'<text x="{x:.2f}" y="{plot_bottom + 18}" text-anchor="middle"'
                f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
                f' font-size="10" fill="#6b7280">{x_value}</text>'
            )

        # X-axis label
        if x_label_text:
            el.append(
                f'<text x="{plot_left + plot_w / 2:.2f}" y="{plot_bottom + 36:.2f}" text-anchor="middle"'
                f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
                f' font-size="11" fill="#374151">{escape(x_label_text)}</text>'
            )

        # Per-series rendering
        for si, (values, stds, ci, label) in enumerate(series):
            stroke_color = PALETTE[ci][0]
            area_op_top = PALETTE[ci][1]
            area_op_bot = PALETTE[ci][2]

            coords = [
                (scale_x(idx, len(x_values)), scale_y(v, y_min, y_max, panel_top))
                for idx, v in enumerate(values)
            ]

            # Register area gradient in defs
            grad_id = f"areaGrad_p{panel_index}_s{si}"
            defs_parts.append(
                f'<linearGradient id="{grad_id}" x1="0" y1="{plot_top:.2f}" x2="0" y2="{plot_bottom:.2f}"'
                f' gradientUnits="userSpaceOnUse">'
            )
            defs_parts.append(
                f'  <stop offset="0%" stop-color="{stroke_color}" stop-opacity="{area_op_top}"/>'
            )
            defs_parts.append(
                f'  <stop offset="100%" stop-color="{stroke_color}" stop-opacity="{area_op_bot}"/>'
            )
            defs_parts.append('</linearGradient>')

            # Area fill
            curve_d = smooth_curve(coords)
            area_d = (
                f"{curve_d}"
                f" L{coords[-1][0]:.2f},{plot_bottom:.2f}"
                f" L{coords[0][0]:.2f},{plot_bottom:.2f} Z"
            )
            el.append(f'<path d="{area_d}" fill="url(#{grad_id})" stroke="none"/>')

            # Glow halo behind the line
            el.append(
                f'<path d="{curve_d}" fill="none" stroke="{stroke_color}"'
                f' stroke-width="8" stroke-opacity="0.18"'
                f' stroke-linecap="round" stroke-linejoin="round"/>'
            )
            # Main line
            el.append(
                f'<path d="{curve_d}" fill="none" stroke="{stroke_color}"'
                f' stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
            )

            # Error bars (±1 σ)
            for idx, (value, std) in enumerate(zip(values, stds)):
                if std > 0:
                    x = scale_x(idx, len(x_values))
                    y_hi = scale_y(min(value + std, y_max), y_min, y_max, panel_top)
                    y_lo = scale_y(max(value - std, y_min), y_min, y_max, panel_top)
                    el.append(
                        f'<line x1="{x:.2f}" y1="{y_hi:.2f}" x2="{x:.2f}" y2="{y_lo:.2f}"'
                        f' stroke="{stroke_color}" stroke-width="1.2" stroke-opacity="0.45"/>'
                    )
                    el.append(
                        f'<line x1="{x-4:.2f}" y1="{y_hi:.2f}" x2="{x+4:.2f}" y2="{y_hi:.2f}"'
                        f' stroke="{stroke_color}" stroke-width="1.2" stroke-opacity="0.45"/>'
                    )
                    el.append(
                        f'<line x1="{x-4:.2f}" y1="{y_lo:.2f}" x2="{x+4:.2f}" y2="{y_lo:.2f}"'
                        f' stroke="{stroke_color}" stroke-width="1.2" stroke-opacity="0.45"/>'
                    )

            # Data dots: outer glow ring + filled core
            for idx, value in enumerate(values):
                x = scale_x(idx, len(x_values))
                y = scale_y(value, y_min, y_max, panel_top)
                el.append(
                    f'<circle cx="{x:.2f}" cy="{y:.2f}" r="8"'
                    f' fill="{stroke_color}" fill-opacity="0.12" stroke="none"/>'
                )
                el.append(
                    f'<circle cx="{x:.2f}" cy="{y:.2f}" r="4"'
                    f' fill="{stroke_color}" stroke="#ffffff" stroke-width="1.5"/>'
                )

            # Legend entry
            legend_x = left + panel_width - 165
            legend_y = panel_top + 32 + si * 22
            el.append(
                f'<rect x="{legend_x}" y="{legend_y - 9}" width="22" height="4"'
                f' rx="2" fill="{stroke_color}" fill-opacity="0.85"/>'
            )
            el.append(
                f'<text x="{legend_x + 28}" y="{legend_y - 2}"'
                f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
                f' font-size="11" fill="#374151">{escape(label)}</text>'
            )

        return "\n".join(el)

    throughput_panel = panel_svg(
        0, top_margin,
        "Débit", "bits/s",
        [(throughput_bits, throughput_bits_stds, 0, "Débit (bits/s)")],
        x_label,
    )
    collision_panel = panel_svg(
        1, top_margin + panel_height + panel_gap,
        "Taux de collision", "%",
        [(collision_rates, collision_stds, 1, "Taux de collision (%)")],
        x_label,
    )
    delay_panel = panel_svg(
        2, top_margin + (panel_height + panel_gap) * 2,
        "Délai moyen", "ms",
        [(mean_delays, delay_stds, 2, "Délai moyen (ms)")],
        x_label,
    )

    defs_xml = "\n  ".join(defs_parts)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
  {defs_xml}
  </defs>
  <rect width="100%" height="100%" fill="url(#svgBg)"/>
  <rect width="100%" height="100%" fill="url(#topGlow)"/>
  <text x="{width / 2}" y="56" text-anchor="middle"
    font-family="system-ui,'Segoe UI',Arial,sans-serif"
    font-size="22" font-weight="700" fill="#1e1b4b" letter-spacing="0.4">{escape(title)}</text>
  {throughput_panel}
  {collision_panel}
  {delay_panel}
  <text x="{width - 20}" y="{height - 14}" text-anchor="end"
    font-family="system-ui,'Segoe UI',Arial,sans-serif"
    font-size="10" fill="#9ca3af">csma_ca_sim.py</text>
</svg>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    """Construit et retourne le parseur d'arguments en ligne de commande.

    Expose tous les paramètres de SimulationConfig ainsi que les options
    de balayage (--sweep-stations, --sweep-wmin) et de répétition (--runs).
    """
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
    """Point d'entrée principal du simulateur.

    Parse les arguments, construit la configuration, lance le ou les balayages
    paramétriques ou une simulation simple, puis affiche et sauvegarde les résultats.
    """
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
        title = args.title if args.title is not None else "CSMA/CA : impact du nombre de stations"
        plot_points(points, title, "Nombre de stations", args.output)
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
        title = args.title if args.title is not None else "CSMA/CA : impact de la fenêtre de contention minimale"
        plot_points(points, title, "Fenêtre de contention minimale (Wmin)", args.output)
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
        title = args.title if args.title is not None else "CSMA/CA : impact du nombre maximal de tentatives (K_max)"
        plot_points(points, title, "Nombre maximal de tentatives K_max", args.output)
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