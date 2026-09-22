"""Opdrachtregel voor de brieventool.

    python -m brieventool voorbeelden/particulier-wand-enkelvoud.yaml
    python -m brieventool offerte.yaml --docx uit/offerte.docx --sjabloon sjablonen/brief.docx

Zonder --docx wordt alleen de tekst getoond. Dat is de snelste manier om te
controleren of de juiste tekstblokken zijn gekozen.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .bibliotheek import BibliotheekFout, laad
from .controle import melding, ontbrekende_gegevens
from .samenstellen import SamenstelFout, stel_samen
from .sjabloon import SjabloonFout, schrijf_docx


def main(argumenten: list[str] | None = None) -> int:
    ontleder = argparse.ArgumentParser(
        prog="brieventool",
        description="Stelt een offertebrief samen uit de tekstblokkenbibliotheek.",
    )
    ontleder.add_argument("offerte", type=Path, help="YAML-bestand met de ingevulde keuzes")
    ontleder.add_argument("--docx", type=Path, help="schrijf een Word-bestand naar dit pad")
    ontleder.add_argument("--sjabloon", type=Path, default=Path("sjablonen/brief.docx"),
                          help="het Word-sjabloon (standaard: sjablonen/brief.docx)")
    ontleder.add_argument("--bibliotheek", type=Path,
                          help="map met teksten.yaml (standaard: BRIEVENTOOL_BIBLIOTHEEK of de projectmap)")
    ontleder.add_argument("--toch", action="store_true",
                          help="schrijf het Word-bestand ook als er nog gegevens ontbreken")
    ontleder.add_argument("--blokken", action="store_true",
                          help="toon welke tekstblokken zijn gebruikt")
    keuzes = ontleder.parse_args(argumenten)

    try:
        bibliotheek = laad(keuzes.bibliotheek)
        offerte = yaml.safe_load(keuzes.offerte.read_text(encoding="utf-8")) or {}
        brief = stel_samen(offerte, bibliotheek)
    except FileNotFoundError as fout:
        print(f"Bestand niet gevonden: {fout.filename}", file=sys.stderr)
        return 1
    except yaml.YAMLError as fout:
        print(f"{keuzes.offerte} is geen geldige YAML: {fout}", file=sys.stderr)
        return 1
    except (BibliotheekFout, SamenstelFout) as fout:
        print(f"Fout: {fout}", file=sys.stderr)
        return 1

    if keuzes.docx:
        ontbreekt = ontbrekende_gegevens(offerte)
        if ontbreekt and not keuzes.toch:
            print(f"Fout: {melding(ontbreekt)}", file=sys.stderr)
            print("Wil je hem toch, gebruik dan --toch.", file=sys.stderr)
            return 1
        try:
            geschreven = schrijf_docx(brief, keuzes.sjabloon, keuzes.docx)
        except SjabloonFout as fout:
            print(f"Fout: {fout}", file=sys.stderr)
            return 1
        print(f"Geschreven: {geschreven}")
    else:
        print(brief.tekst())

    if keuzes.blokken:
        print(f"\n{len(brief.gebruikte_blokken)} tekstblokken gebruikt:", file=sys.stderr)
        for blok_id in brief.gebruikte_blokken:
            print(f"  {blok_id}", file=sys.stderr)

    for waarschuwing in brief.waarschuwingen:
        print(f"Let op: {waarschuwing}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
