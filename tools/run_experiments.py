#!/usr/bin/env python3
"""Script de reproduction des expériences du rapport CSMA/CA.

Lance les 5 scénarios décrits dans le rapport académique et génère :
  - les graphiques SVG dans le dossier figures/
  - les fichiers CSV de données brutes dans le dossier data/

Usage (depuis la racine du projet) :
    python tools/run_experiments.py

Pré-requis :
    L'environnement virtuel doit être activé (ou les dépendances installées).
"""

# ---------------------------------------------------------------------------
# Imports : bibliothèques standard uniquement (pas de dépendance externe)
# ---------------------------------------------------------------------------
import subprocess  # Pour lancer csma_ca_sim.py en tant que sous-processus
import sys         # Pour récupérer l'interpréteur Python actif
from pathlib import Path  # Manipulation portable des chemins de fichiers

# ---------------------------------------------------------------------------
# Constantes globales
# ---------------------------------------------------------------------------
PYTHON = sys.executable  # Interpréteur Python courant (respecte l'environnement virtuel actif)
ROOT   = Path(__file__).resolve().parent.parent  # Racine du projet
SIM    = ROOT / "csma_ca_sim.py"  # Simulateur principal
FIGURES = ROOT / "figures"  # Dossier de sortie pour les graphiques SVG
DATA    = ROOT / "data"     # Dossier de sortie pour les données CSV brutes

# Création des dossiers de sortie si nécessaire (ne lève pas d'erreur s'ils existent déjà)
FIGURES.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Définition des 5 expériences à reproduire
# Chaque entrée contient :
#   "name" : description affichée dans la console pendant l'exécution
#   "args" : liste d'arguments passés à csma_ca_sim.py via la ligne de commande
# Les paramètres correspondent exactement aux expériences décrites dans RAPPORT.md.
# ---------------------------------------------------------------------------
EXPERIMENTS = [
    {
        # Expérience 1 : charge standard, balayage N = 2..20 stations par pas de 2.
        # Paramètres : λ = 20 pkt/s, W_min = 15 (défaut), K_max = 15 (défaut).
        "name": "Cas standard — balayage du nombre de stations (λ=20 pkt/s)",
        "args": [
            "--sweep-stations", "2", "20", "2",
            "--arrival-rate", "20",
            "--runs", "3",            # Moyenne sur 3 répétitions pour réduire la variance
            "--simulation-time", "5",
            "--seed", "42",           # Graine fixe pour la reproductibilité
            "--output", str(FIGURES / "moderate_load_vs_stations.svg"),
            "--csv",   str(DATA    / "moderate_load_vs_stations.csv"),

        ],
    },
    {
        # Expérience 2 : forte charge (λ = 200 pkt/s), même balayage N = 2..20.
        # Permet d'observer la saturation du canal et la montée des collisions.
        "name": "Forte charge — balayage du nombre de stations (λ=200 pkt/s)",
        "args": [
            "--sweep-stations", "2", "20", "2",
            "--arrival-rate", "200",
            "--runs", "3",
            "--simulation-time", "5",
            "--seed", "42",
            "--output", str(FIGURES / "high_load_vs_stations.svg"),
            "--csv",   str(DATA    / "high_load_vs_stations.csv"),

        ],
    },
    {
        # Expérience 3 : impact de la fenêtre de contention minimale W_min.
        # W_min balaie 3..63 par pas de 5, avec 15 stations à charge modérée (λ = 80 pkt/s).
        # Montre l'existence d'un W_min optimal minimisant les collisions sans trop payer en délai.
        "name": "Impact de W_min (15 stations, λ=80 pkt/s)",
        "args": [
            "--sweep-wmin", "3", "63", "5",
            "--stations", "15",
            "--arrival-rate", "80",
            "--runs", "3",
            "--simulation-time", "5",
            "--seed", "42",
            "--output", str(FIGURES / "impact_wmin.svg"),
            "--csv",   str(DATA    / "impact_wmin.csv"),
        ],
    },
    {
        # Expérience 4 : impact du nombre maximal de tentatives K_max.
        # K_max balaie 1..20 par pas de 1, avec 15 stations à forte charge (λ = 150 pkt/s).
        # Un K_max trop faible entraîne des abandons prématurés ; trop élevé, le délai explose.
        "name": "Impact de K_max (15 stations, λ=150 pkt/s)",
        "args": [
            "--sweep-kmax", "1", "20", "1",
            "--stations", "15",
            "--arrival-rate", "150",
            "--runs", "3",
            "--simulation-time", "5",
            "--seed", "42",
            "--output", str(FIGURES / "impact_kmax.svg"),
            "--csv",   str(DATA    / "impact_kmax.csv"),
        ],
    },
    {
        # Expérience 5 : protocole avec mécanisme RTS/CTS activé, charge standard (λ = 20 pkt/s).
        # Permet de comparer les performances avec et sans RTS/CTS (référence : expérience 1).
        "name": "Mécanisme RTS/CTS — balayage du nombre de stations (λ=20 pkt/s)",
        "args": [
            "--sweep-stations", "2", "20", "2",
            "--rtscts",
            "--arrival-rate", "20",
            "--runs", "3",
            "--simulation-time", "5",
            "--seed", "42",
            "--output", str(FIGURES / "rtscts_vs_stations.svg"),
            "--csv",   str(DATA    / "rtscts_vs_stations.csv"),

        ],
    },
]


def main() -> None:
    """Point d'entrée du script : exécute toutes les expériences en séquence.

    Pour chaque expérience définie dans EXPERIMENTS :
      1. Affiche la progression dans la console (ex. [1/5] Nom de l'expérience).
      2. Invoque csma_ca_sim.py en sous-processus avec les arguments définis.
      3. Lève CalledProcessError si le simulateur se termine avec un code d'erreur.

    Après exécution complète, affiche un résumé des dossiers de sortie.
    """
    total = len(EXPERIMENTS)  # Nombre total d'expériences à exécuter
    for i, exp in enumerate(EXPERIMENTS, 1):
        print(f"\n[{i}/{total}] {exp['name']}")
        # Lance csma_ca_sim.py en sous-processus ; check=True interrompt le script
        # immédiatement si le simulateur retourne un code d'erreur non nul.
        subprocess.run([PYTHON, SIM] + exp["args"], check=True)
    print(f"\nTerminé. {total} expériences générées dans {FIGURES}/ et {DATA}/.") 

# Point d'entrée : exécution directe uniquement (pas lors d'un import)
if __name__ == "__main__":
    main()
