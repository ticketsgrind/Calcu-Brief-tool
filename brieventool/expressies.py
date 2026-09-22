"""Veilige evaluatie van de expressies uit teksten.yaml.

De voorwaarden in de tekstblokkenbibliotheek zien eruit als Python, maar we
willen ze niet met eval() uitvoeren: dan wordt een tekstbestand dat iedereen
mag aanpassen ineens uitvoerbare code. Deze module loopt in plaats daarvan de
ontleedboom af en staat alleen toe wat de bibliotheek werkelijk gebruikt:

    vergelijkingen        klanttype == 'particulier', aantal_binnenunits > 1
    logica                and, or, not
    lidmaatschap          'demontage' in werk_inclusief
    attributen            regel.systeemsoort
    functieaanroepen      telwoord(regel.aantal_systemen)  -- alleen uit FUNCTIES
    inline keuze          's' if regel.aantal_systemen > 1 else ''

Alles wat daarbuiten valt levert een ExpressieFout op, met de expressie erbij,
zodat een typefout in teksten.yaml meteen te vinden is.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Callable, Mapping


class ExpressieFout(ValueError):
    """De expressie is ongeldig of gebruikt iets wat niet is toegestaan."""


_VERGELIJKINGEN: Mapping[type, Callable[[Any, Any], Any]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}

_REKENKUNDE: Mapping[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
}


def evalueer(expressie: str, context: Mapping[str, Any],
             functies: Mapping[str, Callable[..., Any]] | None = None) -> Any:
    """Rekent één expressie uit binnen de gegeven context."""
    functies = functies or {}
    boom = _ontleed(expressie)
    return _loop(boom.body, expressie, context, functies)


def _ontleed(expressie: str) -> ast.Expression:
    """Ontleedt de expressie, met één toegift aan de Jinja-schrijfwijze.

    In Jinja mag je "{{ 's' if aantal > 1 }}" schrijven zonder else; Python eist
    daar een else bij. Omdat teksten.yaml in Jinja-stijl is opgeschreven vullen
    we de ontbrekende else aan met een lege tekst.
    """
    kaal = expressie.strip()
    try:
        return ast.parse(kaal, mode="eval")
    except SyntaxError as fout:
        if "else" in (fout.msg or ""):
            try:
                return ast.parse(f"{kaal} else ''", mode="eval")
            except SyntaxError:
                pass
        raise ExpressieFout(f"kan {expressie!r} niet lezen: {fout.msg}") from fout


def is_waar(voorwaarde: str | None, context: Mapping[str, Any],
            functies: Mapping[str, Callable[..., Any]] | None = None) -> bool:
    """Een lege voorwaarde betekent 'dit blok gaat altijd mee'."""
    if voorwaarde is None or not voorwaarde.strip():
        return True
    return bool(evalueer(voorwaarde, context, functies))


def _loop(knoop: ast.AST, bron: str, context: Mapping[str, Any],
          functies: Mapping[str, Callable[..., Any]]) -> Any:
    herhaal = lambda k: _loop(k, bron, context, functies)

    if isinstance(knoop, ast.Constant):
        return knoop.value

    if isinstance(knoop, ast.Name):
        # Een onbekende naam is leeg, niet fout: 'organisatie' mag ontbreken bij
        # een particulier, en de voorwaarde hoort dan gewoon onwaar te zijn.
        return context.get(knoop.id)

    if isinstance(knoop, ast.Attribute):
        doel = herhaal(knoop.value)
        if doel is None:
            return None
        # Alleen woordenboeken: regel.merk, ondertekenaar.naam, bedrijf.kvk.
        # getattr op een gewone waarde zou via __class__ toegang geven tot de
        # rest van Python, en het tekstenbestand mag geen code kunnen draaien.
        if isinstance(doel, Mapping):
            return doel.get(knoop.attr)
        raise ExpressieFout(
            f"{knoop.attr!r} opvragen op {type(doel).__name__} mag niet in {bron!r}"
        )

    if isinstance(knoop, ast.BoolOp):
        waarden = knoop.values
        if isinstance(knoop.op, ast.And):
            uitkomst: Any = True
            for deel in waarden:
                uitkomst = herhaal(deel)
                if not uitkomst:
                    return uitkomst
            return uitkomst
        for deel in waarden:
            uitkomst = herhaal(deel)
            if uitkomst:
                return uitkomst
        return uitkomst

    if isinstance(knoop, ast.UnaryOp) and isinstance(knoop.op, ast.Not):
        return not herhaal(knoop.operand)

    if isinstance(knoop, ast.UnaryOp) and isinstance(knoop.op, ast.USub):
        return -herhaal(knoop.operand)

    if isinstance(knoop, ast.Compare):
        links = herhaal(knoop.left)
        for soort, rechterknoop in zip(knoop.ops, knoop.comparators):
            vergelijk = _VERGELIJKINGEN.get(type(soort))
            if vergelijk is None:
                raise ExpressieFout(f"vergelijking {type(soort).__name__} niet toegestaan in {bron!r}")
            rechts = herhaal(rechterknoop)
            try:
                if not vergelijk(links, rechts):
                    return False
            except TypeError:
                # Bijvoorbeeld None > 1 wanneer een veld niet is ingevuld.
                return False
            links = rechts
        return True

    if isinstance(knoop, ast.BinOp):
        rekenen = _REKENKUNDE.get(type(knoop.op))
        if rekenen is None:
            raise ExpressieFout(f"bewerking {type(knoop.op).__name__} niet toegestaan in {bron!r}")
        return rekenen(herhaal(knoop.left), herhaal(knoop.right))

    if isinstance(knoop, ast.IfExp):
        return herhaal(knoop.body) if herhaal(knoop.test) else herhaal(knoop.orelse)

    if isinstance(knoop, ast.Call):
        if not isinstance(knoop.func, ast.Name):
            raise ExpressieFout(f"alleen eenvoudige functieaanroepen toegestaan in {bron!r}")
        naam = knoop.func.id
        if naam not in functies:
            raise ExpressieFout(f"onbekende functie {naam!r} in {bron!r}")
        if knoop.keywords:
            raise ExpressieFout(f"benoemde argumenten niet toegestaan in {bron!r}")
        return functies[naam](*[herhaal(a) for a in knoop.args])

    if isinstance(knoop, (ast.List, ast.Tuple)):
        return [herhaal(el) for el in knoop.elts]

    if isinstance(knoop, ast.Subscript):
        doel = herhaal(knoop.value)
        if doel is None:
            return None
        try:
            return doel[herhaal(knoop.slice)]
        except (KeyError, IndexError, TypeError):
            return None

    raise ExpressieFout(f"{type(knoop).__name__} niet toegestaan in {bron!r}")
