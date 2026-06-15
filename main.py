#!/usr/bin/env python3
"""
Carveille -- Point d'entree
Usage normal : double-clic sur "Lancer Carveille.bat"
Usage CLI    : python main.py [init | seed | run | ui]
"""

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime

# ── Chemins ─────────────────────────────────────────────────────────────────────
_BASE = os.path.dirname(__file__)
_ENV_PATH = os.path.join(_BASE, ".env")
_SCHEDULE_PATH = os.path.join(_BASE, "db", "schedule.json")


# ── Lecture / ecriture de la configuration (.env) ───────────────────────────────
def _load_config() -> dict:
    cfg = {
        "CANAL_NOTIFICATION": "console",
        "TELEGRAM_BOT_TOKEN": "",
        "TELEGRAM_CHAT_ID": "",
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "",
        "SMTP_PASSWORD": "",
        "SMTP_DEST": "",
    }
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    return cfg


def _save_config(data: dict):
    """Ecrit les cles dans .env et propage immediatement dans os.environ."""
    lines = []
    existing_keys = set()
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        for line in lines:
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                existing_keys.add(s.split("=", 1)[0].strip())

    new_lines = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            new_lines.append(f"{k}={data[k]}\n" if k in data else line)
        else:
            new_lines.append(line)

    for k, v in data.items():
        if k not in existing_keys:
            new_lines.append(f"{k}={v}\n")

    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    for k, v in data.items():
        os.environ[k] = v


# ── Gestion des dossiers clients locaux ─────────────────────────────────────────

def _dossier_clients_root() -> pathlib.Path:
    cfg = _load_config()
    # Par défaut : dossier "Clients" à côté de main.py, quel que soit l'endroit où Carveille est installé
    default = str(pathlib.Path(__file__).parent / "Clients")
    path = cfg.get("DOSSIER_CLIENTS") or default
    return pathlib.Path(path)


def _nom_dossier_safe(nom: str) -> str:
    """Retire les caractères interdits dans un nom de dossier Windows/Mac/Linux."""
    return "".join(c for c in nom if c not in r'\/:*?"<>|').strip()


def _dossier_client(nom_client: str) -> pathlib.Path:
    return _dossier_clients_root() / _nom_dossier_safe(nom_client)


def _creer_dossier_client(nom_client: str):
    base = _dossier_client(nom_client)
    (base / "voitures").mkdir(parents=True, exist_ok=True)
    (base / "documents").mkdir(parents=True, exist_ok=True)
    return base


def _ouvrir_dossier(path: pathlib.Path):
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])


# ── Planificateur de runs automatiques ──────────────────────────────────────────
def _load_schedule() -> dict:
    defaults = {
        "actif": False,
        "horaires": ["09:00"],
        "jours": ["lun", "mar", "mer", "jeu", "ven", "sam", "dim"],
        "nouvelles_annonces": True,
        "baisses_prix": True,
        "resume_hebdo": False,   # résumé hebdomadaire le dimanche
        "derniers_runs": [],     # liste de "YYYY-MM-DD_HH:MM" ou "resume_YYYY-WNN"
    }
    if os.path.exists(_SCHEDULE_PATH):
        try:
            with open(_SCHEDULE_PATH, encoding="utf-8") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    return defaults


