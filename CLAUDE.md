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

## De autosave moet gelezen worden vóór de eerste `renderAll()`, niet erna

`renderAll()` (`scherm/calculatie.js`) roept aan het eind altijd `CB.autosave()`
aan — ook tijdens de allereerste berekening bij het opstarten van de
calculatiestap, met dan nog de lege `nieuweStaat()`. `initCalculatie()` laadt
de bewaarde staat daarom zelf, vóór die eerste `renderAll()`:

    state = CB.leesAutosaveCalculatie() || nieuweStaat();

**Dit stond eerder andersom en dat gaf een leeg calculatieblad bij elke
terugkeer naar deze pagina** (de "← Calculatie"-link in `scherm/brief.html`,
maar ook een gewone F5). De oude opzet liet `index.html` pas ná
`CB.calc.klaar` de bewaarde staat inladen (`CB.laadAutosave()`, die
`CB.calc.vulStaat()` aanriep) — maar `CB.calc.klaar` (dus `initCalculatie()`)
was op dat moment allang minstens één keer door `renderAll()` heen geweest,
die de dan nog lege `nieuweStaat()` al naar `localStorage` had weggeschreven.
Het bewaarde project was dus alweer overschreven met lege staat vóórdat er
ooit naar gekeken werd — de data stond op het moment van wegnavigeren nog
prima in `localStorage`, maar was tegen de tijd dat er iets mee gedaan werd
alweer weg.

`CB.leesAutosaveCalculatie()` (`scherm/gedeeld.js`) is daarom bewust een pure
leesfunctie zonder side-effect op `CB.calc` (in tegenstelling tot de oude
`CB.laadAutosave()`, die naast lezen ook meteen `vulStaat()`+`renderAll()`
aanriep) — `initCalculatie()` gebruikt het resultaat gewoon als startwaarde
van `state`, en de daaropvolgende `bindMeta()`/.../`herbereken()`-reeks
rendert daar vanzelf één keer overheen. Voeg je zelf iets toe dat de
calculatiestaat ergens vroeg in het opstarten leest of overschrijft: doe dat
vóór de eerste `renderAll()`/`herbereken()`-aanroep in `initCalculatie()`,
niet erna vanuit `index.html`.

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

## De Release-pagina wordt door één losse job beheerd, na beide builds

`windows` en `macos` in `build-app.yml` bouwen alleen en leveren hun zip af
als workflow-artifact (`actions/upload-artifact`) — geen van beide raakt de
Release-pagina zelf aan. Een aparte `publiceer`-job (`needs: [windows,
macos]`, `ubuntu-latest`, ver goedkoper dan nog een Windows-/Mac-runner)
haalt beide artifacts op (`actions/download-artifact`) en is de enige plek
die `gh release` aanroept — dat voorkomt dat "windows lukt, mac loopt vast"
de mac-job voor een lastige keuze stelt over een release-object dat windows
net had opgezet.

**Het echte probleem bleek de navraag, niet de upload.** Een aantal eerdere
versies van deze stap (zie git-historie) trokken, op basis van `gh release
view --json assets` die na een upload leeg bleef, de conclusie dat GitHub's
release-API de upload zelf liet mislukken — met als "oplossing" steeds
grovere pogingen: `--clobber`, een losse `gh release delete-asset` vooraf, en
uiteindelijk de hele release bij elke mislukte navraag weggooien en opnieuw
aanmaken. Een diagnostische versie van deze stap (zonder foutonderdrukking,
met de rauwe JSON via `gh api repos/OWNER/REPO/releases/tags/app-download`
in plaats van `gh release view`) liet uiteindelijk zien dat dit een
verkeerde diagnose was: `gh release upload` gaf steeds gewoon exitcode 0, en
`gh api` op diezelfde release liet **seconden** na de upload, in dezelfde
job, al beide assets zien met `"state": "uploaded"` en de juiste
bestandsgrootte. De uploads werkten dus de hele tijd al.

`gh release view --json assets` zelf bleek het onbetrouwbare stuk: die bleef
ook ver na een bewezen geslaagde upload nog `assets: []` teruggeven — zelfs
een onafhankelijke navraag (niet via `gh`, een aparte losse API-aanroep)
liet pas na zo'n **kwartier** de echte, juiste asset-lijst zien. Met andere
woorden: de eerdere "fixes" reageerden op een navraagmethode die simpelweg
traag/onbetrouwbaar is voor een net aangemaakte release, en loste daarmee
niets op — erger nog, het herhaaldelijk weggooien-en-opnieuw-aanmaken van de
hele release bij zo'n foute "nee" kan een release hebben vernietigd waarvan
de assets allang goed stonden, alleen nog niet zichtbaar via die navraag.

**De huidige opzet.** Eén keer verwijderen + aanmaken (geen herhaal-cyclus
van de hele release meer), dan allebei de bestanden uploaden (met een kleine
retry per bestand als de upload zelf een keer mislukt — niet als de navraag
niets laat zien), en ná een korte wachttijd navragen via `gh api ...
--jq '.assets[].name'` — nadrukkelijk niet via `gh release view --json
assets`, want die bleek bij herhaling het onbetrouwbare stuk. Zie je zelf
(bijv. via de GitHub API, of door meteen na een build de Release-pagina te
verversen) dat een net gepubliceerd bestand er nog niet lijkt te staan: geef
het gewoon een paar minuten, er hoeft niets opnieuw gebouwd of gepubliceerd
te worden — de asset staat er wel, de weergave loopt alleen nog achter. De
downloadlink (`.../releases/tag/app-download`) blijft ondertussen hetzelfde,
want de tagnaam verandert niet.

