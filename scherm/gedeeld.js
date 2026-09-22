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
// Het laadscherm-filmpje zelf speelt in scherm/splash.html (altijd het
// eerste dat opent, zie server.py:start); deze overlay op index.html is een
// veel kortere, spinner-only terugval voor de eigen data-ophaal-stap van de
// tool (en voor wie rechtstreeks op "/" uitkomt, bijv. door te herladen).
// Blijft zichtbaar tot beide stappen klaar zijn (CB.calc.klaar/CB.brief.klaar)
// — zie de aanroep van CB.laadscherm.verberg() onderaan index.html.
// MINIMALE_DUUR_MS is klein: alleen om een flits-en-weg-effect te voorkomen,
// niet om iets te laten zien (dat doet splash.html al).
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

/* -------------------------- stappen wisselen -------------------------- */

CB.naarStap = (naam) => {
  for (const stap of document.querySelectorAll('.stap')) {
    stap.classList.toggle('actief', stap.dataset.stap === naam);
  }
  for (const knop of document.querySelectorAll('.stappen button')) {
    knop.classList.toggle('actief', knop.dataset.stap === naam);
  }
  window.scrollTo(0, 0);
};

CB.bindStappen = () => {
  for (const knop of document.querySelectorAll('.stappen button')) {
    knop.addEventListener('click', () => {
      if (!knop.disabled) CB.naarStap(knop.dataset.stap);
    });
  }
};

/* --------------------- gecombineerd projectbestand --------------------- */

const PROJECT_MERK = 'calcu-brief-project';

CB.huidigProject = () => ({
  merk: PROJECT_MERK,
  versie: 1,
  calculatie: CB.calc.staat,
  brief: CB.brief.antwoorden,
});

CB.heeftInhoud = () => CB.calc.heeftInhoud() || CB.brief.heeftInhoud();

CB.projectBestandsnaam = () => {
  const meta = CB.calc.staat.meta || {};
  const delen = [meta.klantnaam, meta.qnummer].filter(Boolean);
  const kaal = delen.join('-') || 'calculatie-en-brief';
  const veilig = kaal.toLowerCase().replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '');
  return (veilig || 'calculatie-en-brief') + '.json';
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
        return CB.toast('Dit is geen calculatie-en-brief-projectbestand.');
      }
      CB.calc.vulStaat(project.calculatie || CB.calc.nieuweStaat());
      CB.brief.vulAntwoorden(project.brief || {});
      CB.toast('Project geopend.');
    };
    lezer.readAsText(bestand);
  });

  document.getElementById('btnNieuw').addEventListener('click', () => {
    if (CB.heeftInhoud() && !confirm('Alles wissen? Niet-opgeslagen wijzigingen gaan dan verloren.')) return;
    CB.calc.vulStaat(CB.calc.nieuweStaat());
    CB.brief.vulAntwoorden({});
    CB.naarStap('calculatie');
    CB.toast('Nieuw project gestart.');
  });
};

/* Vangnet, geen archief: de browser onthoudt de laatste stand zodat een
   dichtgeklapt tabblad geen werk kost. Net als bij de losse brieventool. */
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
    if (project.brief) CB.brief.vulAntwoorden(project.brief);
  } catch (e) { /* corrupte autosave; gewoon leeg beginnen */ }
};
