"""De lokale app: calculatie en briefsamenstelling achter één server.

Precies zoals brieventool/server.py dat al deed voor de brief: de browser
rekent zelf niets uit, stuurt bij elke wijziging de invoer hierheen en krijgt
het resultaat terug van dezelfde code die ook de brief/het Word-bestand
maakt. Dat geldt nu ook voor de calculatie: `calculatie/rekenkern.py` is de
enige plek waar de marge wordt uitgerekend, dus het scherm en de brief kunnen
nooit een verschillend bedrag laten zien.

    python3 server.py
    python3 server.py --poort 8000 --geen-browser

Draait alleen op de eigen machine (127.0.0.1) en is bewust niet van buitenaf
bereikbaar: er staan klant- en prijsgegevens in.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import socket
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from brieventool.bibliotheek import BibliotheekFout, laad
from brieventool.bijlage import SOORTEN, BijlageFout, tekst_uit_bestand
from brieventool.briefpapier import BriefpapierFout, beeld, lees
from brieventool.controle import melding, ontbrekende_gegevens
from brieventool.samenstellen import SamenstelFout, stel_samen
from brieventool.sjabloon import SjabloonFout, schrijf_docx
from calculatie import rekenkern as rk
from overdracht import zet_over

# Een --windowed/--noconsole build (zowel de Windows-.exe als de Mac-.app,
# zie build-app.yml) heeft geen console: sys.stdout/sys.stderr zijn dan None
# in plaats van een writable stream. Een doodgewone print() (er staan er een
# paar verderop, vóór het laadscherm/de browser worden geopend) crasht die
# build dan meteen met een AttributeError -- onzichtbaar, want er is geen
# console om de foutmelding te tonen: de app "doet niets", ook het laadscherm
# niet, precies zoals gemeld. pythonw.exe (start-app.pyw) heeft hetzelfde
# probleem, ook zonder frozen build. Vervang None daarom door een stille sink
# vóórdat er ergens geprint wordt.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

if getattr(sys, "frozen", False):
    # Gebouwd met PyInstaller (--onefile/--windowed): de meegepakte data
    # (analyse/, config/, sjablonen/, data/, scherm/) staat dan niet naast dit
    # bestand maar in de tijdelijke uitpakmap die PyInstaller bijhoudt.
    WORTEL = Path(sys._MEIPASS)  # type: ignore[attr-defined]
else:
    WORTEL = Path(__file__).resolve().parent
SCHERM_MAP = WORTEL / "scherm"
DATA_MAP = WORTEL / "data"
SJABLOON = WORTEL / "sjablonen" / "brief.docx"
MAX_INHOUD = 20 * 1024 * 1024  # ruim genoeg voor een datablad

# Statisch te serveren mappen: alleen bestanden die hieronder hangen, nooit
# daarbuiten (zie _statisch_pad).
STATISCHE_MAPPEN = {"scherm": SCHERM_MAP, "data": DATA_MAP}


class Bediening(BaseHTTPRequestHandler):
    server_version = "CalcuBrief"

    # --- verzoeken -----------------------------------------------------

    def do_GET(self) -> None:
        pad = urlparse(self.path).path
        if pad in ("/", "/index.html"):
            return self._bestand(SCHERM_MAP / "index.html", "text/html; charset=utf-8")
        if pad == "/brief.html":
            # Op het root-niveau geserveerd (niet onder /scherm/) zodat de
            # relatieve fetch("app")/fetch("brief")/fetch("docx")-aanroepen in
            # dat bestand (ongewijzigd overgenomen uit de losstaande
            # brieventool, zie CLAUDE.md) gewoon naar /app, /brief, /docx
            # resolven zonder dat de URL's aangepast hoefden te worden.
            return self._bestand(SCHERM_MAP / "brief.html", "text/html; charset=utf-8")
        if pad == "/app":
            # Zelfde signaal als brieventool: waaraan het scherm herkent dat
            # de motor (en dus ook de rekenkern) erachter zit.
            return self._antwoord(200, {"app": True, "blokken": len(self.server.bibliotheek.blokken)})
        if pad == "/keuzes":
            return self._antwoord(200, self._keuzes())
        if pad == "/briefpapier":
            return self._briefpapier()
        if pad.startswith("/beeld/"):
            return self._beeld(pad[len("/beeld/"):])
        if pad == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return None
        statisch = self._statisch_pad(pad)
        if statisch is not None:
            return self._bestand(statisch)
        return self._antwoord(404, {"fout": "onbekend adres"})

    def do_POST(self) -> None:
        pad = urlparse(self.path).path
        try:
            gegevens = self._gelezen_json()
        except ValueError as fout:
            return self._antwoord(400, {"fout": str(fout)})

        if pad == "/bereken":
            return self._bereken(gegevens)
        if pad == "/overdracht":
            return self._overdracht(gegevens)
        if pad == "/brief":
            return self._brief(gegevens)
        if pad == "/docx":
            return self._docx(gegevens)
        if pad == "/datablad":
            return self._datablad(gegevens)
        return self._antwoord(404, {"fout": "onbekend adres"})

    # --- calculatie ------------------------------------------------------

    def _bereken(self, staat: dict) -> None:
        """Rekent de calculatie-state door: afgeleide materiaalregels,
        uren per rol en de volledige marge-opbouw. Zie calculatie/rekenkern.py
        -- dit is de enige plek waar dit wordt uitgerekend."""
        try:
            resultaat = rk.bereken(staat, self.server.calc_gegevens)
        except (KeyError, TypeError, ValueError) as fout:
            return self._antwoord(400, {"fout": f"kan de calculatie niet doorrekenen: {fout}"})
        return self._antwoord(200, resultaat)

    def _overdracht(self, gegevens: dict) -> None:
        """Zet een calculatie-state om in een voorinvulling voor de brief.

        Nooit een afgeronde brief: het antwoord is een (deels ingevuld)
        offerte-formulier plus de lijst velden die overgenomen/afgeleid zijn,
        zodat het scherm kan laten zien wat gecontroleerd moet worden."""
        staat = gegevens.get("calculatie") or {}
        try:
            berekening = rk.bereken(staat, self.server.calc_gegevens)
            offerte, overdracht = zet_over(staat, berekening, gegevens.get("klanttype"))
        except (KeyError, TypeError, ValueError) as fout:
            return self._antwoord(400, {"fout": f"kan de overdracht niet maken: {fout}"})
        return self._antwoord(200, {
            "offerte": offerte,
            "overdracht": [
                {"pad": v.pad, "status": v.status, "reden": v.reden, "opties": v.opties}
                for v in overdracht
            ],
        })

    # --- brief (ongewijzigd overgenomen uit brieventool/server.py) -------

    def _brief(self, offerte: dict) -> None:
        try:
            brief = stel_samen(offerte, self.server.bibliotheek)
        except (SamenstelFout, BibliotheekFout) as fout:
            return self._antwoord(200, {"fout": str(fout)})

        return self._antwoord(200, {
            "secties": [
                {"naam": naam, "alineas": [
                    {"tekst": a.tekst, "nadruk": a.nadruk, "stijl": a.stijl,
                     "blok": a.blok_id, "letterlijk": a.letterlijk,
                     "uitgelijnd": a.uitgelijnd, "cursief": a.cursief,
                     "los": a.los}
                    for a in alineas]}
                for naam, alineas in brief.secties.items() if alineas
            ],
            "blokken": brief.gebruikte_blokken,
            "waarschuwingen": brief.waarschuwingen,
            "ontbreekt": ontbrekende_gegevens(offerte),
            "kenmerken": {"projectnummer": offerte.get("projectnummer") or "",
                          "referentie": brief.context.get("referentie") or ""},
        })

    def _docx(self, offerte: dict) -> None:
        ontbreekt = ontbrekende_gegevens(offerte)
        if ontbreekt:
            return self._antwoord(200, {"fout": melding(ontbreekt), "ontbreekt": ontbreekt})
        try:
            brief = stel_samen(offerte, self.server.bibliotheek)
            with tempfile.TemporaryDirectory() as tijdelijk:
                pad = schrijf_docx(brief, SJABLOON, Path(tijdelijk) / "brief.docx")
                inhoud = pad.read_bytes()
        except (SamenstelFout, BibliotheekFout, SjabloonFout) as fout:
            return self._antwoord(200, {"fout": str(fout)})

        naam = _bestandsnaam(offerte)
        self.send_response(200)
        self.send_header("Content-Type",
                         "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.send_header("Content-Disposition", f'attachment; filename="{naam}"')
        self.send_header("Content-Length", str(len(inhoud)))
        self.end_headers()
        self.wfile.write(inhoud)

    def _datablad(self, gegevens: dict) -> None:
        import base64
        naam = str(gegevens.get("naam") or "datablad")
        try:
            rauw = base64.b64decode(gegevens.get("inhoud") or "", validate=True)
        except Exception:
            return self._antwoord(200, {"fout": "het bestand kwam beschadigd aan"})

        with tempfile.TemporaryDirectory() as tijdelijk:
            pad = Path(tijdelijk) / Path(naam).name
            pad.write_bytes(rauw)
            try:
                return self._antwoord(200, {"tekst": tekst_uit_bestand(pad)})
            except BijlageFout as fout:
                return self._antwoord(200, {"fout": str(fout)})

    def _keuzes(self) -> dict:
        bib = self.server.bibliotheek
        return {
            "secties": {sectie: [{"id": i, "label": l} for i, l in bib.keuzes(sectie)]
                        for sectie in bib.secties},
            "ondertekenaars": [{"id": sleutel, "naam": persoon.get("naam", sleutel)}
                               for sleutel, persoon in bib.ondertekenaars.items()],
            "bestandssoorten": list(SOORTEN),
        }

    # --- plumbing --------------------------------------------------------

    def _briefpapier(self) -> None:
        try:
            self._antwoord(200, lees(SJABLOON))
        except BriefpapierFout as fout:
            self._antwoord(200, {"fout": str(fout)})

    def _beeld(self, naam: str) -> None:
        try:
            inhoud, soort = beeld(SJABLOON, naam)
        except BriefpapierFout as fout:
            return self._antwoord(404, {"fout": str(fout)})
        self.send_response(200)
        self.send_header("Content-Type", soort)
        self.send_header("Content-Length", str(len(inhoud)))
        self.send_header("Cache-Control", "max-age=3600")
        self.end_headers()
        self.wfile.write(inhoud)

    def _statisch_pad(self, verzoekpad: str) -> Path | None:
        """Vertaalt "/scherm/app.js" of "/data/foo.json" naar een echt
        bestand, zonder buiten die mappen te kunnen komen."""
        delen = [d for d in verzoekpad.split("/") if d not in ("", ".", "..")]
        if len(delen) < 2 or delen[0] not in STATISCHE_MAPPEN:
            return None
        kandidaat = STATISCHE_MAPPEN[delen[0]].joinpath(*delen[1:]).resolve()
        map_wortel = STATISCHE_MAPPEN[delen[0]].resolve()
        if map_wortel not in kandidaat.parents and kandidaat != map_wortel:
            return None
        if not kandidaat.is_file():
            return None
        return kandidaat

    def _bestand(self, pad: Path, content_type: str | None = None) -> None:
        """Serveert een statisch bestand, met Range-ondersteuning (nodig voor
        het laadscherm-filmpje: zonder 206 Partial Content laat lang niet elke
        browser <video> soepel spelen/spoelen)."""
        try:
            grootte = pad.stat().st_size
        except OSError:
            return self._antwoord(404, {"fout": f"{pad.name} ontbreekt"})
        soort = content_type or mimetypes.guess_type(pad.name)[0] or "application/octet-stream"

        bereik = self.headers.get("Range")
        treffer = re.match(r"bytes=(\d*)-(\d*)", bereik) if bereik else None
        if treffer and (treffer.group(1) or treffer.group(2)):
            start = int(treffer.group(1)) if treffer.group(1) else 0
            eind = int(treffer.group(2)) if treffer.group(2) else grootte - 1
            eind = min(eind, grootte - 1)
            with pad.open("rb") as f:
                f.seek(start)
                inhoud = f.read(eind - start + 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{eind}/{grootte}")
        else:
            inhoud = pad.read_bytes()
            self.send_response(200)
        self.send_header("Content-Type", soort)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(inhoud)))
        self.end_headers()
        self.wfile.write(inhoud)

    def _gelezen_json(self) -> dict:
        lengte = int(self.headers.get("Content-Length") or 0)
        if lengte > MAX_INHOUD:
            raise ValueError("het verzoek is te groot")
        try:
            return json.loads(self.rfile.read(lengte) or b"{}")
        except json.JSONDecodeError as fout:
            raise ValueError(f"onleesbaar verzoek: {fout}") from fout

    def _antwoord(self, code: int, gegevens: dict) -> None:
        inhoud = json.dumps(gegevens, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(inhoud)))
        self.end_headers()
        self.wfile.write(inhoud)

    def log_message(self, indeling, *argumenten):
        """Standaard logt http.server elk verzoek; dat is hier alleen ruis."""


def _bestandsnaam(offerte: dict) -> str:
    delen = [str(offerte.get("achternaam") or "offerte").strip(),
             str(offerte.get("plaats") or "").strip(),
             str(offerte.get("sa_nummer") or "").strip()]
    kaal = "-".join(d for d in delen if d)
    veilig = "".join(t if (t.isalnum() or t in "-_") else "-" for t in kaal)
    return (veilig.strip("-").lower() or "offerte") + ".docx"


def _vrije_poort(voorkeur: int) -> int:
    for poort in range(voorkeur, voorkeur + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", poort)) != 0:
                return poort
    raise SystemExit(f"geen vrije poort gevonden vanaf {voorkeur}")


# Aantal beeldjes per seconde waarmee scherm/laadscherm.gif is gemaakt (zie
# .github/workflows/build-app.yml) -- moet gelijk blijven aan de "fps"-waarde
# in dat ffmpeg-commando, anders loopt de afspeelsnelheid hier uit de pas.
LAADSCHERM_FPS = 12


def _native_laadscherm_pad() -> Path | None:
    """scherm/laadscherm.gif bestaat alleen in een gebouwde .exe/.app (zie de
    ffmpeg-stap in de build-workflow) -- draai je vanuit de broncode, dan is
    er geen gif en valt start() terug op gewoon de browser openen."""
    gif = WORTEL / "scherm" / "laadscherm.gif"
    return gif if gif.is_file() else None


def _toon_native_laadscherm(gif_pad: Path) -> None:
    """Speelt het laadscherm-filmpje (als gif, want tkinter kan geen video)
    in een eigen, kaderloos venster op het bureaublad -- dit dekt precies het
    stuk tussen dubbelklikken op de .exe en het openen van de browser, dat
    een browserpagina nooit kan laten zien (er draait dan nog geen browser,
    dus ook geen JavaScript). Blokkeert tot het filmpje één keer is
    afgespeeld; roep dit dus aan vóórdat de browser wordt geopend, niet
    ernaast. Elke fout (geen tkinter, geen beeldscherm, kapotte gif) komt
    gewoon omhoog naar de aanroeper, die dan gewoon de browser opent."""
    import tkinter as tk

    root = tk.Tk()
    root.title("Calcu-Brief-tool")
    root.overrideredirect(True)  # geen titelbalk/randen -- een laadscherm, geen venster om te bedienen
    root.attributes("-topmost", True)
    root.configure(bg="#414B4D")

    frames: list[tk.PhotoImage] = []
    i = 0
    while True:
        try:
            frames.append(tk.PhotoImage(file=str(gif_pad), format=f"gif -index {i}"))
        except tk.TclError:
            break
        i += 1
    if not frames:
        root.destroy()
        raise ValueError(f"{gif_pad} bevat geen leesbare beeldjes")

    breedte, hoogte = frames[0].width(), frames[0].height()
    scherm_b, scherm_h = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{breedte}x{hoogte}+{(scherm_b - breedte) // 2}+{(scherm_h - hoogte) // 2}")

    label = tk.Label(root, image=frames[0], bd=0, bg="#414B4D")
    label.pack()

    frame_ms = round(1000 / LAADSCHERM_FPS)

    def animeer(idx: int = 0) -> None:
        label.configure(image=frames[idx])
        root.after(frame_ms, animeer, (idx + 1) % len(frames))

    animeer()
    # Eén volledige lus, dan verder -- niet oneindig blijven doorspelen.
    root.after(len(frames) * frame_ms, root.destroy)
    root.mainloop()


def start(poort: int = 8391, open_browser: bool = True, bibliotheek_map: Path | None = None) -> int:
    # BRIEVENTOOL_BIBLIOTHEEK (bijv. een gedeelde OneDrive-map) blijft ook in
    # een gebouwde .exe/.app werken -- alleen als die niet gezet is, en er ook
    # geen --bibliotheek is meegegeven, valt een gebouwde app terug op zijn
    # eigen meegepakte teksten.yaml (WORTEL) in plaats van naast een niet-
    # bestaand .py-bestand te zoeken (laad()'s eigen standaardmap()).
    if bibliotheek_map is None and getattr(sys, "frozen", False) and not os.environ.get("BRIEVENTOOL_BIBLIOTHEEK"):
        bibliotheek_map = WORTEL
    try:
        bibliotheek = laad(bibliotheek_map)
    except BibliotheekFout as fout:
        print(f"Fout: {fout}", file=sys.stderr)
        return 1
    if not SJABLOON.is_file():
        print(f"Let op: {SJABLOON} ontbreekt. Maak het met: python3 tools/maak_sjabloon.py",
              file=sys.stderr)

    poort = _vrije_poort(poort)
    server = ThreadingHTTPServer(("127.0.0.1", poort), Bediening)
    server.bibliotheek = bibliotheek
    server.calc_gegevens = rk.laad_gegevens(DATA_MAP)

    adres = f"http://127.0.0.1:{poort}/"
    print(f"Calcu-Brief-tool draait op {adres}")
    print(f"  {len(bibliotheek.blokken)} tekstblokken · stoppen met Ctrl-C")

    # serve_forever() draait op een eigen thread, zodat de hoofdthread vrij is
    # om (indien beschikbaar) het native laadscherm te tonen -- dat MOET op de
    # hoofdthread draaien (tkinter-eis, vooral hard op macOS). Bibliotheek en
    # calculatiegegevens staan hierboven al klaar, dus de server kan gewoon
    # meteen gaan luisteren; er hoeft nergens op "gereed" gewacht te worden.
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    if open_browser:
        gif_pad = _native_laadscherm_pad()
        if gif_pad is not None:
            try:
                _toon_native_laadscherm(gif_pad)
            except Exception as fout:
                print(f"Laadscherm kon niet getoond worden ({fout}); open direct de browser.",
                      file=sys.stderr)
            webbrowser.open(adres)
        else:
            threading.Timer(0.4, lambda: webbrowser.open(adres)).start()

    try:
        server_thread.join()
    except KeyboardInterrupt:
        print("\nGestopt.")
    finally:
        server.server_close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--poort", type=int, default=8391)
    ap.add_argument("--geen-browser", action="store_true",
                    help="niet automatisch een browser openen")
    ap.add_argument("--bibliotheek", type=Path,
                    help="map met teksten.yaml (standaard: BRIEVENTOOL_BIBLIOTHEEK of de projectmap)")
    keuzes = ap.parse_args()
    try:
        return start(keuzes.poort, not keuzes.geen_browser, keuzes.bibliotheek)
    except Exception as fout:
        # Een --windowed/--noconsole build (zie de sys.stdout/sys.stderr-fix
        # hierboven) heeft geen console om een traceback op te tonen: zonder
        # dit vangnet lijkt de app dan simpelweg "niets te doen" bij een
        # onverwachte opstartfout, precies zoals eerder gemeld. tkinter is
        # toch al een afhankelijkheid (zie _toon_native_laadscherm).
        if getattr(sys, "frozen", False):
            try:
                import tkinter
                from tkinter import messagebox
                venster = tkinter.Tk()
                venster.withdraw()
                messagebox.showerror("Calcu-Brief-tool kon niet starten", str(fout))
            except Exception:
                pass  # geen tkinter/beeldscherm beschikbaar; niets meer aan te doen
        raise


if __name__ == "__main__":
    raise SystemExit(main())