def _save_schedule(data: dict):
    os.makedirs(os.path.dirname(_SCHEDULE_PATH), exist_ok=True)
    with open(_SCHEDULE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Etat du run courant (partagé entre les threads) ─────────────────────────────
_run_lock = threading.Lock()
_run_status = {
    "en_cours": False,
    "dernier_run": None,   # ISO datetime du dernier run termine
}


def _do_run_with_status(source: str, day: int = 1, notify_nouvelles: bool = True, notify_baisses: bool = True):
    """Lance un run et met a jour _run_status."""
    from src.runner import run
    with _run_lock:
        _run_status["en_cours"] = True
    try:
        run(source=source, day=day, notify_nouvelles=notify_nouvelles, notify_baisses=notify_baisses)
    finally:
        with _run_lock:
            _run_status["en_cours"] = False
        _run_status["dernier_run"] = datetime.now().isoformat()


_JOURS_SEMAINE = {"lun": 0, "mar": 1, "mer": 2, "jeu": 3, "ven": 4, "sam": 5, "dim": 6}


def _envoyer_resume_hebdo():
    """Envoie un email de résumé hebdomadaire avec les stats par client."""
    from src.database import get_resume_hebdo
    from src.notifier import envoyer_email
    clients = get_resume_hebdo()
    if not clients:
        return
    lignes = ["Bonjour,\n", "Voici le résumé de la semaine écoulée :\n"]
    for c in clients:
        lignes.append(f"• {c['nom']}")
        if c.get("nb_annonces_semaine"):
            lignes.append(f"  → {c['nb_annonces_semaine']} nouvelle(s) annonce(s) cette semaine")
        else:
            lignes.append("  → Aucune nouvelle annonce cette semaine")
        if c.get("nb_retenues_total"):
            lignes.append(f"  → {c['nb_retenues_total']} annonce(s) marquée(s) comme intéressante(s) au total")
        lignes.append("")
    lignes.append("Bonne semaine,\nCarveille")
    envoyer_email("\n".join(lignes), sujet="Carveille — Résumé de la semaine")


def _scheduler_thread():
    """Tourne en arriere-plan et declenche les runs automatiques selon le planning."""
    while True:
        time.sleep(60)
        try:
            sched = _load_schedule()
            if not sched.get("actif"):
                continue
            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            derniers_runs = sched.get("derniers_runs", [])
            changed = False

            # Résumé hebdomadaire le dimanche
            if sched.get("resume_hebdo") and now.weekday() == 6:
                semaine_key = f"resume_{now.strftime('%Y-W%U')}"
                heure_str = sched.get("horaires", ["09:00"])[0]
                try:
                    h, m = map(int, heure_str.split(":"))
                    if now.hour == h and now.minute == m and semaine_key not in derniers_runs:
                        print("[RESUME] Envoi du résumé hebdomadaire")
                        derniers_runs.append(semaine_key)
                        changed = True
                        threading.Thread(target=_envoyer_resume_hebdo, daemon=True).start()
                except ValueError:
                    pass

            jours_actifs = {_JOURS_SEMAINE[j] for j in sched.get("jours", []) if j in _JOURS_SEMAINE}
            if now.weekday() not in jours_actifs:
                if changed:
                    sched["derniers_runs"] = derniers_runs[-100:]
                    _save_schedule(sched)
                continue

            for heure_str in sched.get("horaires", ["09:00"]):
                try:
                    h, m = map(int, heure_str.split(":"))
                except ValueError:
                    continue
                slot_key = f"{today}_{heure_str}"
                if now.hour == h and now.minute == m and slot_key not in derniers_runs and not _run_status["en_cours"]:
                    print(f"[RUN] Run automatique a {heure_str}")
                    derniers_runs.append(slot_key)
                    changed = True
                    t = threading.Thread(
                        target=_do_run_with_status,
                        kwargs={
                            "source": "mobile.de",
                            "notify_nouvelles": sched.get("nouvelles_annonces", True),
                            "notify_baisses": sched.get("baisses_prix", True),
                        },
                        daemon=True,
                    )
                    t.start()
            if changed:
                sched["derniers_runs"] = derniers_runs[-100:]
                _save_schedule(sched)
        except Exception as e:
            print(f"[WARN] Erreur planificateur : {e}")


# ── Commandes CLI ────────────────────────────────────────────────────────────────
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
            "marque": "BMW", "modele": "Serie 1",
            "budget_max": 20000, "budget_strict": 0,
            "km_max": 100000, "annee_min": 2018,
            "boite": "auto", "carburant": "diesel",
            "vendeur_filtre": "indifferent",
            "options_recherchees": "camera,gps",
            "mobile_de_url": None,
            "client_id": None,
            "poids_prix": 30, "poids_km": 25, "poids_annee": 20,
            "poids_boite": 10, "poids_carburant": 10, "poids_options": 5,
            "penalite_infos_manquantes": 10,
            "score_min_notification": 60, "max_annonces": 3,
        },
        {
            "search_id": "search_peugeot_308",
            "nom_recherche": "Peugeot 308 Essence",
            "statut": "active",
            "marque": "Peugeot", "modele": "308",
            "budget_max": 15000, "budget_strict": 1,
            "km_max": 80000, "annee_min": 2019,
            "boite": "indifferent", "carburant": "essence",
            "vendeur_filtre": "indifferent",
            "options_recherchees": "bluetooth",
            "mobile_de_url": None,
            "client_id": None,
            "poids_prix": 30, "poids_km": 25, "poids_annee": 20,
            "poids_boite": 10, "poids_carburant": 10, "poids_options": 5,
            "penalite_infos_manquantes": 10,
            "score_min_notification": 60, "max_annonces": 3,
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
    from src.database import (
        init_db, get_recherches_actives, insert_recherche, get_recherche_by_id,
        get_derniers_resultats, marquer_interet,
        insert_client, get_clients, get_client_by_id, archiver_client, reactiver_client, supprimer_client, client_nom_existe,
        ajouter_lien_client, get_liens_client, supprimer_lien_client,
        modifier_client, sauvegarder_note_annonce, get_autres_clients_pour_listing,
        get_historique_client, get_recherches_sans_client,
        desactiver_recherche, rattacher_recherche_client,
        get_derniers_runs, get_resume_hebdo,
    )

    init_db()

    UI_DIR = os.path.join(_BASE, "ui")

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

        def _send_file(self, path, content_type="text/html; charset=utf-8"):
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)

        def do_DELETE(self):
            if self.path.startswith("/recherches/"):
                search_id = self.path.split("/recherches/")[1]
                desactiver_recherche(search_id)
                self._send_json({"ok": True})
            elif self.path.startswith("/liens/"):
                lien_id = self.path.split("/liens/")[1]
                supprimer_lien_client(lien_id)
                self._send_json({"ok": True})
            elif self.path.startswith("/clients/"):
                client_id = self.path.split("/clients/")[1]
                client = get_client_by_id(client_id)
                supprimer_client(client_id)
                # Supprimer aussi le dossier Windows (en arrière-plan pour ne pas bloquer)
                if client:
                    dossier = _dossier_client(client["nom"])
                    threading.Thread(target=shutil.rmtree, args=(str(dossier),), kwargs={"ignore_errors": True}, daemon=True).start()
                self._send_json({"ok": True})
            else:
                self.send_response(404)
                self.end_headers()

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send_file(os.path.join(UI_DIR, "index.html"))
            elif self.path == "/clients":
                self._send_json(get_clients("actif"))
            elif self.path == "/clients-archives":
                self._send_json(get_clients("archive"))
            elif self.path.startswith("/historique-client/"):
                client_id = self.path.split("/historique-client/")[1]
                self._send_json(get_historique_client(client_id))
            elif self.path.startswith("/clients/") and self.path.endswith("/liens"):
                client_id = self.path.split("/clients/")[1].replace("/liens", "")
                self._send_json(get_liens_client(client_id))
            elif self.path == "/recherches-sans-client":
                self._send_json(get_recherches_sans_client())
            elif self.path == "/recherches":
                self._send_json(get_recherches_actives())
            elif self.path.startswith("/recherches/"):
                search_id = self.path.split("/recherches/")[1]
                r = get_recherche_by_id(search_id)
                self._send_json(r if r else {}, status=200 if r else 404)
            elif self.path == "/runs":
                self._send_json(get_derniers_runs(15))
            elif self.path == "/dossier-clients-root":
                self._send_json({"path": str(_dossier_clients_root())})
            elif self.path.startswith("/resultats/"):
                search_id = self.path.split("/resultats/")[1]
                annonces = get_derniers_resultats(search_id)
                for a in annonces:
                    a["autres_clients"] = get_autres_clients_pour_listing(a["listing_id"], search_id)
                self._send_json(annonces)
            elif self.path == "/config":
                cfg = _load_config()
                # Ne jamais renvoyer le mot de passe en clair
                if cfg.get("SMTP_PASSWORD"):
                    cfg["SMTP_PASSWORD"] = "***"
                self._send_json(cfg)
            elif self.path == "/planificateur":
                self._send_json(_load_schedule())
            elif self.path == "/status":
                self._send_json(dict(_run_status))
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}

            if self.path == "/clients":
                data = {
                    "client_id": body.get("client_id") or str(uuid.uuid4()),
                    "nom": body.get("nom", "").strip(),
                    "contact": body.get("contact", "").strip(),
                    "notes": body.get("notes", "").strip(),
                }
                if not data["nom"]:
                    self._send_json({"ok": False, "error": "Le nom est obligatoire"}, 400)
                    return
                if client_nom_existe(data["nom"]):
                    self._send_json({"ok": False, "error": f"Un client « {data['nom']} » existe déjà."}, 409)
                    return
                insert_client(data)
                # Création du dossier en arrière-plan pour ne pas bloquer la réponse HTTP
                threading.Thread(target=_creer_dossier_client, args=(data["nom"],), daemon=True).start()
                self._send_json({"ok": True, "client_id": data["client_id"]})

            elif self.path.startswith("/clients/") and self.path.endswith("/archiver"):
                client_id = self.path.split("/clients/")[1].replace("/archiver", "")
                archiver_client(client_id)
                self._send_json({"ok": True})

            elif self.path.startswith("/clients/") and self.path.endswith("/reactiver"):
                client_id = self.path.split("/clients/")[1].replace("/reactiver", "")
                reactiver_client(client_id)
                self._send_json({"ok": True})

            elif self.path == "/ouvrir-dossier-racine":
                _ouvrir_dossier(_dossier_clients_root())
                self._send_json({"ok": True})

            elif self.path.startswith("/clients/") and self.path.endswith("/liens"):
                client_id = self.path.split("/clients/")[1].replace("/liens", "")
                url = body.get("url", "").strip()
                titre = body.get("titre", "").strip()
                if not url:
                    self._send_json({"ok": False, "error": "URL manquante"}, 400)
                    return
                lien_id = ajouter_lien_client(client_id, url, titre)
                self._send_json({"ok": True, "lien_id": lien_id})

            elif self.path.startswith("/clients/") and self.path.endswith("/ouvrir-dossier"):
                client_id = self.path.split("/clients/")[1].replace("/ouvrir-dossier", "")
                client = get_client_by_id(client_id)
                if client:
                    dossier = _dossier_client(client["nom"])
                    recree = not dossier.exists()
                    _creer_dossier_client(client["nom"])  # recrée dossier + voitures/ + documents/
                    _ouvrir_dossier(dossier)
                    self._send_json({"ok": True, "recree": recree})
                else:
                    self._send_json({"ok": False}, 404)

            elif self.path == "/convertir-avif":
                import base64, io
                try:
                    from pillow_heif import register_heif_opener
                    register_heif_opener()
                    from PIL import Image
                except ImportError:
                    self._send_json({"ok": False, "error": "Module manquant. Relancez Carveille pour l'installer."}, 500)
                    return

                files   = body.get("files", [])
                cid     = body.get("client_id")
                client  = get_client_by_id(cid) if cid else None
                if client:
                    save_dir = _dossier_client(client["nom"]) / "voitures"
                else:
                    save_dir = _dossier_clients_root() / "_Non classe"
                save_dir.mkdir(parents=True, exist_ok=True)

                converted, errors = [], []
                for f in files:
                    try:
                        nom  = f.get("nom", "image.avif")
                        data = base64.b64decode(f.get("data", ""))
                        img  = Image.open(io.BytesIO(data))
                        out_nom  = pathlib.Path(nom).stem + ".jpg"
                        out_path = save_dir / out_nom
                        # Éviter d'écraser un fichier existant
                        i = 1
                        while out_path.exists():
                            out_path = save_dir / f"{pathlib.Path(nom).stem}_{i}.jpg"
                            i += 1
                        img.convert("RGB").save(str(out_path), "JPEG", quality=92)
                        converted.append(out_path.name)
                    except Exception as e:
                        errors.append(f"{f.get('nom', '?')} : {e}")

                self._send_json({
                    "ok": True,
                    "converted": converted,
                    "errors": errors,
                    "dossier": str(save_dir),
                })

            elif self.path.startswith("/recherches/") and self.path.endswith("/client"):
                search_id = self.path.split("/recherches/")[1].replace("/client", "")
                rattacher_recherche_client(search_id, body.get("client_id"))
                self._send_json({"ok": True})

            elif self.path == "/recherches":
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
                    "client_id": body.get("client_id") or None,
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
                if _run_status["en_cours"]:
                    self._send_json({"ok": False, "message": "Une recherche est deja en cours, patientez..."})
                    return
                source = body.get("source", "mobile.de")
                day = int(body.get("day", 1))
                t = threading.Thread(
                    target=_do_run_with_status,
                    kwargs={"source": source, "day": day},
                    daemon=True,
                )
                t.start()
                self._send_json({"ok": True, "message": "Recherche lancee !"})

            elif self.path == "/note":
                seen_id = body.get("seen_id")
                note = body.get("note", "")
                if seen_id:
                    sauvegarder_note_annonce(seen_id, note)
                    self._send_json({"ok": True})
                else:
                    self._send_json({"ok": False}, 400)

            elif self.path.startswith("/clients/") and self.path.endswith("/modifier"):
                client_id = self.path.split("/clients/")[1].replace("/modifier", "")
                nom = body.get("nom", "").strip()
                if not nom:
                    self._send_json({"ok": False, "error": "Le nom est obligatoire"}, 400)
                    return
                modifier_client(client_id, {"nom": nom, "contact": body.get("contact", ""), "notes": body.get("notes", "")})
                self._send_json({"ok": True})

            elif self.path == "/interet":
                seen_id = body.get("seen_id")
                interet = body.get("interet")
                if seen_id and interet in ("oui", "non", "neutre"):
                    marquer_interet(seen_id, interet if interet != "neutre" else None)
                    self._send_json({"ok": True})
                else:
                    self._send_json({"ok": False, "error": "Parametres invalides"}, 400)

            elif self.path == "/config":
                allowed = {"SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_DEST", "DOSSIER_CLIENTS"}
                to_save = {k: v for k, v in body.items() if k in allowed and v != "***"}
                to_save["CANAL_NOTIFICATION"] = "email"   # toujours email
                _save_config(to_save)
                self._send_json({"ok": True})

            elif self.path == "/test-email":
                from src.notifier import envoyer_email
                ok = envoyer_email(
                    "Ceci est un email de test de Carveille.\n\nSi vous recevez ce message, la configuration est correcte !",
                    sujet="Carveille — Test de configuration"
                )
                if ok:
                    self._send_json({"ok": True})
                else:
                    self._send_json({"ok": False, "error": "Envoi echoue. Verifiez l'adresse email et le mot de passe d'application."}, 400)

            elif self.path == "/planificateur":
                sched = _load_schedule()
                sched["actif"]             = bool(body.get("actif", False))
                sched["horaires"]          = body.get("horaires") or ["09:00"]
                sched["jours"]             = body.get("jours") or list(_JOURS_SEMAINE.keys())
                sched["nouvelles_annonces"] = bool(body.get("nouvelles_annonces", True))
                sched["baisses_prix"]      = bool(body.get("baisses_prix", True))
                sched["resume_hebdo"]      = bool(body.get("resume_hebdo", False))
                _save_schedule(sched)
                self._send_json({"ok": True})

            else:
                self.send_response(404)
                self.end_headers()

    port = 8765
    url = f"http://localhost:{port}"

    def _open_chrome(u):
        if sys.platform == "win32":
            import subprocess
            result = subprocess.run(["cmd", "/c", "start", "chrome", u], capture_output=True)
            if result.returncode != 0:
                webbrowser.open(u)
        else:
            webbrowser.open(u)

    # Si Carveille est deja lance, ouvrir un onglet et quitter
    import socket as _socket
    with _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM) as _s:
        if _s.connect_ex(("localhost", port)) == 0:
            print(f"[WEB] Carveille est deja en cours d'execution sur http://localhost:{port}")
            _open_chrome(url)
            return

    server = http.server.HTTPServer(("localhost", port), Handler)

    # Demarrer le planificateur en arriere-plan
    threading.Thread(target=_scheduler_thread, daemon=True).start()

    # Ouvrir Chrome apres un court delai (laisse le temps au serveur de demarrer)
    def _open_browser():
        time.sleep(1.5)
        _open_chrome(url)
    threading.Thread(target=_open_browser, daemon=True).start()

    print(f"[WEB] Carveille demarre sur http://localhost:{port}")
    print("      Fermez cette fenetre pour arreter.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[OK] Carveille arrete.")


# ── Point d'entree ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Carveille")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("init")
    sub.add_parser("seed")
    run_p = sub.add_parser("run")
    run_p.add_argument("--source", default="mock", choices=["mock", "mobile.de"])
    run_p.add_argument("--day", type=int, default=1)
    sub.add_parser("ui")

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
