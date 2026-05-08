# Rapport — Simulation du protocole CSMA/CA à événements discrets

**Cours :** Réseaux Mobiles et Communications Sans Fil  
**Responsable :** Essaid Sabir, Ph.D.  
**Période :** Semaines 10–12  

---

## Table des matières

1. [Introduction](#1-introduction)
2. [Méthodologie générale et étapes de conception](#2-méthodologie-générale-et-étapes-de-conception)
3. [Résumé du protocole CSMA/CA implémenté](#3-résumé-du-protocole-csmaca-implémenté)
4. [Architecture du simulateur](#4-architecture-du-simulateur)
5. [Choix techniques](#5-choix-techniques)
6. [Résultats et analyse](#6-résultats-et-analyse)
7. [Conclusion](#7-conclusion)
8. [Annexe — Code source commenté](#8-annexe--code-source-commenté)

---

## 1. Introduction

Les réseaux sans fil reposent sur des mécanismes efficaces de partage du médium afin de permettre à plusieurs stations de communiquer sur un même canal. Parmi ces mécanismes, le protocole CSMA/CA (Carrier Sense Multiple Access with Collision Avoidance) joue un rôle central dans les réseaux de type IEEE 802.11 (Wi-Fi), en assurant une gestion équitable de l'accès au canal et en limitant les collisions.

Dans ce contexte, ce projet propose la conception et la mise en œuvre d'un simulateur à événements discrets du protocole CSMA/CA, visant à modéliser spécifiquement le fonctionnement de la couche MAC dans un environnement sans fil. Afin de simplifier le modèle, l'écoute du canal (*carrier sensing*) est réalisée en supposant que les compteurs de backoff de toutes les stations sont globalement accessibles, ce qui permet de ne pas modéliser explicitement la couche physique. Par ailleurs, l'environnement est considéré comme non persistant et les collisions ne peuvent pas être détectées pendant l'émission, mais seulement après la fin de la transmission.

L'objectif est de reproduire le comportement de plusieurs stations en compétition pour l'accès au canal et d'évaluer les performances du protocole à l'aide de différentes métriques : le débit, le taux de collision et le délai moyen de transmission. Le trafic généré par les stations est modélisé par un processus de Poisson, permettant de représenter des arrivées de paquets à caractère aléatoire et statistiquement homogène. De plus, conformément aux hypothèses simplificatrices du modèle, chaque station ne maintient qu'un seul paquet en attente à la fois et ne génère pas de nouvelle trame avant que la précédente n'ait été transmise avec succès ou abandonnée après dépassement du nombre maximal de tentatives.

Une extension intégrant le mécanisme RTS/CTS et la réservation du médium par NAV est également étudiée afin de comparer son impact sur le comportement global du système, notamment en termes de débit et de taux de collision.

Le simulateur permet d'analyser l'effet de différents paramètres du protocole : le nombre de stations, les bornes de la fenêtre de contention (W_min, W_max), le nombre maximal de retransmissions (K_max) et la durée des temporisations (DIFS, SIFS, *slot time*). Le modèle implémente en particulier l'algorithme de **backoff exponentiel binaire** (*Binary Exponential Backoff*, BEB), dans lequel la fenêtre de contention est doublée à chaque collision selon la règle W ← min(2W + 1, W_max), jusqu'à atteindre un plafond.

Le présent rapport est organisé comme suit. La section 2 présente la méthodologie générale et les étapes de conception. La section 3 résume le protocole CSMA/CA implémenté. La section 4 décrit l'architecture du simulateur. La section 5 justifie les choix techniques retenus. La section 6 présente les résultats de simulation et leur analyse. La section 7 conclut le rapport. Le code source entièrement commenté est fourni en annexe (section 8).

---

## 2. Méthodologie générale et étapes de conception

Le développement du simulateur s'appuie sur une approche progressive visant à modéliser de manière fidèle le fonctionnement du protocole CSMA/CA tout en conservant une structure simple et modulable. La méthodologie adoptée repose sur la décomposition du système en plusieurs étapes de conception clairement définies, comme illustré à la Figure 1.

> *Figure 1 — Étapes de conception du simulateur CSMA/CA (à insérer ici)*

Dans un premier temps, le choix d'un modèle à événements discrets a été retenu afin de représenter l'évolution du système dans le temps. Cette approche permet de simuler efficacement les interactions entre les différentes stations en ne traitant que les événements significatifs, tels que les arrivées de paquets, les tentatives de transmission, les mises à jour de backoff et les fins de transmission. Concrètement, ces événements sont structurés sous forme d'actions discrètes qui permettent de découper le temps en unités pertinentes, notamment le *slot time*, le DIFS et le SIFS du protocole.

Dans un deuxième temps, un modèle de station a été défini afin de représenter le comportement individuel de chaque participant du réseau. Chaque station maintient son propre état, incluant le paquet en attente, son compteur de backoff, le nombre de tentatives de retransmission ainsi que les mécanismes de temporisation liés au protocole. L'écoute du canal est réalisée de manière abstraite en supposant que les compteurs de backoff de toutes les stations sont globalement accessibles, ce qui permet de modéliser le mécanisme de *carrier sensing* sans recourir à un modèle physique détaillé. Conformément aux hypothèses du modèle, chaque station ne maintient qu'un seul paquet à la fois : aucune nouvelle trame n'est générée tant que le paquet courant n'a pas été transmis avec succès ou abandonné suite au dépassement du nombre maximal de tentatives K_max.

Dans un troisième temps, la logique du protocole CSMA/CA a été implémentée, notamment l'algorithme de backoff exponentiel binaire, la gestion des collisions et la retransmission des paquets en cas d'échec. Une extension intégrant le mécanisme RTS/CTS a également été ajoutée afin de permettre une comparaison entre différentes stratégies d'accès au médium. Le fonctionnement détaillé de cet algorithme est présenté à la Figure 2 (section 3).

Dans un quatrième temps, un ensemble d'expériences a été défini en faisant varier les paramètres du système : le nombre de stations, le taux d'arrivée des paquets, la taille de la fenêtre de contention et les temporisations (DIFS, SIFS et *slot time*). Afin d'assurer la fiabilité des résultats, chaque configuration est simulée plusieurs fois et les résultats sont moyennés, ce qui permet de réduire l'impact des fluctuations aléatoires inhérentes au modèle stochastique.

Enfin, les résultats obtenus ont été analysés à l'aide de métriques pertinentes — débit, taux de collision et délai moyen — afin d'évaluer les performances du protocole et d'identifier ses limites. L'ensemble du simulateur a été implémenté en Python, en utilisant une file de priorité (*heap*) pour la gestion des événements, garantissant un traitement chronologique cohérent.

---

## 3. Résumé du protocole CSMA/CA implémenté

Cette section décrit précisément les règles du protocole tel qu'il est implémenté dans le simulateur, en distinguant le mode de base et l'extension RTS/CTS. Les valeurs par défaut des paramètres sont celles du standard IEEE 802.11b et sont récapitulées dans le tableau suivant.

| Paramètre | Symbole | Valeur par défaut | Description |
|---|---|---|---|
| Slot time | $T_{\text{slot}}$ | 20 µs | Durée d'un slot de backoff |
| DIFS | $T_{\text{DIFS}}$ | 50 µs | Attente minimale avant toute contention |
| SIFS | $T_{\text{SIFS}}$ | 10 µs | Attente courte entre trames d'un même échange |
| Durée de paquet | $T_{\text{data}}$ | 1 ms | Durée de transmission d'une trame de données |
| Taille de paquet | — | 12 000 bits | Taille fixe de chaque trame |
| Fenêtre minimale | $W_{\min}$ | 15 | Fenêtre de contention initiale |
| Fenêtre maximale | $W_{\max}$ | 1 023 | Plafond de la fenêtre de contention |
| Tentatives max. | $K_{\max}$ | 15 | Nombre d'échecs avant abandon du paquet |
| Durée RTS | $T_{\text{RTS}}$ | 200 µs | Durée d'une trame RTS (mode RTS/CTS) |
| Durée CTS | $T_{\text{CTS}}$ | 200 µs | Durée d'une trame CTS (mode RTS/CTS) |

### 3.1 Génération du trafic

Chaque station génère des paquets de manière indépendante selon un processus de Poisson de paramètre $\lambda$ (paquets/s). Les intervalles entre arrivées sont donc distribués exponentiellement de moyenne $1/\lambda$. Conformément à l'hypothèse du sujet, **une station ne génère pas de nouveau paquet tant que le paquet courant n'a pas été transmis avec succès ou abandonné**. Le prochain événement d'arrivée n'est planifié qu'après résolution du paquet actif.

### 3.2 Phase de contention initiale

À l'arrivée d'un paquet, la station initialise ses compteurs :

$$W \leftarrow W_{\min}, \quad K \leftarrow 0, \quad b \leftarrow \text{Uniforme}[0,\, W]$$

où $b$ est le compteur de backoff tiré aléatoirement et uniformément dans la fenêtre de contention courante. La station est alors ajoutée à l'ensemble des *contendants actifs*.

### 3.3 Décrémentation du backoff et écoute du canal

Le canal est découpé en slots de durée $T_{\text{slot}}$. Avant toute contention, le canal doit rester libre pendant une durée DIFS ; ceci est modélisé par le paramètre `contention_open_time`, qui empêche tout *slot tick* avant $t_{\text{fin transmission}} + T_{\text{DIFS}}$.

À chaque *slot tick*, chaque station contendante dont le NAV est expiré décrémente son compteur :

$$b \leftarrow b - 1$$

Le canal est considéré libre de manière abstraite : si aucune transmission n'est en cours (`current_transmission = None`), les stations peuvent décrémenter. Cette hypothèse, explicitement autorisée par le sujet, évite de modéliser la propagation physique du signal.

### 3.4 Tentative de transmission

Lorsqu'une station atteint $b = 0$, elle tente de transmettre son paquet. Deux cas se présentent selon le nombre de stations ayant atteint $b = 0$ simultanément lors du même slot.

**Transmission réussie** ($|$contendants prêts$|$ $= 1$) : La trame de données est transmise pendant $T_{\text{data}}$, suivie d'un silence de $T_{\text{SIFS}}$. À la fin, la station reçoit implicitement l'acquittement et libère le canal. Ses compteurs sont réinitialisés :

$$W \leftarrow W_{\min}, \quad K \leftarrow 0$$

Une nouvelle période de contention peut démarrer après $T_{\text{DIFS}}$.

**Collision logique** ($|$contendants prêts$|$ $\geq 2$) : Plusieurs stations ont atteint $b = 0$ au même instant — c'est la définition de la collision dans ce modèle non persistant où les collisions ne peuvent être détectées que post-transmission. Chaque station impliquée incrémente son compteur de tentatives $K \leftarrow K + 1$ et applique l'algorithme de **backoff exponentiel binaire** (BEB) :

$$W \leftarrow \min(2W + 1,\; W_{\max}), \quad b \leftarrow \text{Uniforme}[0,\, W]$$

Si $K > K_{\max}$, le paquet est **abandonné** : la station réinitialise ses compteurs ($W \leftarrow W_{\min}$, $K \leftarrow 0$) et planifie l'arrivée du prochain paquet.

### 3.5 Extension RTS/CTS et mécanisme NAV

En mode RTS/CTS (activé par l'option `--rtscts`), la station ne transmet pas directement ses données quand $b = 0$ : elle envoie d'abord une trame **RTS** de durée $T_{\text{RTS}}$.

- **Collision sur le RTS** : même règle BEB que pour une collision de données.
- **RTS réussi** : le point d'accès répond par un **CTS** après $T_{\text{SIFS}}$. La durée totale réservée est :

$$t_{\text{fin données}} = t_{\text{RTS\_end}} + T_{\text{SIFS}} + T_{\text{CTS}} + T_{\text{SIFS}} + T_{\text{data}}$$

Toutes les autres stations reçoivent le CTS et positionnent leur **NAV** (*Network Allocation Vector*) à $t_{\text{fin données}}$ : elles s'interdisent toute décrémentation de backoff jusqu'à cette échéance, ce qui protège l'échange de données contre les interférences.

### 3.6 Hypothèses simplificatrices

Le modèle implémenté repose sur les hypothèses suivantes, conformes au sujet :

1. **Pas de couche physique** : l'état du canal est déduit de l'état interne du simulateur (absence de transmission en cours) ; aucun modèle de propagation n'est utilisé.
2. **Collision logique** : une collision se produit si et seulement si deux stations ou plus atteignent $b = 0$ lors du même *slot tick*.
3. **Un seul paquet par station** : aucune nouvelle trame n'est générée tant que la précédente n'est pas résolue.
4. **Pas de RTS/CTS par défaut** : le mode de base ne comprend ni réservation de canal ni NAV ; ces mécanismes sont une extension optionnelle.

---

## 4. Architecture générale du simulateur

Le simulateur développé repose sur une architecture modulaire permettant de représenter de manière structurée le fonctionnement du protocole CSMA/CA. Cette organisation facilite à la fois l'implémentation du modèle et l'analyse des interactions entre les différentes composantes du système. L'ensemble repose sur trois éléments principaux : un moteur à événements discrets, un modèle de stations et un module de calcul de métriques.

### 4.1 Moteur de simulation à événements discrets

Le cœur du simulateur repose sur un moteur à événements discrets permettant de modéliser l'évolution temporelle du système. Dans cette approche, le temps progresse de manière discontinue en fonction des événements significatifs qui surviennent : arrivée d'un paquet dans une station, progression d'un slot (*slot tick*), fin d'une transmission de données (*data end*) ou fin d'un échange RTS (*rts end*). Ce découpage en événements nommés permet de représenter précisément chaque instant pertinent de la simulation sans avoir à itérer sur chaque unité de temps.

Les événements sont gérés au moyen d'une file de priorité, implémentée à l'aide du module `heapq` de Python, qui garantit leur traitement dans l'ordre chronologique strict. Chaque entrée de la file est un n-uplet `(temps, numéro_de_séquence, type, station, jeton)`, où le numéro de séquence brise les égalités de temps de manière déterministe et le jeton permet d'invalider les événements *slot tick* périmés sans les retirer physiquement de la file.

Cette structure confère au simulateur une grande flexibilité : l'ajout d'un nouveau type d'événement (RTS/CTS, par exemple) se limite à l'ajout d'un gestionnaire dédié, sans modifier le moteur central.

### 4.2 Modèle des stations

Le simulateur considère un ensemble de stations indépendantes partageant un même canal de communication. Chaque station est représentée par un état interne `StationState` qui évolue au cours de la simulation et contient les champs suivants :

| Champ | Rôle |
|---|---|
| `packet` | Trame active en attente de transmission (`None` si la station est idle) |
| `backoff` | Valeur courante du compteur de backoff (en slots) |
| `contention_window` | Fenêtre de contention courante W |
| `retries` | Nombre de tentatives échouées pour le paquet courant |
| `nav_until` | Temps jusqu'auquel la station est bloquée par le NAV (mode RTS/CTS) |

Conformément à l'hypothèse du sujet, chaque station ne maintient qu'**un seul paquet actif à la fois**. Aucune nouvelle trame n'est générée tant que le paquet courant n'a pas été transmis avec succès ou abandonné après dépassement de K_max tentatives. Le comportement des stations est également régi par les paramètres temporels du standard IEEE 802.11 : DIFS, SIFS et *slot time*, tous paramétrables à l'exécution.

### 4.3 Implémentation du protocole CSMA/CA

La logique du protocole CSMA/CA est intégrée directement dans le comportement des stations et du moteur d'événements. Lorsqu'un paquet est prêt à être transmis, la station tire un délai de backoff aléatoire uniforme dans l'intervalle $[0, W]$ et entre en phase de contention. Ce processus repose sur une prise de décision entièrement distribuée : chaque station agit de manière autonome sans coordination centrale.

L'écoute du canal est modélisée de manière abstraite : l'état des compteurs de backoff de toutes les stations est globalement accessible, ce qui permet de détecter la disponibilité du canal sans recourir à un modèle de couche physique. Le système est non persistant ; les collisions ne sont détectées qu'après la fin de la tentative de transmission.

À chaque *slot tick*, le compteur de backoff de chaque station contendante est décrémenté d'une unité. Lorsqu'une station atteint un compteur nul, elle tente de transmettre son paquet. Une **collision logique** se produit lorsque plusieurs stations atteignent simultanément un compteur nul lors du même slot. Dans ce cas, les stations concernées déclenchent une nouvelle phase de backoff selon la règle du BEB : $W \leftarrow \min(2W + 1, W_{\max})$. Ce mécanisme adaptatif stabilise le système même sous forte charge.

> *Figure 2 — Fonctionnement du protocole CSMA/CA avec algorithme de backoff (à insérer ici)*

La figure ci-dessus illustre le flux décisionnel principal du protocole : sélection du backoff b dans [0, W] à l'arrivée du paquet (avec W = W_min initialement), décrémentation slot par slot tant que le canal est libre, tentative de transmission quand b = 0, puis bifurcation selon qu'une collision est détectée ou non. Par souci de lisibilité, la figure présente une version simplifiée ; le comportement complet implémenté dans le code comporte trois éléments supplémentaires :

1. **Attente DIFS** : après toute fin de transmission, le canal doit rester libre pendant T_DIFS avant que les stations puissent recommencer à décrémenter leur backoff.
2. **Plafond W_max** : lors d'une collision, la fenêtre de contention est doublée selon W ← min(2W + 1, W_max), ce qui garantit que W ne dépasse jamais W_max.
3. **Compteur de tentatives K / abandon** : chaque collision incrémente un compteur K. Lorsque K > K_max, le paquet est **abandonné** (comptabilisé comme perdu) et la station réinitialise ses paramètres (W ← W_min, K ← 0) avant de traiter le prochain paquet. Ce mécanisme évite qu'un paquet bloque indéfiniment le système sous forte charge.

Une extension intégrant le mécanisme **RTS/CTS** est également implémentée. Cette approche introduit une phase préalable de réservation du canal : la station gagnante envoie d'abord une trame RTS ; si aucune collision ne se produit sur le RTS, le point d'accès répond par un CTS et toutes les autres stations bloquent leur accès pendant la durée de la transmission via le mécanisme **NAV** (*Network Allocation Vector*). Ce mécanisme réduit les collisions sur les données au prix d'un surcoût en temps dû aux échanges RTS/CTS.

### 4.4 Calcul des métriques de performance

Le simulateur intègre un module de collecte et d'agrégation des métriques de performance. Trois indicateurs principaux sont calculés à la fin de chaque simulation.

**Débit** (*throughput*) — nombre de paquets ou de bits transmis avec succès par unité de temps :

$$\text{Débit} = \frac{\text{Paquets réussis}}{\text{Temps de simulation}} \quad [\text{paquets/s}]$$

$$\text{Débit binaire} = \frac{\text{Bits réussis}}{\text{Temps de simulation}} \quad [\text{bits/s}]$$

**Taux de collision** — proportion des tentatives de transmission ayant abouti à une collision :

$$\text{Taux de collision} = \frac{\text{Transmissions en collision}}{\text{Nombre total de tentatives}}$$

**Délai moyen de transmission** — temps moyen écoulé entre la génération d'un paquet et sa transmission réussie :

$$\bar{d} = \frac{\displaystyle\sum_{i=1}^{N_{\text{réussis}}} \left( t_{\text{succès},i} - t_{\text{arrivée},i} \right)}{N_{\text{réussis}}}$$

En complément, le simulateur calcule l'**utilisation du canal** (*channel utilization*), définie comme la fraction du temps de simulation pendant laquelle le médium transporte effectivement des données utiles :

$$U = \frac{N_{\text{réussis}} \times T_{\text{paquet}}}{T_{\text{simulation}}}$$

Lorsque le nombre maximal de tentatives K_max est atteint, le paquet est abandonné et comptabilisé dans les statistiques de paquets perdus. Ces métriques offrent ainsi une vision globale des performances du système et constituent la base quantitative de l'analyse expérimentale présentée en section 6.

---

## 5. Choix techniques

Le développement du simulateur a nécessité plusieurs choix techniques visant à assurer la simplicité de l'implémentation, la clarté du modèle et la reproductibilité des résultats.

**Langage Python.** Le simulateur a été implémenté en Python, un langage largement utilisé en informatique scientifique et adapté au prototypage rapide. Sa syntaxe claire permet de structurer le code de façon modulaire, ce qui facilite la maintenance et l'extension du simulateur. Les types de données natifs (`dataclass`, `heapq`, `random`) couvrent tous les besoins du modèle sans dépendances externes.

**Simulation à événements discrets.** Cette approche, décrite en détail à la section 4.1, a été retenue afin de modéliser le comportement du système sans itérer sur chaque instant de temps. Seuls les événements significatifs sont traités, ce qui rend la simulation efficace même pour des horizons de temps longs.

**File de priorité (`heapq`).** Les événements sont ordonnés selon leur instant d'occurrence grâce au module `heapq` de Python. Un numéro de séquence monotone est ajouté à chaque entrée de la file afin de rompre les égalités de temps de manière déterministe, garantissant ainsi un ordre de traitement stable et reproductible.

**Modèle MAC simplifié.** L'écoute du canal (*carrier sensing*) est réalisée de manière abstraite en supposant que les compteurs de backoff de toutes les stations sont globalement accessibles, ce qui évite de modéliser la couche physique. Conformément au sujet, chaque station ne maintient qu'un seul paquet actif à la fois ; aucune nouvelle trame n'est générée tant que le paquet courant n'est pas résolu, ce qui simplifie la logique d'état sans affecter la fidélité du modèle MAC.

**Reproductibilité.** La possibilité de fixer une graine aléatoire (`--seed`) rend les simulations entièrement déterministes. L'exécution répétée de chaque scénario (`--runs`) avec calcul de la moyenne réduit l'impact des fluctuations statistiques.

**Configurabilité.** Tous les paramètres du système sont exposés en ligne de commande (nombre de stations, taux d'arrivée, durée de simulation, DIFS, SIFS, *slot time*, W_min, W_max, K_max, RTS/CTS), ce qui rend le simulateur directement utilisable pour les expérimentations sans modifier le code source.

---

## 6. Résultats et analyse

Afin d'évaluer les performances du simulateur, plusieurs séries d'expériences ont été réalisées en faisant varier le nombre de stations et les conditions de charge du réseau. Chaque scénario a été exécuté plusieurs fois (`--runs 3`) et les résultats ont été moyennés afin de réduire les fluctuations dues au caractère stochastique de la simulation. Les métriques analysées sont le débit moyen (en bits par seconde), le taux moyen de collision et le délai moyen de transmission.

### 6.1 Cas standard

La Figure 3 présente les résultats obtenus en faisant varier le nombre de stations de 2 à 20, avec un taux d'arrivée standard.

![Figure 3 — Performances du protocole CSMA/CA en fonction du nombre de stations (cas standard)](Graphiques/stations.svg)

> *Figure 3 — Performances du protocole CSMA/CA en fonction du nombre de stations (cas standard)*

On observe que le débit augmente de manière quasi linéaire avec le nombre de stations, atteignant environ 4,9 Mbps pour 20 stations. Cette évolution s'explique par l'augmentation progressive de la charge globale offerte au réseau. Dans ce régime de charge modérée, le protocole CSMA/CA gère efficacement la contention grâce au mécanisme de backoff et à l'espacement entre les transmissions.

Le délai moyen reste faible et n'augmente que légèrement, passant d'environ 1,18 ms à 1,64 ms, ce qui indique que l'accès au canal demeure fluide. Le taux de collision est quasi nul, confirmant que la probabilité de conflit est très faible dans ce scénario. Cette stabilité s'explique en partie par le fait que chaque station ne traite qu'un seul paquet à la fois, ce qui limite la pression exercée sur le canal.

### 6.2 Forte charge

Une seconde série d'expériences a été réalisée avec un taux d'arrivée de paquets plus élevé (`--arrival-rate 60`). Les résultats sont présentés à la Figure 4.

![Figure 4 — Performances du protocole CSMA/CA en situation de forte charge](Graphiques/high_load.svg)

> *Figure 4 — Performances du protocole CSMA/CA en situation de forte charge*

Dans ce scénario, le débit tend à atteindre un plateau à partir d'un certain nombre de stations, se stabilisant autour de 9,5 Mbps, ce qui traduit une saturation du canal. Le délai moyen de transmission augmente fortement, atteignant plus de 11 ms pour 20 stations. Ce phénomène est directement lié à l'algorithme de backoff exponentiel binaire : à chaque collision, la fenêtre de contention est doublée selon la règle

$$W \leftarrow \min(2W + 1, W_{\max})$$

ce qui entraîne des temps d'attente de plus en plus longs à mesure que la charge augmente.

Contrairement à ce que l'on pourrait attendre, le taux de collision reste très faible. Le protocole CSMA/CA évite efficacement les conflits en forçant les stations à attendre avant de retransmettre. La dégradation des performances provient donc principalement de la contention et du temps d'attente, et non des collisions elles-mêmes.

### 6.3 Impact du mécanisme RTS/CTS

Une comparaison avec l'extension RTS/CTS a été effectuée afin d'évaluer l'impact de ce mécanisme sur les performances du système. Les résultats sont illustrés à la Figure 5.

![Figure 5 — Performances du protocole avec mécanisme RTS/CTS](Graphiques/rtscts.svg)

> *Figure 5 — Performances du protocole CSMA/CA avec mécanisme RTS/CTS*

L'introduction du mécanisme RTS/CTS modifie le fonctionnement du protocole en ajoutant une phase de réservation du canal. Le vecteur d'allocation réseau (NAV) permet d'éviter certaines collisions en bloquant temporairement l'accès au canal pour les autres stations une fois le RTS accepté.

Cependant, ce mécanisme introduit un surcoût lié à l'échange des trames RTS et CTS, ce qui réduit le débit utile global (maximum d'environ 4,9 Mbps). Le délai de transmission augmente également en raison de ces étapes supplémentaires. Par ailleurs, des collisions peuvent encore se produire au niveau des trames RTS elles-mêmes, ce qui se traduit par un taux de collision atteignant environ 4,7 % pour 20 stations.

Ainsi, dans un environnement simplifié sans terminal caché, l'utilisation de RTS/CTS ne permet pas nécessairement d'améliorer les performances et peut même les dégrader en raison du surcoût introduit.

### 6.4 Interprétation générale

Les résultats obtenus mettent en évidence plusieurs tendances importantes :

- **Débit** : il croît avec le nombre de stations jusqu'à saturation du canal, reflétant la capacité finie du médium partagé à absorber un trafic croissant.
- **Délai** : il augmente progressivement avec la charge en raison de la contention accrue et de l'allongement des fenêtres de backoff. En régime saturé, la dégradation est principalement causée par la contention et non par les collisions.
- **Taux de collision** : il reste faible en mode standard grâce au BEB, mais devient non négligeable sur les trames RTS en mode RTS/CTS.
- **RTS/CTS** : sans terminaux cachés, le bénéfice de ce mécanisme est limité et ne compense pas le coût des échanges supplémentaires.

Dans l'ensemble, ces résultats confirment l'efficacité du protocole CSMA/CA pour la gestion de la contention sous charge modérée, et illustrent les compromis inhérents entre débit, délai et gestion des conflits lorsque la charge augmente.

---

## 7. Conclusion

Ce projet a permis de développer un simulateur à événements discrets du protocole CSMA/CA, reproduisant les principaux mécanismes de gestion de l'accès au médium dans les réseaux sans fil. À travers cette implémentation, il a été possible de modéliser le comportement de plusieurs stations en compétition pour un canal partagé et d'évaluer les performances du système à l'aide de métriques pertinentes.

Les résultats expérimentaux obtenus mettent en évidence le fonctionnement global du protocole ainsi que ses limites. En particulier, l'augmentation du nombre de stations ou de la charge du réseau entraîne une forte hausse du délai due à la contention, tandis que le taux de collision reste globalement maîtrisé grâce au mécanisme de backoff exponentiel binaire. L'exception notable concerne les trames de contrôle RTS, qui ne bénéficient pas de protection préalable.

L'étude du mécanisme RTS/CTS montre qu'il introduit un compromis entre la réduction des collisions sur les données et la surcharge induite par les échanges supplémentaires. Dans un environnement simplifié sans terminaux cachés, ce mécanisme n'améliore pas nécessairement les performances globales et peut entraîner une augmentation du délai ainsi qu'une réduction du débit utile.

Dans l'ensemble, ce projet a permis de mieux comprendre les principes de fonctionnement du protocole CSMA/CA et les enjeux liés au partage du médium dans les réseaux sans fil. Le simulateur constitue un outil pertinent pour analyser le comportement du protocole et explorer différents scénarios de communication.

---

## Bibliographie

- Python Software Foundation. (2026). *Python Documentation*. Consulté à l'adresse https://docs.python.org

- Sabir, E. (2026). *Notes de cours — Simulation et protocoles réseaux, Module 4 et Module 5*. Université TÉLUQ. *(Vérifier le code de cours exact avant soumission.)*

- IEEE Computer Society. (2020). *IEEE Std 802.11-2020 — IEEE Standard for Information Technology: Wireless LAN Medium Access Control (MAC) and Physical Layer (PHY) Specifications*. IEEE. https://ieeexplore.ieee.org/document/9363693

---

## 8. Annexes

### Annexe A — Commandes de génération des graphiques

Cette annexe présente les commandes utilisées pour générer les graphiques illustrant les performances du simulateur.

**Graphique 1 — Variation du nombre de stations (cas standard)**

```bash
python csma_ca_sim.py --sweep-stations 2 20 2 --runs 3 --simulation-time 5 --output Graphiques/stations.svg
```

| Option | Effet |
|---|---|
| `--sweep-stations 2 20 2` | Fait varier N de 2 à 20 par pas de 2 |
| `--runs 3` | Répète chaque configuration 3 fois et calcule la moyenne |
| `--simulation-time 5` | Durée de simulation de 5 secondes |
| `--output Graphiques/stations.svg` | Enregistre le graphique SVG |

**Graphique 2 — Forte charge**

```bash
python csma_ca_sim.py --sweep-stations 2 20 2 --arrival-rate 60 --runs 3 --simulation-time 5 --output Graphiques/high_load.svg
```

| Option | Effet |
|---|---|
| `--arrival-rate 60` | Simule une charge élevée (60 paquets/s/station) |

**Graphique 3 — Mécanisme RTS/CTS**

```bash
python csma_ca_sim.py --sweep-stations 2 20 2 --rtscts --runs 3 --simulation-time 5 --output Graphiques/rtscts.svg
```

| Option | Effet |
|---|---|
| `--rtscts` | Active le mécanisme RTS/CTS et la réservation NAV |

---

### Annexe B — Dépôt GitHub

Le code source complet du simulateur, les scripts de génération des graphiques et les fichiers de configuration CI/CD sont disponibles à l'adresse suivante :

**[moyamelissa/Mobile-Networks-and-Wireless-Communications](https://github.com/moyamelissa/Mobile-Networks-and-Wireless-Communications)**

Le dépôt inclut :
- `csma_ca_sim.py` — simulateur principal
- `test_csma_ca_sim.py` — suite de tests automatisés (84 tests)
- `README.md` — documentation d'utilisation
- `Graphiques/` — graphiques SVG générés
- `.github/workflows/` — configuration CI/CD

---

### Annexe C — Code source intégralement commenté

> *(Coller ici l'intégralité du contenu de `csma_ca_sim.py` avant la soumission finale du rapport PDF.)*
