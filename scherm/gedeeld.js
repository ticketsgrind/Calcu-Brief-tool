'use strict';
/* Gedeelde hulpfuncties tussen de calculatie- en briefstap: formattering,
   de server aanroepen, het gecombineerde projectbestand opslaan/openen, en
   het wisselen tussen de twee stappen. Beide stappen registreren zichzelf in
   window.CB zodat dit bestand ze kan aanspreken zonder van hun interne
   opbouw af te weten. */
window.CB = window.CB || {};

CB.eur = n => (n === null || n === undefined || isNaN(n)) ? '—'
  : '€ ' + (n + 0).toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
CB.pct = n => (n === null || n === undefined || isNaN(n)) ? '—'
  : (n * 100).toLocaleString('nl-NL', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + '%';

// Sommige RPC-verzoeken (/bereken, /overdracht, ...) antwoorden met een
// niet-2xx-status én een JSON-body ({"fout": "..."}) die de aanroeper zelf
// afhandelt -- postJSON blijft die dus ongeacht de statuscode teruggeven.
// CB.getJSON is alleen voor statische /data/*.json-bestanden: een 404 daar
// betekent altijd een genuine fout (bijv. een bestand dat in een gebouwde
// .exe/.app onverhoopt niet is meegepakt), nooit een bewust "fout"-antwoord
// om af te handelen -- en de 404-handler in server.py levert toevallig ook
// gewoon geldige JSON ({"fout": "onbekend adres"}), dus zonder de eigen
// statuscontrole hieronder zou zo'n missend bestand stilzwijgend als
// (verkeerde) data worden gebruikt in plaats van een duidelijke fout te
// geven.
CB.postJSON = async (pad, lichaam) => {
  const respons = await fetch(pad, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(lichaam || {}),
  });
  const tekst = await respons.text();
  try {
    return JSON.parse(tekst);
  } catch (fout) {
    throw new Error(`${pad} gaf geen geldig antwoord (${respons.status} ${respons.statusText})`);
  }
};

CB.getJSON = async pad => {
  const respons = await fetch(pad);
  if (!respons.ok) throw new Error(`${pad} gaf ${respons.status} ${respons.statusText}`);
  return respons.json();
};

CB.debounce = (fn, ms) => {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
};

/* ------------------------------- laadscherm ------------------------------ */
// Het laadscherm-filmpje speelt hier gewoon in de pagina (een <video>-
// element in #laadscherm, index.html) -- niet meer native vóór de browser
// open is zoals eerder werd geprobeerd (zie CLAUDE.md §Laadscherm): dat
// crashte op een echte machine, doordat een fout in de native video-weergave
// het hele proces meetrok. Een <video>-element draait in de browser's eigen
// sandbox en kan dat niet meer doen; init() hieronder vangt een mislukte
// afspeelpoging (ontbrekend bestand, browser ondersteunt de codec niet) af
// met een terugval naar de oude spinner, in plaats van een lege plek waar
// eerst het filmpje stond. Deze overlay dekt zo ook de eigen data-ophaal-
// stap van de calculatiestap (materiaalcatalogus/YIMM/Panasonic/Daikin, de
// eerste /bereken-ronde) af -- blijft zichtbaar tot CB.calc.klaar is
// opgelost, zie de aanroep van CB.laadscherm.verberg() onderaan index.html.
//
// MINIMALE_DUUR_MS is expres (ongeveer) net zo lang als het filmpje: de
// data-ophaal-stap is hier lokaal typisch een kwestie van milliseconden,
// dus zonder deze wachttijd zou verberg() de hele #laadscherm-div (met het
// filmpje erin) al weghalen ruim vóórdat het filmpje ook maar goed en wel
// geladen is -- de browser breekt zo'n nog lopende download dan af
// (net::ERR_ABORTED), dus zonder deze wachttijd zou het filmpje in de
// praktijk vrijwel nooit te zien zijn. init() leest de echte duur van het
// filmpje uit zodra die bekend is (dus dit blijft kloppen als
// scherm/laadscherm.mp4 ooit door een andere versie vervangen wordt); de
// waarde hieronder is alleen de terugval voor de korte periode vóórdat die
// metadata binnen is, en (in het onwaarschijnlijke geval dat die nooit
// binnenkomt) voor de rest van die sessie -- 10240ms is de duur van het
// filmpje op het moment van schrijven.
CB.laadscherm = {
  _vanaf: Date.now(),
  MINIMALE_DUUR_MS: 10300,
  // Wordt onderaan dit bestand meteen aangeroepen: de #laadscherm-elementen
  // staan al in de DOM (dit script staat onderaan de body), dus dat hoeft
  // niet op DOMContentLoaded te wachten.
  init() {
    const video = document.getElementById('laadschermVideo');
    if (!video) return;
    video.addEventListener('error', () => this._toonSpinnerTerugval());
    video.addEventListener('loadedmetadata', () => {
      if (isFinite(video.duration) && video.duration > 0) {
        this.MINIMALE_DUUR_MS = Math.ceil(video.duration * 1000) + 100;
      }
    });
  },
  _toonSpinnerTerugval() {
    const video = document.getElementById('laadschermVideo');
    const merk = document.getElementById('laadschermMerk');
    const spinner = document.getElementById('laadschermSpinner');
    if (video) video.style.display = 'none';
    if (merk) merk.style.display = '';
    if (spinner) spinner.style.display = '';
    // Geen filmpje meer om op te wachten -- de lange MINIMALE_DUUR_MS
    // hierboven bestaat alleen om het filmpje de tijd te geven, dus die
    // wachttijd heeft hier geen functie meer en zou de gebruiker onnodig
    // op de spinner laten wachten.
    this.MINIMALE_DUUR_MS = 300;
  },
  zetStatus(tekst) {
    const el = document.getElementById('laadschermStatus');
    if (el) el.textContent = tekst;
  },
  verberg() {
    const el = document.getElementById('laadscherm');
    if (!el) return;
    const wachttijd = Math.max(0, this.MINIMALE_DUUR_MS - (Date.now() - this._vanaf));
    setTimeout(() => {
      el.classList.add('klaar');
      setTimeout(() => el.remove(), 400);
    }, wachttijd);
  },
  // Zonder dit bleef het scherm bij een mislukte data-ophaal-stap eindeloos
  // draaien: CB.calc.klaar.then(...) vuurt dan nooit (geen .catch() erop),
  // en verberg() wordt dus ook nooit aangeroepen -- voor de gebruiker geen
  // enkel verschil met "duurt gewoon nog even". Toon in plaats daarvan wat
  // er misging, in de plek waar toch al naar gekeken wordt.
  toonFout(fout) {
    const video = document.getElementById('laadschermVideo');
    if (video) video.style.display = 'none';
    const spinner = document.getElementById('laadschermSpinner');
    if (spinner) spinner.style.display = 'none';
    const el = document.getElementById('laadschermStatus');
    if (!el) return;
    el.style.color = '#ffb4b4';
    el.textContent = 'Er ging iets mis bij het laden: ' + (fout && fout.message || fout)
      + '. Probeer de pagina te verversen (F5); blijft dit gebeuren, stuur deze melding door.';
  },
};
CB.laadscherm.init();

