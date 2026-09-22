"""De lokale app: een klein webserverje dat het formulier bedient.

De browser rekent niets zelf uit. Bij elke wijziging stuurt hij de antwoorden
hierheen en krijgt de samengestelde brief terug, opgebouwd door dezelfde
samenstellen.py die ook het Word-bestand maakt. Zo kan wat op het scherm staat
niet uit de pas lopen met wat er uitrolt.

    python3 -m brieventool.server
    python3 -m brieventool.server --poort 8000 --geen-browser

Draait alleen op de eigen machine (127.0.0.1) en is bewust niet van buitenaf
bereikbaar: er staan klantgegevens in.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import tempfile
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .bibliotheek import BibliotheekFout, laad
from .controle import melding, ontbrekende_gegevens
from .bijlage import SOORTEN, BijlageFout, tekst_uit_bestand
from .briefpapier import BriefpapierFout, beeld, lees
from .samenstellen import SamenstelFout, stel_samen
from .sjabloon import SjabloonFout, schrijf_docx

WORTEL = Path(__file__).resolve().parent.parent
SCHERM = WORTEL / "ontwerp" / "prototype.html"
SJABLOON = WORTEL / "sjablonen" / "brief.docx"
MAX_INHOUD = 20 * 1024 * 1024      # ruim genoeg voor een datablad


class Bediening(BaseHTTPRequestHandler):
    server_version = "Brieventool"

    # --- verzoeken ---------------------------------------------------------

    def do_GET(self) -> None:
        pad = urlparse(self.path).path
        if pad in ("/", "/index.html"):
            self._scherm()
        elif pad == "/keuzes":
            self._antwoord(200, self._keuzes())
        elif pad == "/app":
            # Waaraan het scherm herkent dat de motor erachter zit. Niet aan het
            # protocol: het ontwerpbestand wordt ook wel over https bediend, en
            # dan is er geen Python.
            self._antwoord(200, {"app": True, "blokken": len(self.server.bibliotheek.blokken)})
        elif pad == "/briefpapier":
            self._briefpapier()
        elif pad.startswith("/beeld/"):
            self._beeld(pad[len("/beeld/"):])
        elif pad == "/favicon.ico":
            # De browser vraagt hier altijd om; een leeg antwoord is genoeg.
            self.send_response(204)
            self.end_headers()
        else:
            self._antwoord(404, {"fout": "onbekend adres"})

    def do_POST(self) -> None:
        pad = urlparse(self.path).path
        try:
            gegevens = self._gelezen_json()
        except ValueError as fout:
            return self._antwoord(400, {"fout": str(fout)})

        if pad == "/brief":
            self._brief(gegevens)
        elif pad == "/docx":
            self._docx(gegevens)
        elif pad == "/datablad":
            self._datablad(gegevens)
        else:
            self._antwoord(404, {"fout": "onbekend adres"})

    # --- werk --------------------------------------------------------------

    def _brief(self, offerte: dict) -> None:
        """De samengestelde brief, als alinea's per sectie."""
        try:
            brief = stel_samen(offerte, self.server.bibliotheek)
        except (SamenstelFout, BibliotheekFout) as fout:
            return self._antwoord(200, {"fout": str(fout)})

        self._antwoord(200, {
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
        # Een gat in een verstuurde brief valt niemand meer op; hier nog wel.
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
        """Leest een aangeleverd datablad uit; de browser stuurt de inhoud mee."""
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
        """Wat het formulier moet tonen: de keuzeblokken en de ondertekenaars."""
        bib = self.server.bibliotheek
        return {
            "secties": {sectie: [{"id": i, "label": l} for i, l in bib.keuzes(sectie)]
                        for sectie in bib.secties},
            "ondertekenaars": [{"id": sleutel, "naam": persoon.get("naam", sleutel)}
                               for sleutel, persoon in bib.ondertekenaars.items()],
            "bestandssoorten": list(SOORTEN),
        }

    # --- plumbing ----------------------------------------------------------

    def _briefpapier(self) -> None:
        """Het echte briefpapier, zodat de voorvertoning erop lijkt."""
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

    def _scherm(self) -> None:
        try:
            inhoud = SCHERM.read_bytes()
        except OSError:
            return self._antwoord(500, {"fout": f"{SCHERM} ontbreekt"})
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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


def start(poort: int = 8391, open_browser: bool = True, bibliotheek_map: Path | None = None) -> int:
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

    adres = f"http://127.0.0.1:{poort}/"
    print(f"Brieventool draait op {adres}")
    print(f"  {len(bibliotheek.blokken)} tekstblokken · stoppen met Ctrl-C")
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(adres)).start()

    try:
        server.serve_forever()
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
    return start(keuzes.poort, not keuzes.geen_browser, keuzes.bibliotheek)


if __name__ == "__main__":
    raise SystemExit(main())
