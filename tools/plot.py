"""Génération de graphiques SVG pour les résultats du simulateur CSMA/CA.

Ce module est indépendant du moteur de simulation : il reçoit une liste de
points expérimentaux (ExperimentPoint) et produit un fichier SVG autonome
à trois panneaux (débit, taux de collision, délai moyen).

Usage depuis un autre module :
    from plot import plot_points
    plot_points(points, title=None, x_label="Nombre de stations", output_path=Path("out.svg"))
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from xml.sax.saxutils import escape

if TYPE_CHECKING:
    from csma_ca_sim import ExperimentPoint


def _format_y_label(value: float) -> str:
    """Formate une valeur d'axe Y de façon compacte.

    - Millions  : « 9.64M »
    - Milliers  : « 123k »
    - Autres    : affichage décimal court (supprime les zéros superflus)
    """
    if value == 0:
        return "0"
    abs_v = abs(value)
    if abs_v >= 1_000_000:
        s = f"{value / 1_000_000:.2f}M"
    elif abs_v >= 1_000:
        s = f"{value / 1_000:.1f}k"
    else:
        # Affiche au plus 2 décimales ; supprime les zéros de fin
        s = f"{value:.2f}".rstrip("0").rstrip(".")
    return s


def plot_points(
    points: list[ExperimentPoint],
    title: Optional[str],
    x_label: str,
    output_path: Path,
) -> None:
    """Génère un graphique SVG à trois panneaux (débit, taux de collision, délai moyen).

    Le SVG est auto-contenu (pas de dépendance externe) et s'affiche directement
    dans un navigateur ou peut être intégré dans un rapport PDF.

    Args:
        points:      Liste de points expérimentaux (un par valeur de paramètre).
        title:       Titre principal affiché en haut du graphique (None = pas de titre).
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
    top_margin = 80 if title else 20
    panel_gap = 55
    inner_left = 115       # largeur réservée à l'axe Y (labels + libellé rotatif)
    inner_right = 30
    inner_top = 55
    inner_bottom = 52

    # Blue/purple light-theme palette: (couleur trait, opacité haut zone, opacité bas zone)
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
        """Convertit l'indice d'un point en coordonnée X SVG."""
        plot_w = panel_width - inner_left - inner_right
        if count == 1:
            return left + inner_left + plot_w / 2
        return left + inner_left + (plot_w * index / (count - 1))

    def scale_y(value: float, minimum: float, maximum: float, panel_top: float) -> float:
        """Convertit une valeur de données en coordonnée Y SVG (axe inversé)."""
        plot_h = panel_height - inner_top - inner_bottom
        if math.isclose(minimum, maximum):  # pragma: no cover
            return panel_top + inner_top + plot_h / 2  # pragma: no cover
        return panel_top + inner_top + (maximum - value) * plot_h / (maximum - minimum)

    def format_ticks(minimum: float, maximum: float, count: int = 5) -> list[float]:
        """Calcule les valeurs des graduations régulièrement espacées sur l'axe Y."""
        if math.isclose(minimum, maximum):  # pragma: no cover
            return [minimum]  # pragma: no cover
        step = (maximum - minimum) / (count - 1)
        return [minimum + step * index for index in range(count)]

    def smooth_curve(coords: list[tuple[float, float]]) -> str:
        """Génère un chemin SVG lissé (spline Catmull-Rom → Bézier cubique)."""
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
            parts.append(
                f"C{cp1x:.2f},{cp1y:.2f} {cp2x:.2f},{cp2y:.2f} {p2[0]:.2f},{p2[1]:.2f}"
            )
        return " ".join(parts)

    # Les définitions SVG (<defs>) sont accumulées ici ; panel_svg y ajoute les dégradés de zone.
    defs_parts: list[str] = []

    def panel_svg(
        panel_index: int,
        panel_top: float,
        panel_title: str,
        y_label: str,
        series: list[tuple[list[float], list[float], int, str]],
        x_label_text: str = "",
    ) -> str:
        """Génère le SVG complet d'un panneau de graphique pour une métrique donnée."""
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

        # Carte (fond blanc arrondi avec bordure et ombre légère)
        el.append(
            f'<rect x="{left}" y="{panel_top}" width="{panel_width}" height="{panel_height}"'
            f' rx="14" fill="#ffffff" stroke="rgba(99,102,241,0.18)" stroke-width="1.2"'
            f' filter="drop-shadow(0 2px 8px rgba(99,102,241,0.08))"/>'
        )

        # Libellé rotatif de l'axe Y (dans la marge gauche, centré verticalement)
        y_center = panel_top + inner_top + (panel_height - inner_top - inner_bottom) / 2
        el.append(
            f'<text x="{left + 15}" y="{y_center:.2f}" text-anchor="middle"'
            f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
            f' font-size="16" fill="#374151"'
            f' transform="rotate(-90,{left + 15:.2f},{y_center:.2f})">'
            f'{escape(panel_title)} ({escape(y_label)})</text>'
        )

        # Lignes de grille horizontales
        for tick_value in format_ticks(y_min, y_max):
            y = scale_y(tick_value, y_min, y_max, panel_top)
            el.append(
                f'<line x1="{plot_left}" y1="{y:.2f}" x2="{plot_left + plot_w}" y2="{y:.2f}"'
                f' stroke="rgba(99,102,241,0.08)" stroke-width="1" stroke-dasharray="4,4"/>'
            )

        # Axes (ligne de base X et ligne de base Y)
        el.append(
            f'<line x1="{plot_left}" y1="{plot_bottom}" x2="{plot_left + plot_w}" y2="{plot_bottom}"'
            f' stroke="#d1d5db" stroke-width="1"/>'
        )
        el.append(
            f'<line x1="{plot_left}" y1="{plot_top}" x2="{plot_left}" y2="{plot_bottom}"'
            f' stroke="#d1d5db" stroke-width="1"/>'
        )

        # Graduations de l'axe Y (format compact : k, M…)
        for tick_value in format_ticks(y_min, y_max):
            y = scale_y(tick_value, y_min, y_max, panel_top)
            el.append(
                f'<text x="{plot_left - 8}" y="{y + 4:.2f}" text-anchor="end"'
                f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
                f' font-size="15" fill="#6b7280">{_format_y_label(tick_value)}</text>'
            )

        # Graduations de l'axe X (valeurs du paramètre balayé)
        for idx, x_value in enumerate(x_values):
            x = scale_x(idx, len(x_values))
            el.append(
                f'<line x1="{x:.2f}" y1="{plot_bottom}" x2="{x:.2f}" y2="{plot_bottom + 4}"'
                f' stroke="#d1d5db" stroke-width="1"/>'
            )
            el.append(
                f'<text x="{x:.2f}" y="{plot_bottom + 18}" text-anchor="middle"'
                f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
                f' font-size="15" fill="#6b7280">{x_value}</text>'
            )

        # Libellé centré de l'axe X (sous les graduations)
        if x_label_text:
            el.append(
                f'<text x="{plot_left + plot_w / 2:.2f}" y="{plot_bottom + 36:.2f}"'
                f' text-anchor="middle"'
                f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
                f' font-size="16" fill="#374151">{escape(x_label_text)}</text>'
            )

        # Tracé de chaque série (courbe lissée, zone, barres d'erreur, points)
        for si, (values, stds, ci, label) in enumerate(series):
            stroke_color = PALETTE[ci][0]
            area_op_top = PALETTE[ci][1]
            area_op_bot = PALETTE[ci][2]

            coords = [
                (scale_x(idx, len(x_values)), scale_y(v, y_min, y_max, panel_top))
                for idx, v in enumerate(values)
            ]

            # Enregistrement du dégradé de zone dans <defs>
            grad_id = f"areaGrad_p{panel_index}_s{si}"
            defs_parts.append(
                f'<linearGradient id="{grad_id}" x1="0" y1="{plot_top:.2f}"'
                f' x2="0" y2="{plot_bottom:.2f}" gradientUnits="userSpaceOnUse">'
            )
            defs_parts.append(
                f'  <stop offset="0%" stop-color="{stroke_color}" stop-opacity="{area_op_top}"/>'
            )
            defs_parts.append(
                f'  <stop offset="100%" stop-color="{stroke_color}" stop-opacity="{area_op_bot}"/>'
            )
            defs_parts.append("</linearGradient>")

            # Zone de remplissage sous la courbe
            curve_d = smooth_curve(coords)
            area_d = (
                f"{curve_d}"
                f" L{coords[-1][0]:.2f},{plot_bottom:.2f}"
                f" L{coords[0][0]:.2f},{plot_bottom:.2f} Z"
            )
            el.append(f'<path d="{area_d}" fill="url(#{grad_id})" stroke="none"/>')

            # Halo lumineux derrière la ligne (effet de profondeur)
            el.append(
                f'<path d="{curve_d}" fill="none" stroke="{stroke_color}"'
                f' stroke-width="8" stroke-opacity="0.18"'
                f' stroke-linecap="round" stroke-linejoin="round"/>'
            )
            # Ligne principale de la courbe
            el.append(
                f'<path d="{curve_d}" fill="none" stroke="{stroke_color}"'
                f' stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>'
            )

            # Barres d'erreur (±1 σ)
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

            # Points de données : anneau de halo + disque central plein
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
    title_element = (
        f'<text x="{width / 2}" y="56" text-anchor="middle"'
        f' font-family="system-ui,\'Segoe UI\',Arial,sans-serif"'
        f' font-size="24" font-weight="700" fill="#1e1b4b" letter-spacing="0.4">'
        f"{escape(title)}</text>"
        if title
        else ""
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <defs>
  {defs_xml}
  </defs>
  <rect width="100%" height="100%" fill="#ffffff"/>
  {title_element}
  {throughput_panel}
  {collision_panel}
  {delay_panel}
  <text x="{width - 20}" y="{height - 14}" text-anchor="end"
    font-family="system-ui,'Segoe UI',Arial,sans-serif"
    font-size="13" fill="#9ca3af">csma_ca_sim.py</text>
</svg>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding="utf-8")
