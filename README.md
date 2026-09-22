# Calcu-Brief-tool — Schilt Airconditioning

Eén tool die begint bij de calculatie en eindigt bij een offertebrief: je vult
een project door (installaties, materiaal, uren, marge), en zodra dat klaar
is vult de brief zich grotendeels vanzelf — als een **bewerkbaar concept**,
nooit als een afgeronde brief. Dit is de samenvoeging van twee eerder losse
tools (de calculatietool en de brieventool); zie "Herkomst" onderaan voor wat
daarbij is overgenomen, geport en toegevoegd.

## Starten

**Mac:** dubbelklik `Calcu-Brief-tool.app`. Dat is een echte, headless
app-bundel: geen Terminal-venster, alleen een systeemmelding als er iets
misgaat (Python ontbreekt, of `pip install -r requirements.txt` is nog niet
gedraaid). Eerste keer: rechtsklik → Open (onbekende-ontwikkelaar-
waarschuwing van macOS).

Wil je een pictogram op je Bureaublad of in het Dock? Sleep het `.app`-
bestand daar **niet** los naartoe — hij verwacht de rest van de projectmap
naast zich. Maak in plaats daarvan een Finder-alias (rechtsklik op
`Calcu-Brief-tool.app` → Maak alias) en sleep die alias naar je Bureaublad of
Dock; die blijft naar de app in de projectmap wijzen.

**Windows:** dubbelklik `start-app.pyw`. Windows koppelt `.pyw`-bestanden
standaard aan `pythonw.exe`, dat draait zonder zwart consolevenster (fouten
komen als een dialoogvenster). Wil je juist wél live meelezen wat de server
doet (bijv. om een probleem uit te zoeken), gebruik dan `start.bat`.
Bureaublad-snelkoppeling: rechtsklik `start-app.pyw` → Verzenden naar →
Bureaublad (snelkoppeling maken).

Beide starten een lokale server en openen de tool in je browser
(`http://127.0.0.1:8391/`), met een kort laadscherm terwijl de gegevens en de
rekenkern klaarstaan. De app is bewust niet van buitenaf bereikbaar: er staan
klant- en prijsgegevens in.

Vereist: Python 3.11+ (`python3 --version` / `python --version`) mét de
afhankelijkheden geïnstalleerd:

    pip install -r requirements.txt   # PyYAML + Jinja2, allebei pure Python

Zonder dubbelklik-opstarter kan het ook rechtstreeks:

    python3 server.py
    python3 server.py --poort 8000 --geen-browser

## Hoe de twee stappen samenhangen

- **Stap 1 — Calculatie**: installaties, materiaal, uren, uitbesteding,
  equipment en de marge-opbouw tot en met de verkoopprijs. De rekenkern
  (`calculatie/rekenkern.py`) is de enige plek waar dit wordt uitgerekend —
  het scherm stuurt bij elke wijziging de invoer naar `POST /bereken` en
  toont het antwoord, precies zoals stap 2 dat al deed voor de brief. Zo
  kunnen de twee stappen nooit een verschillend bedrag laten zien.
- **Overdracht**: de knop "↺ Vul voor vanuit de calculatie" in stap 2 zet de
  calculatie om in een (deels ingevulde) briefconcept (`overdracht.py`).
  Directe overnames (datum, verkoopprijs, merk, aantallen) worden gewoon
  ingevuld. Onzekere afleidingen — vooral de vertaling van de calculatie se
  grove systeemsoort (VRF/RAC/PAC/Overig) naar de fijnere indeling die de
  brief kent (splitsystem/multi-splitsystem/vrf/warmtepomp/
  vloeistofkoelmachine) — krijgen het label **"afgeleid — controleer"** en
  blijven gewoon een bewerkbaar veld. Wat de calculatie niet kan weten
  (klanttype, adres, aanhef, facturering, ondertekenaar, ...) blijft een
  gewoon, door `brieventool/controle.py` bewaakt formulierveld: er komt geen
  Word-bestand totdat alles is ingevuld, en de melding noemt precies wat er
  nog mist.