CB.toast = msg => {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(CB._toastTimer);
  CB._toastTimer = setTimeout(() => el.classList.remove('show'), 2200);
};

/* ------------------------------ projectbestand ----------------------------- */
// Alleen de calculatie: de brief is een eigen pagina (scherm/brief.html) met
// zijn eigen Opslaan/Openen/Nieuw voor het briefconcept, zo goed als 1-op-1
// overgenomen van de losstaande brieventool (zie CLAUDE.md). Vroeger stond
// hier ook CB.brief.antwoorden in hetzelfde bestand; dat is losgekoppeld
// toen de brief-tab plaatsmaakte voor die eigen pagina.

const PROJECT_MERK = 'calcu-brief-project';

// Eén project kan meerdere losse calculaties ("opties") bevatten sinds
// versie 2 (zie CLAUDE.md) -- vóór die tijd was er precies één `calculatie`.
// Zet een geopend of bewaard projectbestand om naar een lijst opties, met
// terugval op dat oudere formaat zodat een bestaand opgeslagen bestand of
// browser-autosave gewoon blijft werken, als "Optie A". Geeft null terug als
// het bestand geen van beide vormen heeft.
CB.optiesUitProject = project => {
  if (project && Array.isArray(project.opties) && project.opties.length) {
    return project.opties.map(o => ({ naam: o.naam || 'Optie', staat: o.calculatie || CB.calc.nieuweStaat() }));
  }
  if (project && project.calculatie) {
    return [{ naam: 'Optie A', staat: project.calculatie }];
  }
  return null;
};

CB.huidigProject = () => ({
  merk: PROJECT_MERK,
  versie: 2,
  opties: CB.calc.alleOpties().map(o => ({ naam: o.naam, calculatie: o.staat })),
  actieveOptie: CB.calc.actieveOptieIndex,
});

CB.heeftInhoud = () => CB.calc.heeftInhoud();

