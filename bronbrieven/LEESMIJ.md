# bronbrieven/

## Sjablonen (in git)

De 16 lege sjablonen, `.dotx` op één `.docx` na. De bestandsnaam geeft de variant
aan: model binnenunit, enkelvoud of meervoud, en of het een particuliere versie is.

Uitlezen:

    python3 tools/extract_docx.py

Dat schrijft per brief een leesbare `.md` en één gezamenlijke `_alles.json` naar
`analyse/_extract/`.

## uitgewerkt/ (niet in git)

Ingevulde klantbrieven, gebruikt om de patronen in `projectnummer`, `referentie`,
de btw-weergave en de facturering te achterhalen. Deze bevatten namen, adressen,
e-mailadressen en prijzen van echte klanten en staan daarom in `.gitignore` — zie
`analyse/vragen.md` vraag 18. De analyse verwijst ernaar als `uitgewerkt-1` tot
en met `uitgewerkt-7`, zonder klantgegevens.

Uitlezen:

    python3 tools/extract_docx.py --in bronbrieven/uitgewerkt --out analyse/_extract/uitgewerkt
    python3 tools/extract_pdf.py bronbrieven/uitgewerkt/<brief>.pdf

Omdat deze map niet in git staat, is hij er in een nieuwe werkomgeving niet.
Wil je `tools/toets_tegen_echte_brief.py` draaien, zet er dan eerst een
verstuurde brief in terug.
