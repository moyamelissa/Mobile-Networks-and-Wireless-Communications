# Figure 2 — Protocole CSMA/CA avec backoff exponentiel binaire

> **Rendu** : ce fichier s'affiche avec les diagrammes dans VS Code (extension *Markdown Preview Mermaid Support*) et sur GitHub.  
> **Pour Visio** : utilisez le tableau de correspondance des formes en bas de page.

---

## Diagramme principal (mode de base, sans RTS/CTS)

```mermaid
flowchart TD
    A([Arrivée d'un paquet]):::terminal
    B["Initialiser\nW ← W_min,  K ← 0\nb ← U[0, W]"]:::action
    C{"Canal libre ?\n(aucune transmission\nen cours)"}:::decision
    D["Attendre\n(canal occupé)"]:::action
    E["Décrémenter\nb ← b − 1"]:::action
    F{"b = 0 ?"}:::decision
    G["Transmission\ndu paquet\n(durée T_data)"]:::action
    H{"Collision ?\n(plusieurs stations\nà b = 0 simultané)"}:::decision
    I([Transmission réussie\nW ← W_min,  K ← 0]):::success
    J["K ← K + 1"]:::action
    K{"K > K_max ?"}:::decision
    L([Paquet abandonné\n— perdu —\nW ← W_min,  K ← 0]):::failure
    M["Augmenter la fenêtre\nW ← min(2W + 1, W_max)\nb ← U[0, W]"]:::action
    N["Attendre DIFS\navant reprise\nde la contention"]:::wait

    A --> B
    B --> C
    C -- NON --> D
    D --> C
    C -- OUI --> E
    E --> F
    F -- NON --> C
    F -- OUI --> G
    G --> H
    H -- NON --> I
    H -- OUI --> J
    J --> K
    K -- OUI --> L
    K -- NON --> M
    M --> N
    N --> C

    classDef terminal  fill:#a8d5a2,stroke:#3a7d44,color:#1a3a1a,font-weight:bold,rx:30
    classDef action    fill:#aec6e8,stroke:#2c5f8a,color:#0d1f33
    classDef decision  fill:#f7c59f,stroke:#b85c00,color:#3b1a00,font-style:italic
    classDef success   fill:#a8d5a2,stroke:#3a7d44,color:#1a3a1a,font-weight:bold,rx:30
    classDef failure   fill:#f4a7a7,stroke:#8b0000,color:#3b0000,font-weight:bold,rx:30
    classDef wait      fill:#e8d5f0,stroke:#6a3d8a,color:#2d1040
```

---

## Extension RTS/CTS (mode optionnel)

```mermaid
flowchart TD
    A([b = 0 — prêt à émettre]):::terminal
    B["Envoyer RTS\n(durée T_RTS)"]:::action
    C{"Collision RTS ?\n(plusieurs RTS simultanés)"}:::decision
    D["K ← K + 1"]:::action
    E{"K > K_max ?"}:::decision
    F([Paquet abandonné]):::failure
    G["W ← min(2W+1, W_max)\nb ← U[0, W]\nAttendre DIFS"]:::action
    H["Recevoir CTS\n(durée T_SIFS + T_CTS)"]:::action
    I["Autres stations :\nNAV ← t_fin_données\n(blocage médium)"]:::wait
    J["Transmission données\n(durée T_SIFS + T_data)"]:::action
    K([Transmission réussie\nW ← W_min,  K ← 0]):::success

    A --> B
    B --> C
    C -- OUI --> D
    D --> E
    E -- OUI --> F
    E -- NON --> G
    G --> A
    C -- NON --> H
    H --> I
    I --> J
    J --> K

    classDef terminal  fill:#a8d5a2,stroke:#3a7d44,color:#1a3a1a,font-weight:bold,rx:30
    classDef action    fill:#aec6e8,stroke:#2c5f8a,color:#0d1f33
    classDef decision  fill:#f7c59f,stroke:#b85c00,color:#3b1a00,font-style:italic
    classDef success   fill:#a8d5a2,stroke:#3a7d44,color:#1a3a1a,font-weight:bold,rx:30
    classDef failure   fill:#f4a7a7,stroke:#8b0000,color:#3b0000,font-weight:bold,rx:30
    classDef wait      fill:#e8d5f0,stroke:#6a3d8a,color:#2d1040
```

---

## Correspondance des formes pour Visio

| Couleur / style dans le diagramme | Forme Visio recommandée | Remplissage | Exemples de nœuds |
|---|---|---|---|
| **Vert** — ovale | **Terminateur** (début / fin) | `#a8d5a2` (vert pastel) | Arrivée d'un paquet, Transmission réussie, Paquet abandonné |
| **Bleu** — rectangle | **Processus / Action** | `#aec6e8` (bleu pastel) | Initialiser, Décrémenter b, Transmission du paquet, K ← K + 1 |
| **Orange** — losange | **Décision** | `#f7c59f` (orange pastel) | Canal libre ?, b = 0 ?, Collision ?, K > K_max ? |
| **Violet** — rectangle | **Délai / Attente** | `#e8d5f0` (violet pastel) | Attendre DIFS, NAV ← t_fin |
| **Rouge** — ovale | **Fin d'erreur** | `#f4a7a7` (rouge pastel) | Paquet abandonné (RTS/CTS) |

### Polices et flèches recommandées pour Visio
- Police : **Calibri 10 pt**, centré dans la forme
- Flèches : connecteurs droits, étiquette **OUI / NON** en Calibri 9 pt italique sur la branche
- Largeur de forme : processus 3,5 cm × 1,2 cm / décision 3 cm × 1,5 cm / terminateur 3 cm × 0,9 cm (rayon 0,45 cm)
- Espacement vertical entre formes : 1 cm

---

*Référence code : `_handle_slot_tick`, `_handle_data_end`, `_handle_rts_end`, `_prime_station_for_contention` dans `csma_ca_sim.py`*
