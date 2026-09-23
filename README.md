# Calcu-Brief-tool — Schilt Airconditioning

Eén tool die begint bij de calculatie en eindigt bij een offertebrief: je vult
een project door (installaties, materiaal, uren, marge), en zodra dat klaar
is vult de brief zich grotendeels vanzelf — als een **bewerkbaar concept**,
nooit als een afgeronde brief. Dit is de samenvoeging van twee eerder losse
tools (de calculatietool en de brieventool); zie "Herkomst" onderaan voor wat
daarbij is overgenomen, geport en toegevoegd.

## Starten (voor collega's: downloaden en dubbelklikken, geen Python nodig)

Op de [Releases-pagina](https://github.com/ticketsgrind/Calcu-Brief-tool/releases/tag/app-download)
staat een op zichzelf staande app per platform — Python zit erin gebakken,
er hoeft niets geïnstalleerd te worden:

- **Windows:** `CalcuBriefTool-windows.zip` downloaden, uitpakken, en
  `CalcuBriefTool.exe` **in die uitgepakte map** dubbelklikken (niet het
  bestand er los uit halen — de map ernaast bevat wat de app nodig heeft).
  Windows kan een SmartScreen-waarschuwing tonen ("Windows heeft de app
  beschermd"); klik op **Meer info** → **Toch uitvoeren**.
- **Mac:** `CalcuBriefTool-mac.zip` downloaden, uitpakken, `CalcuBriefTool.app`
  dubbelklikken (eerste keer rechtsklik → Open, vanwege de onbekende-
  ontwikkelaar-waarschuwing van macOS).

Na het dubbelklikken opent na een paar seconden vanzelf de browser met de
tool.

Deze bestanden worden automatisch opnieuw gebouwd bij elke wijziging (zie
`.github/workflows/build-app.yml`) — de link hierboven geeft altijd de
nieuwste versie.

## Starten vanuit de broncode (voor ontwikkelaars)

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

- **Stap 1 — Calculatie** (`scherm/index.html`): installaties, materiaal,
  uren, uitbesteding, equipment en de marge-opbouw tot en met de
  verkoopprijs. De rekenkern (`calculatie/rekenkern.py`) is de enige plek
  waar dit wordt uitgerekend — het scherm stuurt bij elke wijziging de
  invoer naar `POST /bereken` en toont het antwoord. "Calculatie klaar →
  verder naar de brief" navigeert daarna naar de briefstap.
- **Stap 2 — Brief** (`scherm/brief.html`, een eigen pagina, geen tab): zo
  goed als 1-op-1 overgenomen van de losstaande brieventool — zie
  "Herkomst" onderaan. Kiest en vult tekstblokken uit `analyse/teksten.yaml`
  en levert een Word-bestand op het echte Schilt-briefpapier, via dezelfde
  `brieventool.samenstellen`/`brieventool.sjabloon`-code die ook de
  voorvertoning tekent — er is dus precies één plek die bepaalt wat er in de
  brief komt te staan.
- **Overdracht**: bij het overstappen naar stap 2 (of via de knop "↺ Vanuit
  calculatie" daar) zet `overdracht.py` de calculatie om in een (deels
  ingevulde) aanvulling op het briefconcept — bestaande, met de hand
  ingevulde velden blijven staan. Directe overnames (datum, verkoopprijs,
  merk, aantallen) worden gewoon ingevuld. Onzekere afleidingen — vooral de
  vertaling van de calculatie se grove systeemsoort (VRF/RAC/PAC/Overig)
  naar de fijnere indeling die de brief kent (splitsystem/multi-
  splitsystem/vrf/warmtepomp/vloeistofkoelmachine) — worden na de overdracht
  expliciet genoemd in een melding, ter controle. Wat de calculatie niet kan
  weten (klanttype, adres, aanhef, facturering, ondertekenaar, ...) blijft
  een gewoon, door `brieventool/controle.py` bewaakt formulierveld: er komt
  geen Word-bestand totdat alles is ingevuld, en de melding noemt precies
  wat er nog mist.

## Project opslaan/openen

De calculatie (**Calculatie opslaan als .json** / **Calculatie openen…** in
stap 1) en de brief (**Opslaan** / **Openen** in de kop van stap 2) hebben
allebei hun eigen bestand — dat is hoe de losstaande brieventool dat al deed
en is met de overname van die stap zo gebleven. Wat ze wel delen: dezelfde
klantnaam/projectnaam in de standaard bestandsnaam
(`Calculatie-klant-project.json` / `Brief-klant-project.docx`), en de
browser onthoudt de laatste stand van allebei apart in `localStorage` als
vangnet tegen een dichtgeklapt tabblad — dat is geen archief, alleen die ene
computer heeft het.

## Indeling

    server.py             de lokale app: bedient beide stappen
    Calcu-Brief-tool.app/ dubbelklik-opstarter voor Mac (geen Terminal-venster)
    start-app.pyw         dubbelklik-opstarter voor Windows (geen consolevenster)
    start.command / .bat  dezelfde opstart, wél met zichtbare terminal/console (handig bij problemen)
    calculatie/
      rekenkern.py        de rekenkern (marge, uren, afgeleide materiaalregels)
    overdracht.py         zet een calculatie om in een aanvulling op het briefconcept
    brieventool/          tekstblokken kiezen, invullen, Word-bestand schrijven
    analyse/teksten.yaml  de brieftekst zelf (152 blokken) — geen codewijziging nodig
    config/ondertekenaars.yaml   ondertekenaars + bedrijfsgegevens
    sjablonen/brief.docx  het Word-sjabloon (gegenereerd, niet met de hand bewerken)
    bronbrieven/          de 16 lege bronsjablonen waaraan de opmaak is nagemeten
    data/                 calculatie-stamgegevens (materiaalcatalogus, YIMM, Panasonic/Daikin, tarieven)
    scherm/
      index.html/stijl.css/calculatie.js/gedeeld.js   stap 1 (calculatie)
      brief.html         stap 2 (brief) — een eigen pagina, 1-op-1 overgenomen
                         van de losstaande brieventool (zie "Herkomst")
    tools/ververs_brief_scherm.py   werkt scherm/brief.html bij na een wijziging
                         in analyse/teksten.yaml of sjablonen/brief.docx
    tests/                231 tests (rekenkern, overdracht, brieventool)
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
  volledig werkende motor (`brieventool/`, 118+ tests) én een werkend
  prototype van het formulier (`ontwerp/prototype.html`). Dat prototype is
  hier overgenomen als `scherm/brief.html`, vrijwel letterlijk — zie
  hieronder waarom.

**Een eerdere versie van deze samenvoeging bouwde het briefformulier zelf
opnieuw** (`scherm/brief.js`, inmiddels verwijderd), in plaats van het
bestaande prototype over te nemen. Dat werkte in eigen tests, maar de brief
week op punten af van wat de losstaande brieventool maakte, en het
Word-bestand klopte niet altijd — precies het probleem dat deze samenvoeging
had moeten voorkomen. `scherm/brief.html` is daarom alsnog vrijwel een
letterlijke kopie van `ontwerp/prototype.html`: die pagina praat rechtstreeks
met dezelfde `brieventool.samenstellen`/`brieventool.sjabloon`-code als de
rest van de tool, en is in de bronrepo al grondig getoetst. De enige
toevoegingen zijn de koppeling met de calculatiestap (er was in de
losstaande tool geen calculatiestap om aan te koppelen) en een aangepaste
standaard bestandsnaam; zie CLAUDE.md voor de details.
