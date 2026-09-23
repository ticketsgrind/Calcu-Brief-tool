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

## `CB.getJSON`/`CB.postJSON`: de foutafhandeling loopt uiteen, met opzet

`CB.getJSON` (`scherm/gedeeld.js`) is alleen voor statische `/data/*.json`-
bestanden en gooit een fout bij elke niet-2xx-status. `CB.postJSON` is voor
de RPC-achtige endpoints (`/bereken`, `/overdracht`, `/brief`, ...) die
bewust een niet-2xx-status mét een `{"fout": "..."}`-body teruggeven, die de
aanroeper zelf afhandelt (bijv. `if (resultaat.fout) { CB.toast(...) }` in
`calculatie.js`) — die blijft daarom werken ongeacht de statuscode. Verwar
deze twee niet: een missend statisch bestand geeft in `server.py` óók een
`{"fout": "onbekend adres"}`-body (dezelfde generieke 404-handler als voor
elk onbekend pad), dus zonder de aparte, strengere controle in `getJSON` zou
zo'n missend bestand stilzwijgend als (verkeerde) data zijn gebruikt in
plaats van een duidelijke fout te geven — precies gebeurd bij het uitzoeken
van een "laadscherm blijft oneindig draaien"-melding.

**`CB.calc.klaar` (index.html) heeft daarom ook een `.catch()`, niet alleen
een `.then()`.** Zonder die `.catch()` bleef het laadscherm-overlay bij zo'n
mislukte data-ophaal-stap eindeloos draaien: de promise-keten wees dan
gewoon nergens meer heen, en `CB.laadscherm.verberg()` (in de `.then()`)
werd dus nooit aangeroepen — voor de gebruiker geen enkel verschil met
"duurt gewoon nog even", met geen enkele aanwijzing wat er misging.
`CB.laadscherm.toonFout(fout)` toont die fout nu in plaats daarvan in het
laadscherm zelf. Voeg je een nieuwe async opstartstap toe aan de
calculatiestap (zie ook de laadscherm-sectie hierboven): laat een fout
daarin altijd omhoogkomen (gooi 'm, vang 'm niet stil weg) zodat hij hier
terechtkomt, in plaats van een tweede stille-hang-plek te scheppen.

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

## Laadscherm: het native filmpje is uitgeschakeld (crashte op een echte machine)

**Wat er was geprobeerd.** Om het "duurt lang"-moment tussen dubbelklikken op
de `.exe` en het openen van de browser (10-20s blauwe laadcirkel, met niets
erachter) te dekken, speelde `server.py` vóór het openen van de browser
`scherm/laadscherm.mp4` af als gif (`tk.PhotoImage(..., format="gif -index
N")`) in een eigen, kaderloos tkinter-venster. De gif werd bij het bouwen
gemaakt uit het filmpje via ffmpeg (`.github/workflows/build-app.yml`,
inmiddels ook weer verwijderd).

**Waarom dat nu uitgeschakeld is.** Dit was letterlijk het enige stuk van de
hele tool dat niet vanuit deze ontwikkelomgeving te testen was (geen
tkinter, geen beeldscherm in de sandbox) — en het bleek op een echte
Windows-machine de app te laten crashen vóórdat er iets te zien was. Niet op
een manier die met een gewone `try`/`except` op te vangen was: het
logbestand (zie hieronder) bevatte na zo'n mislukte poging geen enkele
regel, ook niet de allereerste regel die altijd meteen bij het opstarten
wordt weggeschreven — dat wijst op een harde, native crash (vermoedelijk in
de Tcl/Tk-bibliotheek zelf) die het hele proces meeneemt vóórdat Python's
eigen foutafhandeling of bestand-buffering nog kan draaien. Een oudere build
van vóór dit laadscherm bestond (destijds nog `--onefile`, dus zonder de
`_internal`-map met `tcl86t.dll`/`tk86t.dll`) werkte op diezelfde machine
wel altijd probleemloos, wat dit bevestigde.

