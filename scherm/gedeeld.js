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

CB.postJSON = async (pad, lichaam) => {
  const respons = await fetch(pad, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(lichaam || {}),
  });
  return respons.json();
};

CB.getJSON = async pad => (await fetch(pad)).json();

CB.debounce = (fn, ms) => {
  let timer = null;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
};

/* ------------------------------- laadscherm ------------------------------ */
// Het laadscherm-filmpje zelf speelt native (tkinter, zie
// server.py:_toon_native_laadscherm), vóór de browser al open is; deze
// overlay op index.html is een veel kortere, spinner-only terugval voor de
// eigen data-ophaal-stap van de calculatiestap (materiaalcatalogus/YIMM/
// Panasonic/Daikin, de eerste /bereken-ronde) -- voor wie rechtstreeks op
// "/" uitkomt (bijv. door te herladen) is er dus nog altijd iets te zien.
// Blijft zichtbaar tot CB.calc.klaar is opgelost -- zie de aanroep van
// CB.laadscherm.verberg() onderaan index.html. MINIMALE_DUUR_MS is klein:
// alleen om een flits-en-weg-effect te voorkomen, niet om iets te laten zien
// (dat doet het native laadscherm al).
CB.laadscherm = {
  _vanaf: Date.now(),
  MINIMALE_DUUR_MS: 300,
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
};

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

CB.huidigProject = () => ({
  merk: PROJECT_MERK,
  versie: 1,
  calculatie: CB.calc.staat,
});

CB.heeftInhoud = () => CB.calc.heeftInhoud();

// scherm/brief.html doet dit zelf nog een keer (veiligeNaamdeel daar): het is
// een losstaande pagina zonder gedeelde scripts met deze kant van de tool.
CB.veiligeBestandsnaamdeel = tekst => String(tekst || '').trim().replace(/[\\/:*?"<>|]+/g, '-');

CB.projectBestandsnaam = () => {
  const meta = CB.calc.staat.meta || {};
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
      CB.calc.vulStaat(project.calculatie || CB.calc.nieuweStaat());
      CB.toast('Project geopend.');
    };
    lezer.readAsText(bestand);
  });

  document.getElementById('btnNieuw').addEventListener('click', () => {
    if (CB.heeftInhoud() && !confirm('Alles wissen? Niet-opgeslagen wijzigingen gaan dan verloren.')) return;
    CB.calc.vulStaat(CB.calc.nieuweStaat());
    CB.toast('Nieuw project gestart.');
  });
};

/* Vangnet, geen archief: de browser onthoudt de laatste stand zodat een
   dichtgeklapt tabblad geen werk kost. Net als bij de losse brieventool.
   Dezelfde sleutel wordt ook door scherm/brief.html gelezen (nooit
   weggeschreven) om de calculatiegegevens over te nemen -- zie
   CALCULATIE_CONCEPT_SLEUTEL daar. */
const AUTOSAVE_SLEUTEL = 'calcubrief.concept';

CB.autosave = () => {
  try { localStorage.setItem(AUTOSAVE_SLEUTEL, JSON.stringify(CB.huidigProject())); }
  catch (e) { /* localStorage kan vol/uitgeschakeld zijn; geen ramp */ }
};

CB.laadAutosave = () => {
  let bewaard;
  try { bewaard = localStorage.getItem(AUTOSAVE_SLEUTEL); } catch (e) { return; }
  if (!bewaard) return;
  try {
    const project = JSON.parse(bewaard);
    if (project.calculatie) CB.calc.vulStaat(project.calculatie);
  } catch (e) { /* corrupte autosave; gewoon leeg beginnen */ }
};
