# 📖 Code Source Entièrement Commenté - csma_ca_sim.py

## 📚 IMPORTS

### `from __future__ import annotations`
- **Rôle** : Permet d'utiliser les annotations de type modernes en Python (type hints au format texte)
- **Bénéfice** : Évite les problèmes de compatibilité avec les versions plus anciennes de Python

### `import argparse`
- **Rôle** : Module pour analyser et gérer les arguments passés en ligne de commande
- **Utilisation** : Parse les paramètres du simulateur (nombre de stations, taux d'arrivée, etc.)
- **Fonction clé** : `build_arg_parser()` retourne un `ArgumentParser` configuré

### `import heapq`
- **Rôle** : Implémente une file de priorité (priority queue) efficace basée sur un heap
- **Utilisation** : Gère la file d'événements discrets du simulateur
- **Fonction clé** : `heapq.heappush()` (ajouter un événement), `heapq.heappop()` (récupérer l'événement suivant)

### `import math`
- **Rôle** : Fournit des fonctions mathématiques avancées
- **Utilisation** : `math.ceil()` pour arrondir vers le haut, `math.isclose()` pour comparer des floats

### `import random`
- **Rôle** : Génère des nombres aléatoires
- **Utilisation** : Modélise les arrivées aléatoires de paquets (loi de Poisson) et le backoff aléatoire
- **Fonction clé** : `random.expovariate()` (distribution exponentielle), `randint()` (entier aléatoire)

### `from dataclasses import dataclass`
- **Rôle** : Décorateur pour créer des classes de données automatiquement
- **Utilisation** : Simplifie la création de structures de données (SimulationConfig, PacketState, etc.)
- **Avantage** : Génère automatiquement `__init__()`, `__repr__()`, `__eq__()`, etc.

### `from pathlib import Path`
- **Rôle** : Gère les chemins de fichiers de manière orientée objet
- **Utilisation** : Manipulation des fichiers de sortie (graphiques SVG)
- **Fonction clé** : `Path.write_text()` pour sauvegarder les fichiers

### `from statistics import mean`
- **Rôle** : Calcule la moyenne arithmétique
- **Utilisation** : Agrège les résultats de plusieurs simulations pour obtenir une moyenne

### `from xml.sax.saxutils import escape`
- **Rôle** : Échappe les caractères spéciaux XML/HTML (pour éviter les injections)
- **Utilisation** : Sécurise les textes insérés dans les graphiques SVG

### `from typing import Optional`
- **Rôle** : Type hint pour indiquer qu'une variable peut être `None` ou une autre valeur
- **Utilisation** : Améliore la clarté du code et l'autocomplétion dans les IDEs

---

## 🎯 CONSTANTES D'ÉVÉNEMENTS

### `EVENT_ARRIVAL = "arrival"`
- **Signification** : Événement quand un nouveau paquet arrive à une station
- **Déclencheur** : Selon la loi de Poisson (distribution exponentielle)
- **Gestion** : Fonction `_handle_arrival()`

### `EVENT_SLOT_TICK = "slot_tick"`
- **Signification** : Événement à chaque début de slot (unité de temps discrète)
- **Déclencheur** : Tous les `slot_time` secondes
- **Gestion** : Fonction `_handle_slot_tick()` (décrémente backoff, initie transmission)

### `EVENT_RTS_END = "rts_end"`
- **Signification** : Événement quand une transmission RTS (Request To Send) se termine
- **Déclencheur** : Mode RTS/CTS activé (`--rtscts`)
- **Gestion** : Fonction `_handle_rts_end()` (détecte collision RTS, envoie CTS si succès)

### `EVENT_DATA_END = "data_end"`
- **Signification** : Événement quand la transmission des données se termine
- **Déclencheur** : Après `packet_duration` secondes
- **Gestion** : Fonction `_handle_data_end()` (détecte collision, enregistre succès)

---

## 🔧 FONCTIONS UTILITAIRES

### `next_slot_boundary(time_value: float, slot_time: float) -> float`
- **Rôle** : Calcule le prochain début de slot après un instant donné
- **Paramètres** :
  - `time_value` : instant actuel en secondes
  - `slot_time` : durée d'un slot en secondes (défaut 20 µs)
- **Retour** : instant du prochain slot (valeur ≥ `time_value`)
- **Exemple** : Si `time_value=5.1` µs et `slot_time=20` µs → retourne 6.0 µs (slot suivant)
- **Utilité** : Synchronise les événements slot_tick sur les limites de slot

### `run_single_experiment(config: SimulationConfig) -> SimulationResult`
- **Rôle** : Exécute UNE simulation complète avec une configuration donnée
- **Paramètres** :
  - `config` : objet `SimulationConfig` avec tous les paramètres
- **Retour** : objet `SimulationResult` avec les métriques finales
- **Processus** : Crée un `CSMACASimulator` et l'exécute via `.run()`

### `average_results(results: list[SimulationResult]) -> SimulationResult`
- **Rôle** : Agrège les résultats de plusieurs simulations en une moyenne
- **Paramètres** :
  - `results` : liste de `SimulationResult` provenant de plusieurs runs
- **Retour** : objet `SimulationResult` avec valeurs moyennes
- **Calcul** : 
  - Pour "bits/s" : moyenne des débits
  - Pour "generated_packets" : SOMME totale de tous les runs
- **Utilité** : Réduit la variance en moyennant plusieurs exécutions

### `sweep_stations(base_config, start, stop, step, runs) -> list[ExperimentPoint]`
- **Rôle** : Balaie le nombre de stations et mesure l'impact sur les performances
- **Paramètres** :
  - `base_config` : configuration de base (`SimulationConfig`)
  - `start` : nombre initial de stations (ex: 2)
  - `stop` : nombre final de stations (ex: 20)
  - `step` : pas d'incrémentation (ex: 2 → teste 2, 4, 6, ..., 20)
  - `runs` : nombre d'exécutions par valeur (ex: 10 pour moyenne)
- **Retour** : liste de points (x=nombre stations, y=métriques)
- **Utilité** : Génère des courbes "débit vs. nombre de stations"
- **Exemple** : `sweep_stations(config, 2, 20, 2, 10)` → teste N=2,4,6,...,20 avec 10 répétitions chaque

### `sweep_wmin(base_config, start, stop, step, runs) -> list[ExperimentPoint]`
- **Rôle** : Balaie la fenêtre de contention minimale (Wmin) et mesure l'impact
- **Paramètres** :
  - Identiques à `sweep_stations()` mais fait varier `wmin` au lieu de `station_count`
- **Retour** : liste de points (x=Wmin, y=métriques)
- **Utilité** : Analyse l'impact du paramètre de backoff sur les performances

### `print_result(config: SimulationConfig, result: SimulationResult) -> None`
- **Rôle** : Affiche les résultats de simulation en format texte lisible
- **Paramètres** :
  - `config` : configuration utilisée
  - `result` : résultats obtenus
- **Affichage** : 
  - Section "Configuration" : tous les paramètres MAC/physiques
  - Section "Results" : débit, collision, délai, paquets générés/réussis/perdus
- **Sortie** : Texte sur la console

### `plot_points(points, title, x_label, output_path) -> None`
- **Rôle** : Génère un graphique SVG en trois panneaux (débit, collision, délai)
- **Paramètres** :
  - `points` : liste de `ExperimentPoint` (résultats de sweep)
  - `title` : titre du graphique (ex: "CSMA/CA: impact du nombre de stations")
  - `x_label` : label de l'axe X (ex: "Nombre de stations")
  - `output_path` : chemin du fichier SVG à créer
- **Fonctions internes** :
  - `scale_x()`, `scale_y()` : transforment les coordonnées pour l'affichage
  - `format_ticks()` : génère les marques de l'axe Y
  - `panel_svg()` : crée un panneau (courbe + axes + légende)
- **Sortie** : Fichier SVG (pur, sans dépendance externe)
- **Note** : Ne dépend pas de matplotlib, utilise SVG brut

### `build_arg_parser() -> argparse.ArgumentParser`
- **Rôle** : Crée et configure l'analyseur d'arguments en ligne de commande
- **Retour** : objet `ArgumentParser` configuré avec tous les paramètres
- **Arguments définis** (voir section CLASSE SimulationConfig pour détails) :
  - `--stations` : nombre de stations (défaut 8)
  - `--arrival-rate` : taux d'arrivée (défaut 20 pkt/s)
  - `--wmin`, `--wmax`, `--kmax` : paramètres CSMA/CA
  - `--sweep-stations` ou `--sweep-wmin` : mode balayage
  - `--rtscts` : active RTS/CTS
  - etc.
- **Utilité** : Rend le simulateur configurable sans modifier le code

### `main() -> None`
- **Rôle** : Point d'entrée principal du programme
- **Processus** :
  1. Parse les arguments (`build_arg_parser()`)
  2. Crée la configuration (`SimulationConfig`)
  3. Exécute le mode approprié :
     - Mode balayage stations : `sweep_stations()` + `plot_points()`
     - Mode balayage Wmin : `sweep_wmin()` + `plot_points()`
     - Mode simple : `run_single_experiment()` ou `average_results()`
  4. Affiche les résultats (`print_result()`)
- **Utilité** : Orchestre toute l'exécution du programme

---

## 🏗️ CLASSES DE DONNÉES (@dataclass)

### `SimulationConfig`
**Rôle** : Encapsule TOUS les paramètres de configuration du simulateur (structure immuable)

#### Paramètres de Simulation
- `station_count: int = 8`
  - **Rôle** : Nombre de stations dans le réseau
  - **Défaut** : 8
  - **Plage** : 1 à 100+ (testé jusqu'à 32)
  - **CLI** : `--stations N`

- `arrival_rate: float = 20.0`
  - **Rôle** : Taux d'arrivée Poisson par station (paquets/seconde)
  - **Défaut** : 20 pkt/s
  - **Formule** : Inter-arrivée = exponentielle(λ=20)
  - **CLI** : `--arrival-rate R`

- `simulation_time: float = 20.0`
  - **Rôle** : Durée totale de la simulation (secondes simulées)
  - **Défaut** : 20 secondes
  - **Note** : TEMPS SIMULÉ, pas temps réel
  - **CLI** : `--simulation-time T`

#### Paramètres Physiques
- `packet_bits: int = 12000`
  - **Rôle** : Taille d'un paquet en bits
  - **Défaut** : 12000 bits (1500 octets, paquet Ethernet typique)
  - **Calcul débit** : `débit_bits/s = paquets_réussis * packet_bits / temps_sim`
  - **CLI** : `--packet-bits B`

- `packet_duration: float = 0.001`
  - **Rôle** : Temps pour transmettre un paquet (secondes)
  - **Défaut** : 0.001 s = 1 ms
  - **Calcul** : `packet_duration = packet_bits / débit_physique`
  - **Example** : 12000 bits à 12 Mbps = 1 ms
  - **CLI** : `--packet-duration D`

- `slot_time: float = 20e-6`
  - **Rôle** : Durée d'un slot (unité de temps CSMA/CA)
  - **Défaut** : 20 µs (IEEE 802.11)
  - **Utilité** : Mesure de précision du backoff
  - **CLI** : `--slot-time S`

- `difs: float = 50e-6`
  - **Rôle** : DIFS = Distributed Inter-Frame Space (espace entre trames)
  - **Défaut** : 50 µs (IEEE 802.11)
  - **Utilité** : Temps d'attente après collision avant contention
  - **CLI** : `--difs D`

- `sifs: float = 10e-6`
  - **Rôle** : SIFS = Short Inter-Frame Space (espace court)
  - **Défaut** : 10 µs (IEEE 802.11)
  - **Utilité** : Temps entre RTS et CTS, ou entre CTS et DATA
  - **CLI** : `--sifs S`

#### Paramètres CSMA/CA de Backoff
- `wmin: int = 15`
  - **Rôle** : Fenêtre de contention MINIMALE (Wmin)
  - **Défaut** : 15 slots (IEEE 802.11b)
  - **Signification** : W₀ = Wmin, backoff initial ∈ [0, Wmin-1]
  - **CLI** : `--wmin W`

- `wmax: int = 1023`
  - **Rôle** : Fenêtre de contention MAXIMALE (Wmax)
  - **Défaut** : 1023 slots (IEEE 802.11)
  - **Signification** : Limite l'augmentation du backoff exponentiel
  - **Formule** : W' = min(2W + 1, Wmax)
  - **CLI** : `--wmax W`

- `kmax: int = 15`
  - **Rôle** : Nombre MAXIMAL de retransmissions avant abandon (Kmax)
  - **Défaut** : 15 tentatives
  - **Processus** : Si `retries > kmax` → paquet perdu
  - **CLI** : `--kmax K`

#### Paramètres Aléatoires
- `seed: Optional[int] = None`
  - **Rôle** : Graine pour le générateur aléatoire (reproduire résultats)
  - **Défaut** : `None` (aléatoire à chaque exécution)
  - **Utilité** : Permet de reproduire exactement les mêmes résultats
  - **CLI** : `--seed S`

#### Mode RTS/CTS
- `rtscts: bool = False`
  - **Rôle** : Active le mécanisme RTS/CTS + NAV
  - **Défaut** : `False` (mode simple sans RTS/CTS)
  - **Impact** : Réduit les collisions de données, augmente surcharge
  - **CLI** : `--rtscts`

- `rts_duration: float = 200e-6`
  - **Rôle** : Durée d'une transmission RTS (secondes)
  - **Défaut** : 200 µs
  - **Utilité** : Utilisé uniquement si `rtscts=True`
  - **CLI** : `--rts-duration D`

- `cts_duration: float = 200e-6`
  - **Rôle** : Durée d'une transmission CTS (secondes)
  - **Défaut** : 200 µs
  - **Utilité** : Utilisé uniquement si `rtscts=True`
  - **CLI** : `--cts-duration D`

---

### `PacketState`
**Rôle** : Représente l'état d'un paquet en attente de transmission

#### Attributs
- `arrival_time: float`
  - **Signification** : Instant auquel le paquet est arrivé à la station
  - **Utilité** : Calcul du délai (fin_transmission - arrival_time)

- `attempts: int = 0`
  - **Signification** : Nombre de tentatives de transmission effectuées
  - **Incrémentation** : +1 à chaque `_start_transmission()` ou `_start_rts()`
  - **Note** : Distinct de `retries` (retries = attempts - 1 après première tentative)

---

### `StationState`
**Rôle** : Représente l'état MAC complet d'une station CSMA/CA

#### Identité
- `station_id: int`
  - **Signification** : Identificateur unique de la station (0 à N-1)

#### Paquet en Attente
- `packet: Optional[PacketState] = None`
  - **Signification** : Le paquet en cours de transmission (une seule file par station)
  - **`None`** : Pas de paquet en attente
  - **Non-None** : Paquet en contention ou transmission
  - **Contrainte** : Une seule file (déjà respectée, pas de buffering)

#### Fenêtre de Contention
- `contention_window: int = 0`
  - **Signification** : Taille actuelle de la fenêtre de contention W
  - **Initialisation** : W = Wmin à l'arrivée d'un nouveau paquet
  - **Augmentation** : W' = min(2W + 1, Wmax) après collision
  - **Utilité** : Détermine la plage du backoff aléatoire [0, W-1]

#### Backoff
- `backoff: int = 0`
  - **Signification** : Compteur de backoff en nombre de SLOTS
  - **Initialisation** : Random ∈ [0, W-1] à chaque arrivée/collision
  - **Décrémentation** : -1 à chaque slot_tick
  - **Transmission** : Quand backoff == 0 (station prête à envoyer)

#### Retransmissions
- `retries: int = 0`
  - **Signification** : Nombre de retransmissions déjà effectuées
  - **Incrémentation** : +1 après collision/RTS collision (pas après arrivée)
  - **Abandon** : Si retries > kmax → paquet perdu, station libre

#### Protection NAV (RTS/CTS)
- `nav_until: float = 0.0`
  - **Signification** : Instant jusqu'où la station respecte le NAV (Network Allocation Vector)
  - **Rôle** : Protège le canal réservé par une transmission RTS/CTS
  - **Fonctionnement** : Si `nav_until > current_time` → station n'émet pas
  - **Activation** : Mis à jour par `_handle_rts_end()` en mode RTS/CTS
  - **Défaut** : 0.0 (pas de NAV)

---

### `SimulationResult`
**Rôle** : Encapsule les résultats finaux d'une simulation (métriques agrégées)

#### Métriques de Débit
- `throughput_packets_per_s: float`
  - **Signification** : Débit en paquets par seconde
  - **Calcul** : `successful_packets / simulation_time`
  - **Unité** : pkt/s

- `throughput_bits_per_s: float`
  - **Signification** : Débit en bits par seconde
  - **Calcul** : `(successful_packets * packet_bits) / simulation_time`
  - **Unité** : bits/s (ou Mbps/Gbps selon magnitude)

#### Métrique de Collision
- `collision_rate: float`
  - **Signification** : Taux de collision (entre 0 et 1)
  - **Calcul** : `collided_packets / total_attempts`
  - **Interprétation** : % de tentatives qui ont collisionnées
  - **Affichage** : Multiplié par 100 pour % dans `print_result()`

#### Métrique de Délai
- `mean_delay_s: float`
  - **Signification** : Délai moyen de transmission en secondes
  - **Calcul** : `delay_sum / successful_packets` où `delay_sum = Σ(tx_time - arrival_time)`
  - **Unité** : secondes (affichées en ms dans `print_result()`)
  - **Interprétation** : Temps moyen entre génération et transmission réussie d'un paquet

#### Statistiques de Paquets
- `generated_packets: int`
  - **Signification** : Nombre total de paquets générés
  - **Incrémentation** : +1 à chaque appel de `_handle_arrival()`

- `successful_packets: int`
  - **Signification** : Nombre de paquets transmis avec succès
  - **Incrémentation** : +1 à chaque succès dans `_handle_data_end()`

- `dropped_packets: int`
  - **Signification** : Nombre de paquets abandonnés après Kmax retransmissions
  - **Incrémentation** : +1 quand `retries > kmax`

- `total_attempts: int`
  - **Signification** : Nombre total de tentatives de transmission
  - **Incrémentation** : +nombre_de_stations_qui_envoient à chaque transmission
  - **Détails** : Compte les collisions

- `collided_packets: int`
  - **Signification** : Nombre de paquets ayant entré en collision
  - **Incrémentation** : +nombre_en_collision à chaque collision détectée

---

### `ExperimentPoint`
**Rôle** : Représente un point dans un graphique de balayage (sweep)

#### Coordonnée X
- `x_value: int`
  - **Signification** : Valeur du paramètre balayé
  - **Exemple** : Nombre de stations (2, 4, 6, ..., 20) ou Wmin (15, 31, 47, ...)

#### Métriques (mêmes que SimulationResult)
- `throughput_packets_per_s: float` → pour la courbe
- `throughput_bits_per_s: float` → pour la courbe
- `collision_rate: float` → pour la courbe
- `mean_delay_s: float` → pour la courbe

---

## ⚙️ CLASSE PRINCIPALE : CSMACASimulator

**Rôle** : Moteur de simulation discrete-event CSMA/CA

### Initialisation (`__init__`)

#### Paramètres
- `config: SimulationConfig` : Configuration de la simulation

#### Attributs Fondamentaux
- `self.config : SimulationConfig`
  - **Rôle** : Référence à la configuration (paramètres)

- `self.random : random.Random`
  - **Rôle** : Générateur aléatoire avec graine optionnelle
  - **Utilité** : Garantit la reproductibilité

- `self.stations : list[StationState]`
  - **Rôle** : Tableau des états de toutes les stations
  - **Taille** : `config.station_count` éléments
  - **Initialisation** : Tous les stations commencent sans paquet

#### Gestion d'Événements
- `self.event_queue : list[tuple[float, int, str, int, Optional[int]]]`
  - **Rôle** : File de priorité (heap) des événements
  - **Tuple** : (time, sequence, event_type, station_id, token)
  - **Ordre** : Événements triés par (time, sequence)

- `self.sequence : int = 0`
  - **Rôle** : Compteur incrémental pour briser les égalités de temps
  - **Utilité** : Déterministe si deux événements ont le même temps

#### État de Contention
- `self.contenders : set[int]`
  - **Rôle** : Ensemble des ID de stations en attente de transmission
  - **Ajout** : Quand un paquet arrive
  - **Suppression** : Quand transmission débute

- `self.current_transmission : Optional[set[int]]`
  - **Rôle** : ID des stations transmettant actuellement
  - **`None`** : Canal libre
  - **Ensemble** : Une ou plusieurs stations (si collision)
  - **Utilité** : Détecte collisions (taille > 1)

#### Synchronisation Temporelle
- `self.contention_open_time : float = 0.0`
  - **Rôle** : Instant de réouverture du canal après collision/transmission
  - **Attente** : Ajoute DIFS après transmission réussie
  - **Utilité** : Empêche contention immédiate après fin transmission

- `self.scheduled_slot_tick_time : Optional[float]`
  - **Rôle** : Instant auquel le prochain slot_tick est programmé
  - **Optimisation** : Évite de programmer plusieurs slot_ticks identiques

- `self.slot_tick_token : int = 0`
  - **Rôle** : Numéro de version du slot_tick programmé
  - **Utilité** : Invalide les anciens slot_ticks si reprogrammé

- `self.nav_until : float = 0.0`
  - **Rôle** : Contrôle global du NAV (rarement utilisé, var d'état)

#### Compteurs de Statistiques
- `self.generated_packets : int = 0` → Paquets générés
- `self.successful_packets : int = 0` → Paquets transmis avec succès
- `self.dropped_packets : int = 0` → Paquets perdus après Kmax
- `self.total_attempts : int = 0` → Tentatives totales
- `self.collided_packets : int = 0` → Paquets en collision
- `self.successful_bits : int = 0` → Bits transmis (pour débit)
- `self.delay_sum : float = 0.0` → Somme des délais

---

### Méthode `run() -> SimulationResult`
**Rôle** : Exécute la simulation principale (boucle d'événements)

#### Processus
1. **Initialisation** : Programme les premières arrivées pour chaque station
2. **Boucle d'événements** : Tant que `event_queue` non vide :
   - Retire l'événement le plus tôt
   - Valide les slot_ticks obsolètes
   - Appelle le handler approprié
3. **Calcul final** : Agrège les statistiques
4. **Retour** : Objet `SimulationResult` avec tous les métriques

#### Calculs Finaux
- `throughput_packets_per_s = successful_packets / simulation_time`
- `throughput_bits_per_s = successful_bits / simulation_time`
- `collision_rate = collided_packets / total_attempts` (évite division par 0)
- `mean_delay_s = delay_sum / successful_packets` (évite division par 0)

---

### Méthode `_push_event(time_value, event_type, station_id, token=None) -> None`
**Rôle** : Ajoute un événement à la file avec priorité temporelle

#### Paramètres
- `time_value : float` : Instant d'exécution de l'événement
- `event_type : str` : Type d'événement (EVENT_ARRIVAL, EVENT_SLOT_TICK, etc.)
- `station_id : int` : ID de la station impliquée (-1 si événement global)
- `token : Optional[int]` : Token de validation (pour slot_ticks surtout)

#### Processus
1. Incrémente `self.sequence` (garantit ordre déterministe)
2. Crée tuple : `(time_value, sequence, event_type, station_id, token)`
3. `heapq.heappush()` ajoute le tuple au heap

---

### Méthode `_sample_interarrival() -> float`
**Rôle** : Génère le temps d'attente jusqu'au prochain paquet (loi exponentielle = Poisson)

#### Formule
- Si `arrival_rate ≤ 0` → retourne `math.inf` (pas d'arrivées)
- Sinon → `random.expovariate(arrival_rate)` (distribution exponentielle)

#### Interprétation
- `arrival_rate = λ` paramètre Poisson
- Inter-arrivées = Exponentielle(λ)
- Résultat en secondes

#### Exemple
- `arrival_rate = 20 pkt/s` → Inter-arrivée moyenne = 0.05 s = 50 ms

---

### Méthode `_sample_backoff(contention_window: int) -> int`
**Rôle** : Génère un délai de backoff aléatoire

#### Formule
- Retourne : `random.randint(0, contention_window)`
- Plage : [0, contention_window] inclus (donc W valeurs possibles si W=contention_window)

#### Interprétation
- Backoff ∈ [0, W-1] slots
- Uniforme et aléatoire

---

### Méthode `_schedule_next_arrival(station_id, base_time) -> None`
**Rôle** : Programme la prochaine arrivée de paquet pour une station

#### Processus
1. Appelle `_sample_interarrival()` → délai aléatoire
2. Calcule `next_arrival = base_time + interarrival`
3. Si `next_arrival ≤ simulation_time` → programme l'événement
4. Sinon → pas de nouvelle arrivée (simulation termin

ée pour cette station)

---

### Méthode `_schedule_slot_tick_if_needed(current_time) -> None`
**Rôle** : Programme un tick d'horloge si nécessaire (optimisation)

#### Conditions pour NE PAS programmer
- Transmission en cours (`current_transmission ≠ None`)
- Aucune station en attente (`contenders` vide)

#### Processus
1. Calcule prochain début de slot : `next_slot_boundary(max(current_time, contention_open_time), slot_time)`
2. Vérifie si un tick est déjà programmé à cette time (évite duplicatas)
3. Incrémente `slot_tick_token` (invalide anciens ticks)
4. Programme le nouveau tick

---

### Méthode `_start_transmission(current_time, station_ids) -> None`
**Rôle** : Initie une transmission de données (mode simple, sans RTS)

#### Paramètres
- `current_time : float` : Instant actuel
- `station_ids : list[int]` : ID des stations à transmettre (1 ou plus si collision)

#### Processus
1. `self.current_transmission = set(station_ids)` → marque canal occupé
2. Pour chaque station : retirer du `contenders`, incrémenter `attempts`
3. Ajouter à `total_attempts` le nombre de stations
4. Calcule `release_time = current_time + packet_duration + (sifs si pas collision)`
5. Invalide les anciens slot_ticks
6. Programme l'événement `EVENT_DATA_END` à `release_time`

#### Collision Détectée
- Si `len(station_ids) > 1` → collision logique
- Release time = `current_time + packet_duration` (pas SIFS car collision)

---

### Méthode `_start_rts(current_time, station_ids) -> None`
**Rôle** : Initie une transmission RTS (mode RTS/CTS, bonus)

#### Paramètres
- Identiques à `_start_transmission()`

#### Processus
1. Marque transmission en cours
2. Incrémente `attempts` et `total_attempts`
3. Calcule `rts_end = current_time + rts_duration`
4. Invalide anciens slot_ticks
5. Programme l'événement `EVENT_RTS_END` à `rts_end`

#### Différence vs Data Transmission
- Transmet RTS (court, ~200 µs) au lieu de données
- Si collision RTS détectée → tous les RTS en collision
- Si succès RTS → station envoie CTS (point d'accès) puis données

---

### Méthode `_handle_arrival(current_time, station_id) -> None`
**Rôle** : Gère l'arrivée d'un nouveau paquet

#### Processus
1. Récupère `station = stations[station_id]`
2. **Vérification** : Si `station.packet ≠ None` → rejette arrivée (file complète)
3. **Incrémente** `generated_packets`
4. **Initialise paquet** :
   - `packet = PacketState(arrival_time=current_time, attempts=0)`
   - `contention_window = wmin`
   - `retries = 0`
   - `backoff = sample_backoff(wmin)` (aléatoire ∈ [0, Wmin-1])
5. **Ajoute à contenders** : `contenders.add(station_id)`
6. **Programme slot_tick** si canal libre (`current_transmission == None`)

#### Contrainte Importante
- Une seule file par station : rejette les arrivées si un paquet attend déjà

---

### Méthode `_handle_slot_tick(current_time) -> None`
**Rôle** : Gère chaque tick d'horloge (décrémente backoff, initie transmission)

#### Vérifications Initiales
- Si transmission en cours → abandon (attendre fin)
- Si aucun contender → abandon (rien à faire)

#### Filtre NAV
- `active = [s for s in contenders if stations[s].nav_until ≤ current_time]`
- Exclut les stations sous NAV

#### Cas 1 : Stations Prêtes (backoff == 0)
- `ready_to_send = [s for s in active if stations[s].backoff == 0]`
- Si vide → cas 2
- Si non-vide :
  - Mode RTS/CTS → `_start_rts(current_time, ready_to_send)`
  - Mode simple → `_start_transmission(current_time, ready_to_send)`
  - Return (transmission lancée)

#### Cas 2 : Décrémentation de Backoff
- Pour chaque `s` dans `active` : `stations[s].backoff -= 1`

#### Cas 3 : Vérification Post-Décrémentation
- `active_after = [s pour s in active si backoff == 0]`
- Si non-vide → lancer transmission (Cas 1 bis)
- Si vide → programmer prochain slot_tick

#### Programmation Prochain Slot
- `_schedule_slot_tick_if_needed(current_time + slot_time)`
- Programmé au prochain début de slot

---

### Méthode `_handle_rts_end(current_time) -> None`
**Rôle** : Gère la fin d'une transmission RTS (détecte collision RTS ou succès)

#### Cas 1 : Collision RTS (len(transmission) > 1)
- **Statut** : Plusieurs stations ont envoyé RTS simultanément
- **Action** :
  - Compte collisions : `collided_packets += len(affected_stations)`
  - Réinitialise : `current_transmission = None`
  - Ajoute DIFS : `contention_open_time = current_time + difs`
  - Pour chaque station en collision :
    - `retries += 1`
    - Si `retries > kmax` → paquet perdu, réinitialise
    - Sinon → augmente fenêtre `W' = min(2W+1, Wmax)`, tire nouveau backoff
  - Programme prochain slot_tick

#### Cas 2 : Succès RTS (len(transmission) == 1)
- **Statut** : Une seule station a envoyé RTS (pas de collision)
- **Action** :
  - Calcule durée CTS+SIFS+DATA : `data_end_time = current_time + sifs + cts_duration + sifs + packet_duration`
  - **NAV Protection** : Met à jour `nav_until` pour toutes les autres stations (qui ont un paquet)
  - Programme `EVENT_DATA_END` à `data_end_time`
  - Point d'accès envoie CTS, station envoie data

---

### Méthode `_handle_data_end(current_time) -> None`
**Rôle** : Gère la fin d'une transmission de données

#### Cas 1 : Succès (len(transmission) == 1 et pas collision)
- **Statut** : Un paquet transmis sans collision
- **Action** :
  - `successful_packets += 1`
  - `successful_bits += packet_bits`
  - Calcule délai : `delay_sum += current_time - packet.arrival_time`
  - Réinitialise la station : packet=None, W=Wmin, retries=0
  - Marque canal libre : `current_transmission = None`
  - DIFS : `contention_open_time = current_time + difs`
  - Programme prochaine arrivée pour cette station
  - Programme prochain slot_tick si contenders

#### Cas 2 : Collision Data (len(transmission) > 1)
- **Statut** : Deux ou plusieurs stations transmettent simultanément (rare en mode RTS/CTS)
- **Action** :
  - Compte collision
  - Réinitialise transmission
  - Pour chaque station :
    - `retries += 1`
    - Si `retries > kmax` → paquet perdu
    - Sinon → augmente fenêtre, tire nouveau backoff
  - Programme prochain slot_tick

---

## 🎯 RÉSUMÉ DE FLUX

### Flux Généreux (Happy Path - Mode Simple)

```
ARRIVÉE → BACKOFF ALÉATOIRE → SLOT TICKS → BACKOFF == 0 → TRANSMISSION → DATA_END (SUCCÈS)
  ↓           ↓                                                             ↓
généré    W=Wmin                                                      successful++
          retries=0                                                   delay_sum += délai
          contenders++                                                packet=None
```

### Flux Collision

```
ARRIVÉE → ... → TRANSMISSION (2+ stations) → DATA_END (COLLISION)
                                                      ↓
                                              collided_packets++
                                              retries++
                                              W' = min(2W+1, Wmax)
                                              backoff = sample(W')
                                              contenders.add()
                                              → Retour à SLOT TICKS
```

### Flux Abandon (Kmax)

```
ARRIVÉE → ... → COLLISION → COLLISION → ... → COLLISION (retries > kmax)
                                                       ↓
                                                dropped++
                                                packet=None
                                                → Pas de retransmission
```

### Flux RTS/CTS (Bonus)

```
ARRIVÉE → BACKOFF → SLOT TICKS → RTS → RTS_END
                                         ↓
                                    (Si succès RTS)
                                    NAV pour autres
                                    → CTS → DATA → DATA_END (SUCCÈS)
```

---

## 📊 EXEMPLE D'EXÉCUTION

### Ligne de Commande
```bash
python csma_ca_sim.py --stations 5 --arrival-rate 10 --simulation-time 5 --runs 3
```

### Séquence d'Exécution
1. `main()` parse arguments
2. Crée `SimulationConfig(station_count=5, arrival_rate=10, ...)`
3. Boucle `for run in range(3)` :
   - Appelle `run_single_experiment(config)`
   - Crée `CSMACASimulator(config)`
   - Appelle `simulator.run()`
     - Boucle d'événements
     - Retourne `SimulationResult`
4. Appelle `average_results(results)` → moyenne des 3 runs
5. Appelle `print_result(config, result)` → affiche métriques

---

## 🎓 POINTS CLÉS À RETENIR

### Loi de Poisson
- Arrivées = distribution exponentielle (`expovariate`)
- Modélise les appels aléatoires dans les réseaux réels
- Paramètre λ = taux d'arrivée

### Backoff Exponentiel
- W₀ = Wmin
- Après collision : W' = min(2W + 1, Wmax)
- Backoff aléatoire ∈ [0, W-1]
- Réduit congestion après collision

### Collision Logique
- Deux+ stations avec backoff == 0 au même slot
- Aucune transmission réelle (simulateur discret)
- Détectée par `len(current_transmission) > 1`

### Métriques Clés
- **Débit** : Paquets réussis / temps
- **Collision** : Paquets en collision / tentatives
- **Délai** : Temps moyen attente (génération → succès)

### Modes
- **Simple** : Transmission directe (sans RTS/CTS)
- **RTS/CTS** : Handshake court + NAV pour autres stations