Gezien dit al meerdere keren de hele app onbruikbaar maakte voor collega's,
en niet op afstand te diagnosticeren viel (geen Windows-machine hier, en de
fout omzeilt Python's eigen foutafhandeling), is dit weer uitgeschakeld:
`server.py` opent na het opstarten van de server nu weer gewoon direct de
browser (`threading.Timer(0.4, ...)`), zoals vóór dit filmpje er was.
`scherm/laadscherm.mp4` staat nog gewoon in de repository (voor als dit ooit
veiliger opnieuw wordt opgepakt, bijv. door het filmpje in een apart proces
te tonen zodat een crash daar niet de hele app meeneemt), maar wordt niet
meer meegepakt in de build (zie de "verwijder het filmpje"-stap in
`build-app.yml`) en er is geen ffmpeg/gif-stap meer nodig.

**De rest van de laadscherm-diagnostiek blijft wel relevant.** Een
`--windowed`/`--noconsole`-build (zowel de Windows-.exe als de Mac-.app)
heeft geen console — `sys.stdout`/`sys.stderr` zijn dan `None`, geen
writable stream. Een doodgewone `print()` (er staan er een paar, vlak na het
opstarten van de server, vóór de browser wordt geopend) crasht zo'n build
dan met een `AttributeError` — onzichtbaar, want er is geen console om iets
te tonen: de app "doet niets". `pythonw.exe` (`start-app.pyw`) heeft
hetzelfde probleem, ook zonder frozen build. Fix: bovenin `server.py` wordt
`sys.stdout`/`sys.stderr` vervangen als ze `None` zijn, vóór er ergens
geprint wordt -- bij een gebouwde app naar `calcubrief-log.txt` naast de
.exe/.app (regel-gebufferd, niet naar een stille `os.devnull`-sink: dat
loste de crash op maar maakte een volgend probleem juist onmogelijk te
diagnosticeren). Direct na die omwisseling wordt altijd één regel gelogd
("opgestart, <tijdstip>") — staat die regel er niet eens in bij een volgend
probleem, dan is de app niet eens tot in `server.py` gekomen, of is
midden in iets abrupt afgebroken (een harde/native crash, zoals hierboven
bij het laadscherm) — allebei iets heel anders dan een gewone Python-fout,
die wél in het logbestand terechtkomt vóórdat `main()`'s eigen
`tkinter.messagebox`-foutmelding verschijnt (alleen wanneer `sys.frozen`
waar is). Kortom: **een "doet niets bij het opstarten"-melding voor de
gebouwde app** — check eerst of `calcubrief-log.txt` bestaat en wat erin
staat (leeg bestand = harde crash, geen bestand = nog niet eens tot in
`server.py` gekomen, een foutmelding erin = een gewone, opgevangen fout).

**De overlay in `scherm/index.html`** (`#laadscherm`, spinner-only) dekt de
eigen, veel kortere data-ophaal-stap van de calculatiestap zelf af zodra de
browser eenmaal open is: verdwijnt pas als `CB.calc.klaar` is opgelost (zie
de inline `<script>` onderaan dat bestand), dus na de materiaalcatalogus/
YIMM/Panasonic/Daikin-data en de eerste `/bereken`-ronde. Voeg je een nieuwe
async opstartstap toe aan de calculatiestap, neem die dan op in die
`klaar`-promise, anders verdwijnt deze overlay te vroeg. `MINIMALE_DUUR_MS`
staat hier laag (300ms, alleen om een flits-en-weg-effect te voorkomen).
`scherm/brief.html` is een eigen pagina met zijn eigen (eenvoudigere)
laadgedrag, zie hierboven.

## Git

Ontwikkel op de branch `claude/magical-davinci-63dmec`. Commitberichten in
het Nederlands, beschrijvend (niet gebiedende wijs, niet verleden tijd), met
uitleg van het waarom bij niet voor de hand liggende keuzes.
