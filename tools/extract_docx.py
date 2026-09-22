#!/usr/bin/env python3
"""Leest alle .docx en .dotx uit bronbrieven/ uit met behoud van volgorde, kopjes en opsommingen.

Gebruikt python-docx wanneer dat beschikbaar is. Is het niet geinstalleerd, dan valt
het script terug op een parser die alleen de standaardbibliotheek gebruikt: een .docx
is een zip met XML, dus dat kan zonder externe dependency.

Gebruik:
    python3 tools/extract_docx.py                 # leest bronbrieven/, schrijft analyse/_extract/
    python3 tools/extract_docx.py --in map --out map
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# --------------------------------------------------------------------------
# Datamodel: elk blok is een dict zodat de JSON-uitvoer stabiel blijft.
# --------------------------------------------------------------------------

def _para(text, style=None, list_level=None, list_kind=None, source="body"):
    return {
        "type": "paragraaf",
        "tekst": text,
        "stijl": style,
        "lijst_niveau": list_level,
        "lijst_soort": list_kind,
        "herkomst": source,
    }


def _table(rows, source="body"):
    return {"type": "tabel", "rijen": rows, "herkomst": source}


# --------------------------------------------------------------------------
# Parser zonder externe dependency (zipfile + ElementTree)
# --------------------------------------------------------------------------

def _text_from_run_container(el) -> str:
    """Plakt de tekst van een paragraaf aan elkaar, inclusief tabs en regelafbrekingen."""
    parts = []
    for node in el.iter():
        tag = node.tag
        if tag == W + "t":
            parts.append(node.text or "")
        elif tag == W + "tab":
            parts.append("\t")
        elif tag in (W + "br", W + "cr"):
            parts.append("\n")
        elif tag == W + "noBreakHyphen":
            parts.append("-")
    return "".join(parts)


def _paragraph_props(p):
    """Haalt stijlnaam en eventuele lijstinformatie uit de paragraaf-properties."""
    style = None
    level = None
    kind = None

    ppr = p.find(W + "pPr")
    if ppr is not None:
        pstyle = ppr.find(W + "pStyle")
        if pstyle is not None:
            style = pstyle.get(W + "val")

        numpr = ppr.find(W + "numPr")
        if numpr is not None:
            ilvl = numpr.find(W + "ilvl")
            level = int(ilvl.get(W + "val")) if ilvl is not None else 0
            kind = "genummerd_of_bullet"

    # Word zet opsommingen vaak alleen via de stijlnaam, niet via numPr.
    if style and level is None:
        low = style.lower().replace(" ", "")
        if "listbullet" in low or low.startswith("lijstopsomming"):
            level, kind = 0, "bullet"
        elif "listnumber" in low or low.startswith("lijstnummering"):
            level, kind = 0, "genummerd"
        elif "listparagraph" in low or "lijstalinea" in low:
            level, kind = 0, "genummerd_of_bullet"

    return style, level, kind


def _parse_table(tbl, source):
    rows = []
    for tr in tbl.findall(W + "tr"):
        cells = []
        for tc in tr.findall(W + "tc"):
            cell_paras = [
                _text_from_run_container(p).strip() for p in tc.findall(W + "p")
            ]
            cells.append("\n".join(t for t in cell_paras if t))
        rows.append(cells)
    return _table(rows, source)


def _parse_body(root, source="body"):
    """Loopt de body-elementen in documentvolgorde af: paragrafen en tabellen door elkaar."""
    blocks = []
    body = root.find(W + "body")
    container = body if body is not None else root

    for el in container:
        if el.tag == W + "p":
            text = _text_from_run_container(el)
            style, level, kind = _paragraph_props(el)
            # Lege paragrafen bewaren we niet; ze zeggen niets over de inhoud.
            if text.strip() or style:
                blocks.append(_para(text.rstrip(), style, level, kind, source))
        elif el.tag == W + "tbl":
            blocks.append(_parse_table(el, source))
    return blocks


def _style_name_map(zf: zipfile.ZipFile) -> dict:
    """styles.xml vertaalt de interne styleId naar de naam die de gebruiker in Word ziet."""
    try:
        root = ET.fromstring(zf.read("word/styles.xml"))
    except KeyError:
        return {}
    mapping = {}
    for style in root.findall(W + "style"):
        sid = style.get(W + "styleId")
        name_el = style.find(W + "name")
        if sid and name_el is not None:
            mapping[sid] = name_el.get(W + "val")
    return mapping


def extract_stdlib(path: Path) -> dict:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        styles = _style_name_map(zf)

        blocks = _parse_body(ET.fromstring(zf.read("word/document.xml")), "body")

        # Briefkop, project no., Ref. en contactgegevens staan vaak in de
        # header of footer, niet in de body. Die willen we dus ook zien.
        for part in sorted(n for n in names if re.fullmatch(r"word/(header|footer)\d*\.xml", n)):
            label = Path(part).stem
            blocks.extend(_parse_body(ET.fromstring(zf.read(part)), label))

        media = sorted(n for n in names if n.startswith("word/media/"))

    for b in blocks:
        if b["type"] == "paragraaf" and b["stijl"]:
            b["stijl"] = styles.get(b["stijl"], b["stijl"])

    return {"bestand": path.name, "blokken": blocks, "afbeeldingen": media}


# --------------------------------------------------------------------------
# Variant met python-docx, voor wie hem wel geinstalleerd heeft
# --------------------------------------------------------------------------

def extract_python_docx(path: Path) -> dict:
    import docx
    from docx.document import Document as _Doc
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(str(path))
    blocks = []

    # Body-elementen in documentvolgorde aflopen, paragrafen en tabellen door elkaar.
    for child in doc.element.body:
        if child.tag == W + "p":
            p = Paragraph(child, doc)
            style, level, kind = _paragraph_props(child)
            if p.text.strip() or p.style.name:
                blocks.append(_para(p.text.rstrip(), p.style.name, level, kind))
        elif child.tag == W + "tbl":
            t = Table(child, doc)
            rows = [[c.text.strip() for c in row.cells] for row in t.rows]
            blocks.append(_table(rows))

    for i, section in enumerate(doc.sections):
        for label, part in (("header", section.header), ("footer", section.footer)):
            for p in part.paragraphs:
                if p.text.strip():
                    blocks.append(_para(p.text.rstrip(), p.style.name, source=f"{label}{i or ''}"))

    with zipfile.ZipFile(path) as zf:
        media = sorted(n for n in zf.namelist() if n.startswith("word/media/"))

    return {"bestand": path.name, "blokken": blocks, "afbeeldingen": media}


# --------------------------------------------------------------------------
# Uitvoer
# --------------------------------------------------------------------------

def to_markdown(doc: dict) -> str:
    lines = [f"# {doc['bestand']}", ""]
    if doc["afbeeldingen"]:
        lines += ["> Afbeeldingen in dit bestand: " + ", ".join(doc["afbeeldingen"]), ""]

    huidige_herkomst = "body"
    for b in doc["blokken"]:
        herkomst = b.get("herkomst", "body")
        if herkomst != huidige_herkomst:
            lines += ["", f"<!-- {herkomst} -->", ""]
            huidige_herkomst = herkomst

        if b["type"] == "tabel":
            lines.append("")
            for rij in b["rijen"]:
                lines.append("| " + " | ".join(c.replace("\n", "<br>") for c in rij) + " |")
            lines.append("")
            continue

        stijl = b["stijl"] or ""
        tekst = b["tekst"]
        if b["lijst_niveau"] is not None:
            lines.append("  " * b["lijst_niveau"] + f"- {tekst}   <!-- {stijl} -->")
        elif stijl.lower().startswith(("heading", "kop")):
            lines.append(f"## {tekst}   <!-- {stijl} -->")
        else:
            lines.append(f"{tekst}   <!-- {stijl} -->")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in", dest="src", default="bronbrieven", type=Path)
    ap.add_argument("--out", dest="dst", default="analyse/_extract", type=Path)
    args = ap.parse_args()

    if not args.src.is_dir():
        print(f"Map {args.src} bestaat niet.", file=sys.stderr)
        return 1

    # .dotx is een Word-sjabloon, intern hetzelfde zip-met-XML formaat als .docx.
    files = sorted(
        p
        for p in args.src.iterdir()
        if p.suffix.lower() in (".docx", ".dotx") and not p.name.startswith("~$")
    )
    if not files:
        print(f"Geen .docx of .dotx gevonden in {args.src}/.", file=sys.stderr)
        return 1

    try:
        import docx  # noqa: F401
        extract, motor = extract_python_docx, "python-docx"
    except ImportError:
        extract, motor = extract_stdlib, "standaardbibliotheek (python-docx niet gevonden)"
    print(f"Uitleesmotor: {motor}")

    args.dst.mkdir(parents=True, exist_ok=True)
    docs = []
    for f in files:
        doc = extract(f)
        docs.append(doc)
        (args.dst / f"{f.stem}.md").write_text(to_markdown(doc), encoding="utf-8")
        print(f"  {f.name}: {len(doc['blokken'])} blokken, {len(doc['afbeeldingen'])} afbeelding(en)")

    (args.dst / "_alles.json").write_text(
        json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{len(docs)} brieven uitgelezen naar {args.dst}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
