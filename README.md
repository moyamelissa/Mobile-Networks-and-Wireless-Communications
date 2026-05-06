# Simulateur CSMA/CA à événements discrets

[![Tests](https://github.com/moyamelissa/Mobile-Networks-and-Wireless-Communications/actions/workflows/tests.yml/badge.svg)](https://github.com/moyamelissa/Mobile-Networks-and-Wireless-Communications/actions)
[![Coverage](https://img.shields.io/badge/coverage-94%25-green)]()
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()


## Présentation

Ce projet propose un simulateur à événements discrets du protocole CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance), utilisé dans les réseaux Wi-Fi IEEE 802.11.  
Le programme modélise plusieurs stations partageant un canal et permet d’analyser :

- le débit (throughput)
- le taux de collision
- le délai moyen

Un mode optionnel RTS/CTS est disponible pour comparaison.

---

## Utilisation rapide

Simulation simple :

```bash
python csma_ca_sim.py --stations 4 --arrival-rate 20 --simulation-time 5
```

Génération d’un graphique paramétrique :

```bash
python csma_ca_sim.py --sweep-stations 2 20 2 --runs 3 --output resultats.svg
```

Activer le mode RTS/CTS :

```bash
python csma_ca_sim.py --stations 8 --arrival-rate 50 --rtscts
```

---

## Paramètres principaux

| Paramètre             | Description                                              |
|-----------------------|----------------------------------------------------------|
| --stations            | Nombre de stations en compétition                        |
| --arrival-rate        | Taux d’arrivée des paquets par station                   |
| --simulation-time     | Durée totale de la simulation (secondes)                 |
| --wmin, --wmax        | Fenêtre de contention minimale et maximale (backoff)     |
| --rtscts              | Active le mode RTS/CTS                                   |

---

## Tests

Lancer les tests unitaires :

```bash
python -m pytest test_csma_ca_sim.py
```

---

## Structure du projet

```
csma_ca_sim.py         # Simulateur principal
test_csma_ca_sim.py    # Tests unitaires
Graphiques/            # Graphiques SVG générés
RAPPORT.md             # Rapport académique
README.md              # Documentation rapide
```

---

## Licence

MIT — Utilisation libre pour un usage académique ou commercial.

---

2026 – Projet académique, Réseaux Mobiles et Communications Sans Fil