- **Stap 2 — Brief**: kiest en vult tekstblokken uit
  `analyse/teksten.yaml` (zie `brieventool/`) en levert een Word-bestand op
  het echte Schilt-briefpapier. Facturering, betaling, condensafvoer e.d.
  hardcoderen hun mogelijke waarden niet in het scherm: die worden afgeleid
  uit de voorwaarden in `teksten.yaml` zelf (`GET /keuzes`, zie
  `brieventool/bibliotheek.py:velden`), zodat een nieuwe variant in de
  tekstbibliotheek vanzelf in het formulier verschijnt.

## Project opslaan/openen

**Opslaan als .json** bewaart zowel de calculatie als het briefconcept in
één bestand; **Openen** leest zo'n bestand weer helemaal terug (calculatie
wordt automatisch herberekend). De browser onthoudt daarnaast de laatste
stand in `localStorage` als vangnet tegen een dichtgeklapt tabblad — dat is
geen archief, alleen die ene computer heeft het.

## Indeling

    server.py             de lokale app: bedient beide stappen
    Calcu-Brief-tool.app/ dubbelklik-opstarter voor Mac (geen Terminal-venster)
    start-app.pyw         dubbelklik-opstarter voor Windows (geen consolevenster)
    start.command / .bat  dezelfde opstart, wél met zichtbare terminal/console (handig bij problemen)
    calculatie/
      rekenkern.py        de rekenkern (marge, uren, afgeleide materiaalregels)
    overdracht.py         zet een calculatie om in een briefconcept
    brieventool/          tekstblokken kiezen, invullen, Word-bestand schrijven
    analyse/teksten.yaml  de brieftekst zelf (143 blokken) — geen codewijziging nodig
    config/ondertekenaars.yaml   ondertekenaars + bedrijfsgegevens
    sjablonen/brief.docx  het Word-sjabloon (gegenereerd, niet met de hand bewerken)
    bronbrieven/          de 16 lege bronsjablonen waaraan de opmaak is nagemeten
    data/                 calculatie-stamgegevens (materiaalcatalogus, YIMM, Panasonic/Daikin, tarieven)
    scherm/               het scherm: index.html + stijl.css + calculatie.js + brief.js
    tests/                230 tests (rekenkern, overdracht, brieventool)
    voorbeelden/          ingevulde offertes om mee te proberen (los van de calculatie)

## Tests

    python3 -m unittest discover -s tests -t .

## Herkomst

Deze repo voegt twee eerder losse tools samen tot één codebase (zoals
afgesproken na afweging van de alternatieve, gescheiden-tools-met-JSON-
koppeling-aanpak):

- **De calculatietool** (`calculatie-tool-schilt`) — een op zichzelf staand
  HTML-bestand. De rekenkern is hier overgezet naar Python
  (`calculatie/rekenkern.py`), getoetst tegen dezelfde 39 tegen Excel
  geverifieerde controles als het origineel (nu `tests/test_rekenkern.py`).
  De DOM-weergave en het zoeken/bladeren in de materiaalcatalogus zijn zo
  goed als ongewijzigd overgenomen (`scherm/calculatie.js`).
- **De brieventool** (`brieven-tool-schilt-bedrijven`) — Python, met een
  volledig werkende motor (`brieventool/`, 118+ tests) maar nog zonder
  formulier ("Wat er nog niet is: het formulier", zie de oorspronkelijke
  README). Dat formulier is hier gebouwd (`scherm/brief.js`), samen met de
  nieuwe overdracht vanuit de calculatie.

Wat bewust niet is overgenomen: de losse, server-loze JS-spiegel van de
brief-motor in `ontwerp/prototype.html` (een noodgreep om de brief ook zonder
Python te kunnen tonen). Omdat deze tool sowieso een Python-server draait
voor de calculatie, is die tweede motor hier overbodig — er is nu precies
één plek (Python) die bepaalt wat er in de brief komt te staan.