## Laadscherm: het filmpje speelt in de browser, niet meer native ervoor

**Wat er eerst was geprobeerd, en waarom dat uitgeschakeld is.** Om het
"duurt lang"-moment tussen dubbelklikken op de `.exe` en het openen van de
browser (10-20s blauwe laadcirkel, met niets erachter) te dekken, speelde
`server.py` vóór het openen van de browser `scherm/laadscherm.mp4` af als
gif in een eigen, kaderloos tkinter-venster. Dit was letterlijk het enige
stuk van de hele tool dat niet vanuit deze ontwikkelomgeving te testen was
(geen tkinter, geen beeldscherm in de sandbox) — en het bleek op een echte
Windows-machine de app te laten crashen vóórdat er iets te zien was, op een
manier die zelfs Python's eigen foutafhandeling omzeilde (leeg
`calcubrief-log.txt`, wat op een harde, native crash wijst, vermoedelijk in
de Tcl/Tk-bibliotheek zelf). Zie git-historie voor de volledige diagnose;
dit is toen volledig verwijderd uit `server.py` (geen
`_toon_native_laadscherm()`/`_native_laadscherm_pad()`/`LAADSCHERM_FPS`
meer) en `build-app.yml` (geen ffmpeg/gif-stap meer).

**Nu speelt het filmpje in de pagina zelf** — gewoon een `<video>`-element
(`#laadschermVideo`) in de `#laadscherm`-overlay van `scherm/index.html`,
niet meer native vóórdat de browser open is. Dat is fundamenteel veiliger:
een `<video>` draait in de browser's eigen sandbox, dus een probleem daarmee
(ontbrekend bestand, browser ondersteunt de codec niet) kan nooit meer de
hele app meetrekken zoals de tkinter-versie deed. `CB.laadscherm.init()`
(`scherm/gedeeld.js`) luistert daarom naar het `error`-event op de video en
valt bij zo'n fout terug op de oude spinner (`#laadschermMerk` +
`#laadschermSpinner`, beide standaard verborgen) in plaats van een lege plek
waar het filmpje stond — dat gebeurde ook echt tijdens het bouwen hiervan:
de headless Chromium in deze ontwikkelomgeving kan dit specifieke bestand
niet decoderen (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, vermoedelijk een build
zonder H.264-ondersteuning) — een goede, onbedoelde test van precies dit
terugvalpad. Reguliere browsers (Chrome/Edge/Safari op een echte pc/Mac)
ondersteunen H.264/AAC in mp4 wél gewoon.

**`MINIMALE_DUUR_MS` is expres (ongeveer) de duur van het filmpje** (10,24s
op het moment van schrijven, `10300` als terugvalwaarde in de code totdat
`loadedmetadata` de echte duur teruggeeft), niet meer een klein getal om
alleen een flits-en-weg-effect te voorkomen. Reden: de data-ophaal-stap
hieronder is lokaal typisch een kwestie van milliseconden, dus zonder deze
langere wachttijd zou de overlay (met het filmpje erin) al verwijderd worden
ruim vóórdat het filmpje ook maar goed geladen is — de browser breekt zo'n
nog lopende download dan gewoon af (`net::ERR_ABORTED`, ook zo aangetroffen
tijdens het testen hiervan), waardoor het filmpje in de praktijk vrijwel
nooit te zien zou zijn geweest. Bij een `error` (zie hierboven) heeft
wachten geen zin meer: `_toonSpinnerTerugval()` zet `MINIMALE_DUUR_MS` dan
terug naar 300ms, zodat een gebruiker bij wie het filmpje niet afspeelt niet
alsnog onnodig 10 seconden naar een spinner hoeft te staren.

**`scherm/laadscherm.mp4` wordt weer meegepakt in de build** (`--add-data
"scherm;scherm"` bevat het al, dus er was geen aparte stap nodig) — de
eerdere "verwijder het filmpje uit de build"-stappen in `build-app.yml` zijn
verwijderd, want het bestand wordt nu wél gebruikt. Vervang je dit bestand
ooit door een andere versie: de duur wordt automatisch opnieuw uitgelezen
(zie `loadedmetadata` in `CB.laadscherm.init()`), dus de `10300`-terugvalwaarde
hoeft dan niet per se aangepast te worden (die is toch alleen de korte
overbrugging vóórdat de echte duur bekend is) — wel zo netjes om 'm bij een
bewuste, blijvende vervanging alsnog bij te werken zodat de code zichzelf
blijft documenteren.

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

**De overlay in `scherm/index.html`** (`#laadscherm`, met het filmpje erin,
zie hierboven) dekt de eigen data-ophaal-stap van de calculatiestap zelf af
zodra de browser eenmaal open is: verdwijnt pas als zowel `CB.calc.klaar` is
opgelost (zie de inline `<script>` onderaan dat bestand) als de
`MINIMALE_DUUR_MS`-wachttijd voorbij is — dus na de materiaalcatalogus/YIMM/
Panasonic/Daikin-data, de eerste `/bereken`-ronde, én (in het normale geval)
het filmpje. Voeg je een nieuwe async opstartstap toe aan de calculatiestap,
neem die dan op in die `klaar`-promise, anders verdwijnt deze overlay te
vroeg. `scherm/brief.html` is een eigen pagina met zijn eigen (eenvoudigere)
laadgedrag, zie hierboven.

## Git

Ontwikkel op de branch `claude/magical-davinci-63dmec`. Commitberichten in
het Nederlands, beschrijvend (niet gebiedende wijs, niet verleden tijd), met
uitleg van het waarom bij niet voor de hand liggende keuzes.
