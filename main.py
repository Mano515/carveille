#!/usr/bin/env python3
"""
Carveille -- Point d'entree CLI

Usage :
  python main.py init                            Initialise la base de donnees
  python main.py seed                            Charge les recherches de test
  python main.py run [--source mock|mobile.de] [--day 1]   Lance un run
  python main.py ui                              Lance l'interface web
"""

import argparse
import uuid


def cmd_init():
    from src.database import init_db
    init_db()


def cmd_seed():
    from src.database import init_db, insert_recherche
    init_db()

    recherches_test = [
        {
            "search_id": "search_bmw_auto",
            "nom_recherche": "BMW Serie 1 Auto",
            "statut": "active",
            "marque": "BMW",
            "modele": "Serie 1",
            "budget_max": 20000,
            "budget_strict": 0,
            "km_max": 100000,
            "annee_min": 2018,
            "boite": "auto",
            "carburant": "diesel",
            "vendeur_filtre": "indifferent",
            "options_recherchees": "camera,gps",
            "mobile_de_url": None,
            "poids_prix": 30,
            "poids_km": 25,
            "poids_annee": 20,
            "poids_boite": 10,
            "poids_carburant": 10,
            "poids_options": 5,
            "penalite_infos_manquantes": 10,
            "score_min_notification": 60,
            "max_annonces": 3,
        },
        {
            "search_id": "search_peugeot_308",
            "nom_recherche": "Peugeot 308 Essence",
            "statut": "active",
            "marque": "Peugeot",
            "modele": "308",
            "budget_max": 15000,
            "budget_strict": 1,
            "km_max": 80000,
            "annee_min": 2019,
            "boite": "indifferent",
            "carburant": "essence",
            "vendeur_filtre": "indifferent",
            "options_recherchees": "bluetooth",
            "mobile_de_url": None,
            "poids_prix": 30,
            "poids_km": 25,
            "poids_annee": 20,
            "poids_boite": 10,
            "poids_carburant": 10,
            "poids_options": 5,
            "penalite_infos_manquantes": 10,
            "score_min_notification": 60,
            "max_annonces": 3,
        },
    ]

    for r in recherches_test:
        insert_recherche(r)
        print(f"[OK] Recherche '{r['nom_recherche']}' inseree.")


def cmd_run(source: str, day: int):
    from src.runner import run
    run(source=source, day=day)


def cmd_ui():
    import http.server
    import threading
    import json
    import os
    from src.database import (
        init_db, get_recherches_actives, insert_recherche,
        get_derniers_resultats, marquer_interet
    )
    from src.runner import run as do_run

    init_db()

    UI_DIR = os.path.join(os.path.dirname(__file__), "ui")

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _send_json(self, data, status=200):
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path):
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send_file(os.path.join(UI_DIR, "index.html"))
            elif self.path == "/recherches":
                self._send_json(get_recherches_actives())
            elif self.path.startswith("/resultats/"):
                search_id = self.path.split("/resultats/")[1]
                self._send_json(get_derniers_resultats(search_id))
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            if self.path == "/recherches":
                data = {
                    "search_id": body.get("search_id") or str(uuid.uuid4()),
                    "nom_recherche": body.get("nom_recherche", ""),
                    "statut": "active",
                    "marque": body.get("marque", ""),
                    "modele": body.get("modele", ""),
                    "budget_max": body.get("budget_max"),
                    "budget_strict": int(bool(body.get("budget_strict", False))),
                    "km_max": body.get("km_max"),
                    "annee_min": body.get("annee_min"),
                    "boite": body.get("boite", "indifferent"),
                    "carburant": body.get("carburant", "indifferent"),
                    "vendeur_filtre": body.get("vendeur_filtre", "indifferent"),
                    "options_recherchees": body.get("options_recherchees", ""),
                    "mobile_de_url": body.get("mobile_de_url") or None,
                    "poids_prix": body.get("poids_prix", 30),
                    "poids_km": body.get("poids_km", 25),
                    "poids_annee": body.get("poids_annee", 20),
                    "poids_boite": body.get("poids_boite", 10),
                    "poids_carburant": body.get("poids_carburant", 10),
                    "poids_options": body.get("poids_options", 5),
                    "penalite_infos_manquantes": body.get("penalite_infos_manquantes", 10),
                    "score_min_notification": body.get("score_min_notification", 60),
                    "max_annonces": body.get("max_annonces", 3),
                }
                insert_recherche(data)
                self._send_json({"ok": True, "search_id": data["search_id"]})

            elif self.path == "/run":
                source = body.get("source", "mock")
                day = int(body.get("day", 1))
                t = threading.Thread(target=do_run, kwargs={"source": source, "day": day})
                t.start()
                self._send_json({"ok": True, "message": f"Run lance (source={source}, day={day})"})

            elif self.path == "/interet":
                seen_id = body.get("seen_id")
                interet = body.get("interet")
                if seen_id and interet in ("oui", "non", "neutre"):
                    marquer_interet(seen_id, interet if interet != "neutre" else None)
                    self._send_json({"ok": True})
                else:
                    self._send_json({"ok": False, "error": "seen_id ou interet invalide"}, 400)

            else:
                self.send_response(404)
                self.end_headers()

    port = 8765
    server = http.server.HTTPServer(("localhost", port), Handler)
    print(f"[WEB] Interface disponible sur http://localhost:{port}")
    print("   (Ctrl+C pour arreter)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServeur arrete.")


def main():
    parser = argparse.ArgumentParser(description="Carveille CLI")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="Initialise la base de donnees")
    sub.add_parser("seed", help="Charge les recherches de test")

    run_p = sub.add_parser("run", help="Lance un run")
    run_p.add_argument("--source", default="mock", help="mock ou mobile.de")
    run_p.add_argument("--day", type=int, default=1, help="Jour mock (1 ou 2)")

    sub.add_parser("ui", help="Lance l'interface web")

    args = parser.parse_args()

    if args.cmd == "init":
        cmd_init()
    elif args.cmd == "seed":
        cmd_seed()
    elif args.cmd == "run":
        cmd_run(args.source, args.day)
    elif args.cmd == "ui":
        cmd_ui()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