// scherm/brief.html doet dit zelf nog een keer (veiligeNaamdeel daar): het is
// een losstaande pagina zonder gedeelde scripts met deze kant van de tool.
CB.veiligeBestandsnaamdeel = tekst => String(tekst || '').trim().replace(/[\\/:*?"<>|]+/g, '-');

CB.projectBestandsnaam = () => {
  // Van de EERSTE optie: dat is ook waar overdracht.zet_meerdere_over()
  // (Python) de projectbrede velden (klant, datum, Q-nummer) vandaan haalt --
  // dezelfde regel hier houdt de bestandsnaam daarmee in lijn.
  const eerste = CB.calc.alleOpties()[0];
  const meta = (eerste && eerste.staat.meta) || {};
  const delen = [meta.klantnaam, meta.projectnaam].map(CB.veiligeBestandsnaamdeel).filter(Boolean);
  const naam = delen.length ? `Calculatie-${delen.join('-')}` : 'Calculatie';
  return naam + '.json';
};

CB.bindOpslaanOpenen = () => {
  document.getElementById('btnOpslaan').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify(CB.huidigProject(), null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = CB.projectBestandsnaam();
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    CB.toast('Project opgeslagen als ' + a.download);
  });

  const fileInput = document.getElementById('fileInput');
  document.getElementById('btnOpenen').addEventListener('click', () => {
    if (CB.heeftInhoud() && !confirm('Er staat al iets ingevuld. Dit overschrijven met het geopende bestand?')) return;
    fileInput.value = '';
    fileInput.click();
  });
  fileInput.addEventListener('change', () => {
    const bestand = fileInput.files[0];
    if (!bestand) return;
    const lezer = new FileReader();
    lezer.onload = () => {
      let project;
      try { project = JSON.parse(lezer.result); }
      catch (e) { return CB.toast('Kan dit bestand niet lezen: geen geldige JSON.'); }
      if (project.merk !== PROJECT_MERK) {
        return CB.toast('Dit is geen calculatie-projectbestand.');
      }
      const opties = CB.optiesUitProject(project) || [{ naam: 'Optie A', staat: CB.calc.nieuweStaat() }];
      CB.calc.vulOpties(opties, project.actieveOptie || 0);
      CB.toast('Project geopend.');
    };
    lezer.readAsText(bestand);
  });

  document.getElementById('btnNieuw').addEventListener('click', () => {
    if (CB.heeftInhoud() && !confirm('Alles wissen? Niet-opgeslagen wijzigingen gaan dan verloren.')) return;
    CB.calc.vulOpties([{ naam: 'Optie A', staat: CB.calc.nieuweStaat() }], 0);
    CB.toast('Nieuw project gestart.');
  });
};

/* Vangnet binnen deze ene sessie (tabblad), geen archief: een stap naar de
   brief en terug (of een F5) verliest niets, maar het sluiten van het
   tabblad/de app wist deze stand bewust -- op verzoek van Lars (2 oktober
   2026): de tool liet bij een nieuwe calculatie nog de vorige klant zien,
   omdat localStorage (vóór deze wijziging) over een afgesloten en opnieuw
   geopend tabblad heen bleef bestaan. sessionStorage deelt die eigenschap
   niet: die overleeft navigatie/herladen binnen hetzelfde tabblad prima
   (precies wat deze autosave moet doen), maar is leeg zodra de app een
   nieuw tabblad opent (een nieuwe werksessie) -- zie ook de
   beforeunload-waarschuwing in index.html, de andere helft van deze
   wijziging: die vangt nu op wat sessionStorage niet meer doet (per ongeluk
   sluiten met niet-opgeslagen werk). Dezelfde sleutel wordt ook door
   scherm/brief.html gelezen (nooit weggeschreven) om de calculatiegegevens
   over te nemen -- zie CALCULATIE_CONCEPT_SLEUTEL daar, ook omgezet naar
   sessionStorage. */
const AUTOSAVE_SLEUTEL = 'calcubrief.concept';

CB.autosave = () => {
  try { sessionStorage.setItem(AUTOSAVE_SLEUTEL, JSON.stringify(CB.huidigProject())); }
  catch (e) { /* sessionStorage kan vol/uitgeschakeld zijn; geen ramp */ }
};

// Puur lezen, geen side-effect op CB.calc -- gebruikt door initCalculatie()
// (calculatie.js) om de startstaat te bepalen vóór de eerste renderAll().
// Dat "vóór" is geen toeval: renderAll() roept zelf altijd CB.autosave() aan
// (ook tijdens de allereerste berekening bij het opstarten, met dan nog de
// lege nieuweStaat()) -- werd deze functie pas ná die eerste renderAll()
// aangeroepen (zoals eerder gebeurde, via CB.calc.vulStaat() vanuit
// index.html's CB.calc.klaar.then()), dan was de bewaarde autosave dus al
// overschreven met lege staat vóórdat hij ooit gelezen werd. Dat gaf een
// leeg calculatieblad bij elke terugkeer naar deze pagina (ook een gewone
// F5), ook al stond de data nog prima in de autosave op het moment van
// wegnavigeren. Geeft { opties, actieveOptie } terug (via CB.optiesUitProject,
// dus ook met terugval op het oudere formaat vóór meerdere opties), of null.
CB.leesAutosaveOpties = () => {
  let bewaard;
  try { bewaard = sessionStorage.getItem(AUTOSAVE_SLEUTEL); } catch (e) { return null; }
  if (!bewaard) return null;
  try {
    const project = JSON.parse(bewaard);
    const opties = CB.optiesUitProject(project);
    return opties ? { opties, actieveOptie: project.actieveOptie || 0 } : null;
  } catch (e) { return null; /* corrupte autosave; gewoon leeg beginnen */ }
};
