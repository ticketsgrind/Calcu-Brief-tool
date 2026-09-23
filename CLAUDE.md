# CLAUDE.md

Deze repository is in het Nederlands: code, commentaar, variabelenamen,
commitberichten en documentatie. Zie ook `README.md` voor de indeling en hoe
de tool te starten.

## Wat dit is

De samenvoeging van twee eerder losse tools (calculatietool + brieventool)
tot één app: stap 1 is de calculatie, stap 2 de offertebrief, met een
overdracht ertussen die nooit gokt. Zie `README.md` §Herkomst voor de
achtergrond van die samenvoeging.

## De architectuurregel: één plek per berekening

`calculatie/rekenkern.py` is de ENIGE plek die de marge/uren/afgeleide
materiaalregels uitrekent, en `brieventool/samenstellen.py` de enige plek die
bepaalt wat er in de brief komt te staan. Het scherm (`scherm/*.js`) rekent
zelf niets uit: elke wijziging gaat naar `POST /bereken` resp. `POST /brief`
en het scherm tekent alleen het antwoord. Voeg nooit een tweede
implementatie van een rekenregel of blokselectie toe aan de JS-kant, ook niet
"voor de snelheid" — dat is precies het risico dat deze samenvoeging moest
oplossen (calculatie en brief die een ander bedrag laten zien).

Wat wél client-side blijft: triviale, niet-interpretatiegevoelige arithmetiek
(`regelTotaal`/`lijstTotaal` in `scherm/calculatie.js` — gewoon aantal ×
prijs) en het zoeken/bladeren in de materiaalcatalogus. Dat is opzoeklogica,
geen rekenregel, en dupliceert dus niets business-kritisch.

## `overdracht.py`: nooit gokken, wel afleiden

Drie statussen per veld, zie de moduledocstring:
- **direct** — simpele overname (datum, verkoopprijs).
- **afgeleid** — een toegepaste regel met een niet-triviale aanname. De
  systeemsoort-vertaling (calculatie se grove VRF/RAC/PAC/Overig → de fijnere
  indeling van de brief) is hier het voorbeeld: RAC/PAC met 1 binnendeel
  wordt splitsystem, met meer een multi-splitsystem — ook als het in
  werkelijkheid meerdere losse splitsystemen zijn.
- **keuze_nodig** — de calculatie bevat de informatie niet; het veld blijft
  leeg. "Overig" kan zowel warmtepomp als vloeistofkoelmachine zijn en krijgt
  daarom nooit een gok, altijd een lege keuze met beide opties.

Een `keuze_nodig`- of leeg veld hoeft geen aparte "ontbreekt"-lijst: zodra
het een normaal offerte-veld is loopt het gewoon door de bestaande
`brieventool/controle.ontbrekende_gegevens()`. **`systeemsoort` is om die
reden toegevoegd aan `controle.INSTALLATIEVELDEN`** (was er niet in de
losstaande brieventool, omdat daar nog geen formulier bestond en elke
offerte met de hand in YAML werd geschreven) — zonder systeemsoort matcht
geen enkel blok in de sectie "systeemomschrijving" en blijft die
installatieregel stilzwijgend zonder omschrijving.

**De koppeling zit in `scherm/brief.html`, niet in `overdracht.py` zelf** —
zie de sectie "De briefstap is 1-op-1 overgenomen" hieronder voor waar en
hoe. Voor de "afgeleid"-status geldt daar: dit scherm heeft geen los
badge-per-veld-systeem zoals eerder werd geprobeerd; in plaats daarvan noemt
`vulVanuitCalculatie()` de afgeleide velden expliciet in een melding na de
overdracht, zodat "nooit stilzwijgend" behouden blijft zonder de
overgenomen UI te hoeven aanpassen.

**Btw bij overdracht.** De calculatie rekent altijd exclusief btw (er is geen
klanttype-begrip in stap 1). `overdracht.zet_over()` krijgt daarom optioneel
`klanttype` mee (door `scherm/brief.html` meegestuurd als de huidige waarde
van `A.klanttype` op het moment van de klik) en telt er 21% bij op vóór het
bedrag in `prijsregels` komt, maar alleen bij `klanttype == "particulier"`
-- onbekend/leeg klanttype blijft exclusief, nooit een gok welke kant op.
Wordt klanttype pas ná de eerste overdracht ingesteld, dan klopt het bedrag
dus nog niet totdat de overdracht opnieuw wordt toegepast (de knop "↺ Vanuit
calculatie" in `scherm/brief.html`).

## De briefstap is 1-op-1 overgenomen uit de losstaande brieventool

`scherm/brief.html` is vrijwel een letterlijke kopie van
`ontwerp/prototype.html` uit de losstaande brieventool (repo
`brieven-tool-schilt-bedrijven`) — niet een eigen bouwsel zoals de eerdere
`scherm/brief.js` dat was. Reden: die eigen JS-implementatie leek te werken
in tests, maar de echte brief week op punten af van wat de losstaande tool
maakte, en het Word-bestand daaruit klopte niet altijd. Het prototype is
grondig getest (eigen `test_spiegel.py`/`test_server.py` in de bronrepo) en
praat via `fetch("app")`/`fetch("brief")`/`fetch("docx")`/`fetch("briefpapier")`/
`fetch("datablad")` rechtstreeks met dezelfde `brieventool.samenstellen`/
`brieventool.sjabloon`-code als deze tool — er is dus precies één plek die
bepaalt wat er in de brief staat, ook nu.

**Waarom een aparte pagina en geen tab zoals stap 1.** Het prototype is een
complete, op zichzelf staande pagina (eigen `<style>`, eigen kop met
Nieuw/Openen/Opslaan/Word-bestand-knoppen) — die in de bestaande
tab-structuur van `index.html` proppen zou of de CSS van de twee stappen
laten botsen, of de eigen kop van het prototype dubbel neerzetten naast de
stappen-nav. `server.py` serveert `scherm/brief.html` daarom op het
root-niveau (`/brief.html`, niet onder `/scherm/`), zodat de relatieve
`fetch("app")` etc. in dat bestand — ongewijzigd overgenomen — gewoon naar
`/app` etc. resolven zonder dat de URL's aangepast hoefden te worden. De
"Calculatie klaar → verder naar de brief"-knop en de "2 Brief →"-knop in de
stappen-nav (`scherm/index.html`) doen daarom een echte paginanavigatie
(`location.href = 'brief.html'`), geen tab-wissel meer.

**De koppeling met de calculatie** (niet in het origineel, want die kende
geen calculatiestap) zit in een apart, duidelijk afgebakend script-blok
onderaan `scherm/brief.html`, vlak vóór de bestaande opstart-IIFE:
- `calculatieStaatOphalen()` leest `localStorage['calcubrief.concept']` —
  dezelfde sleutel als `AUTOSAVE_SLEUTEL` in `scherm/gedeeld.js` — en pakt
  daar alleen `.calculatie` uit; er wordt hier nooit iets teruggeschreven.
- `vulVanuitCalculatie()` stuurt die calculatiestaat plus het huidige
  `A.klanttype` naar `POST /overdracht` en voegt het resultaat toe aan `A`
  (`Object.assign`, dus een aanvulling, geen vervanging — bestaande, met de
  hand ingevulde velden blijven staan). `installaties[]` is een
  uitzondering: de EERSTE keer (`A._vanuitCalculatieToegepast` nog niet
  gezet) vervangt de calculatie de voorbeeldinstallaties helemaal — die
  samenvoegen zou verwarrende resten van de voorbeelddata achterlaten als de
  aantallen niet overeenkomen. Bij een volgende toepassing (na eigen
  aanpassingen zoals "ruimte" of "eigen kopregel") wordt per regel
  samengevoegd, zodat die aanpassingen niet verloren gaan.
- De knop "↺ Vanuit calculatie" in de kop roept dit handmatig aan; een
  eenmalige `sessionStorage`-vlag (`calcubrief.naarBrief`, gezet door
  `scherm/index.html` vlak vóór de navigatie) laat het bij binnenkomst ook
  automatisch één keer gebeuren — zodat "één klik doet alles" behouden
  blijft zonder dat deze pagina iets hoeft te weten van hoe `index.html` dat
  aanroept, en andersom.
- De standaard bestandsnaam (`bestandsnaam()`, ook gebruikt door de eigen
  Opslaan-als-JSON-knop van dit scherm) is de enige andere aanpassing t.o.v.
  het origineel: die las daar `achternaam-plaats-sa_nummer`, hier leest hij
  eerst `localStorage['calcubrief.concept'].calculatie.meta` (klantnaam +
  projectnaam) zodat de calculatie- en briefbestanden van hetzelfde project
  dezelfde naam delen (`Calculatie-…`/`Brief-…`, zie `CB.projectBestandsnaam`
  in `gedeeld.js`) — en valt terug op de oorspronkelijke naamgeving als er
  geen calculatieproject bekend is (de brief kan nog steeds los gebruikt
  worden).

**Bijwerken na een wijziging in `analyse/teksten.yaml` of
`sjablonen/brief.docx`.** Net als het origineel heeft `scherm/brief.html` de
tekstblokken en het Word-sjabloon ingebakken (voor de fallback-modus zonder
server, zie hieronder) — dat loopt dus niet vanzelf gelijk met een wijziging
in die bronbestanden. Draai na zo'n wijziging:

    python3 tools/ververs_brief_scherm.py

(een aangepaste versie van `ontwerp/ververs_prototype.py` uit de bronrepo,
die hier `scherm/brief.html` bijwerkt in plaats van `ontwerp/prototype.html`).

**De ingebakken "motor"/"word"-fallback (tussen `/*<motor>*/`...`/*</motor>*/`
en `/*<word>*/`...`/*</word>*/`) is ongebruikte, maar bewust niet verwijderde
code.** Die draait alleen als `fetch("app")` faalt (geen server) — in deze
tool draait er altijd een server, dus dit pad wordt in de praktijk nooit
gebruikt, behalve als noodgreep wanneer de server tijdens gebruik wegvalt
(`verversViaApp`'s catch-blok zet dan `VIA_APP=false`). Verwijderen zou de
1-op-1-overname minder letterlijk maken voor weinig winst; laten staan kost
niets (het weegt niet mee in wat de browser laadt totdat het echt nodig is).
Bijkomend voordeel: de bronrepo's eigen `test_spiegel.py` bewijst al dat deze
JS-motor hetzelfde resultaat geeft als `samenstellen.py` — dat is hier niet
opnieuw getest, maar de logica zelf is ongewijzigd overgenomen.

## `scherm/*.js` staan zonder modules naast elkaar

`calculatie.js` wordt als gewoon `<script>` geladen (geen `type=module`) en
deelt dus één globale scope met `gedeeld.js`. Het is daarom in een IIFE
gewrapt — zonder dat botsen `const`/`let` op topniveau met wat `gedeeld.js`
daar zelf neerzet. Voeg je een derde scherm-bestand toe dat **op dezelfde
pagina** als `gedeeld.js` draait (dus niet `scherm/brief.html`, dat is een
eigen pagina zonder gedeelde scripts), wrap het dan ook in een IIFE, of zet
het als module.

## Server-static-bestanden: het pad-voorvoegsel is verplicht

`server.py` serveert `scherm/` en `data/` alleen onder hun eigen
voorvoegsel (`/scherm/app.js`, `/data/foo.json`) — nooit op de root. HTML/JS
die naar deze bestanden verwijst moet dus `scherm/...` schrijven, niet een
kale bestandsnaam (die zou naar `/bestand.js` resolven, wat een 404 geeft).

## De dubbelklik-opstarters gaan uit van hun plek in de projectmap

`Calcu-Brief-tool.app` (Mac) en `start-app.pyw`/`start.bat` (Windows) vinden
`server.py` via een relatief pad vanaf hun eigen locatie — ze moeten dus
in de projectmap blijven staan. Een `.app` die je los naar het Bureaublad
sleept, verliest die relatie; een Finder-alias (of op Windows een
snelkoppeling) niet, vandaar dat de README dat aanraadt in plaats van
verplaatsen/kopiëren. macOS start een `.app`-bundel headless (geen
Terminal-venster): `Contents/MacOS/start` toont fouten daarom als
`osascript display alert` in plaats van ze te printen, en logt de server
zelf naar `.calcubrief-server.log` (gitignored) voor het geval de melding
niet genoeg zegt. Windows-equivalent: `start-app.pyw` draait via
`pythonw.exe` (geen console) en gebruikt `tkinter.messagebox` voor
foutmeldingen.

## De standalone build: `--onedir`, niet `--onefile`

`.github/workflows/build-app.yml` bouwt met PyInstaller op GitHub's eigen
Windows-/Mac-runners (een .exe/.app is niet vanaf Linux te cross-compileren).
Windows gebruikt expliciet `--onedir`: een `--onefile`-.exe pakt zichzelf bij
**elke** start opnieuw uit naar een tijdelijke map voordat er ook maar één
regel Python draait — met het laadscherm-filmpje erbij (~7MB) merkbaar genoeg
om, in combinatie met een dubbelklik die daarna ook nog op de browser moet
wachten, als "traag opstarten" op te vallen. `--onedir` slaat die uitpakstap
over; de prijs is dat de download een map is (`CalcuBriefTool-windows.zip`
uitpakken, `CalcuBriefTool.exe` **in** die map dubbelklikken) in plaats van
één los bestand. Mac gebruikt sowieso al `--onedir` (PyInstaller's eigen
standaard, alleen Windows had `--onefile` nodig gehad om er één bestand van
te maken) — vandaar dat daar niets hoefde te veranderen.

`server.py`'s `WORTEL`/`DATA_MAP`/`SJABLOON`/`SCHERM_MAP` (frozen-detectie via
`sys.frozen`/`sys._MEIPASS`, zie de constante bovenin het bestand) werken
voor beide PyInstaller-modi identiek: `sys._MEIPASS` wijst bij `--onedir` naar
de map naast de `.exe` in plaats van een tijdelijke uitpakmap, maar de code
hoeft dat onderscheid niet te kennen.

## Laadscherm: native (vóór de browser) + een overlay in de pagina

**Waarom niet gewoon een pagina met het filmpje?** Eerdere versie opende de
browser meteen naar zo'n pagina (`scherm/splash.html`, inmiddels verwijderd).
Bleek niet te werken: het echte "duurt lang"-moment bij een gebouwde `.exe`
is niet de tijd die de tool zelf nodig heeft (bibliotheek/calculatiegegevens
laden is een kwestie van milliseconden), maar de tijd die de browser zelf
nodig heeft om als apart programma op te starten — en tot die browser er is,
kan geen enkele HTML-pagina iets laten zien. Dat gaf een "blauwe laadcirkel"
van 10-20s met niets erachter, precies het probleem dat opgelost moest
worden.

**Laag 1 — het native laadscherm**, `_toon_native_laadscherm()` in
`server.py`, draait daarom vóórdat de browser wordt geopend, als een eigen,
kaderloos venster (tkinter, stdlib, geen nieuwe afhankelijkheid). tkinter kan
geen video afspelen, dus dit speelt `scherm/laadscherm.gif` (per frame via
`tk.PhotoImage(..., format="gif -index N")`) — die gif bestaat alleen in een
gebouwde `.exe`/`.app`, gemaakt uit `scherm/laadscherm.mp4` door een
ffmpeg-stap in `.github/workflows/build-app.yml` (12 fps, moet gelijk
blijven aan `LAADSCHERM_FPS` in `server.py`). Draai je vanuit de broncode
(geen gif aanwezig), dan slaat `start()` dit laagje gewoon over en opent de
browser zoals voorheen — `_native_laadscherm_pad()` geeft dan `None` terug.
`serve_forever()` draait daarom op een eigen thread: tkinter's `mainloop()`
moet op de hoofdthread (harde eis, vooral op macOS), en de server moet
tegelijk al kunnen luisteren.

**Dit is het enige stuk van de hele tool dat niet vanuit deze omgeving te
testen was** (geen tkinter, geen beeldscherm in de sandbox waarin dit
gebouwd is) — bij een wijziging hier dus extra voorzichtig zijn en op een
echte Windows-/Mac-machine controleren. Elke fout in
`_toon_native_laadscherm()` wordt in `start()` opgevangen: bij een probleem
(geen tkinter, corrupte gif, geen beeldscherm) print het een waarschuwing en
opent gewoon de browser, in plaats van de app te laten crashen op wat
uiteindelijk maar een laadscherm is.

**Laag 2 — de overlay in `scherm/index.html`** (`#laadscherm`, spinner-only)
dekt de eigen, veel kortere data-ophaal-stap van de calculatiestap zelf af
zodra de browser eenmaal open is: verdwijnt pas als `CB.calc.klaar` is
opgelost (zie de inline `<script>` onderaan dat bestand), dus na de
materiaalcatalogus/YIMM/Panasonic/Daikin-data en de eerste `/bereken`-ronde.
Voeg je een nieuwe async opstartstap toe aan de calculatiestap, neem die dan
op in die `klaar`-promise, anders verdwijnt deze overlay te vroeg.
`MINIMALE_DUUR_MS` staat hier laag (300ms, alleen om een flits-en-weg-effect
te voorkomen) — het filmpje zelf hoort nu alleen bij laag 1. `scherm/brief.html`
is een eigen pagina met zijn eigen (eenvoudigere) laadgedrag, zie hierboven.

## Git

Ontwikkel op de branch `claude/magical-davinci-63dmec`. Commitberichten in
het Nederlands, beschrijvend (niet gebiedende wijs, niet verleden tijd), met
uitleg van het waarom bij niet voor de hand liggende keuzes.
