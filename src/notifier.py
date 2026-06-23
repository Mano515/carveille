import os
import json
import smtplib
from email.mime.text import MIMEText
import requests
from dotenv import load_dotenv

load_dotenv()


def _formater_detail(score_detail_json: str) -> str:
    if not score_detail_json:
        return ""
    try:
        d = json.loads(score_detail_json)
    except Exception:
        return ""
    lignes = []
    labels = {
        "prix": "Prix", "km": "Km", "annee": "Annee",
        "boite": "Boite", "carburant": "Carburant",
        "options": "Options", "vendeur": "Vendeur",
        "penalite": "Penalite", "fraicheur": "Fraicheur",
    }
    for key, label in labels.items():
        if key not in d:
            continue
        item = d[key]
        score = item.get("score", 0)
        max_v = item.get("max", 0)
        if key == "penalite" and score == 0:
            continue
        if key == "fraicheur" and score == 0:
            continue
        if key == "vendeur" and score == 0:
            continue
        if max_v > 0:
            lignes.append(f"    {label}: {score}/{max_v}")
        else:
            lignes.append(f"    {label}: {score:+.0f}")
    return "\n".join(lignes)


def _formater_annonce(ann: dict, idx: int) -> str:
    boite = ann.get("boite") or "?"
    carburant = ann.get("carburant") or "?"
    vendeur = ann.get("vendeur_type") or "?"
    ville = ann.get("ville") or "?"
    prix = f"{int(ann['prix']):,}EUR".replace(",", " ") if ann.get("prix") else "?"
    km = f"{int(ann['km']):,}km".replace(",", " ") if ann.get("km") else "?"
    score = ann.get("score", 0)
    url = ann.get("url", "")
    titre = ann.get("titre", "")

    # Date immat vs annee
    date_immat = ann.get("date_immat")
    annee_str = date_immat if date_immat else (str(ann.get("annee", "?")) if ann.get("annee") else "?")

    baisse = ann.get("baisse_prix", 0)
    baisse_str = f" [BAISSE -{baisse:.0f}EUR]" if baisse and baisse > 0 else ""

    detail_str = _formater_detail(ann.get("score_detail", ""))
    detail_block = f"\n   Detail :\n{detail_str}" if detail_str else ""

    return (
        f"{idx}. {titre}{baisse_str} -- {prix} -- {km} -- Score : {score}/100\n"
        f"   {ville} | {vendeur.capitalize()} | {boite.capitalize()} | {carburant.capitalize()} | 1ere immat : {annee_str}"
        f"{detail_block}\n"
        f"   {url}"
    )


def formater_message(recherche: dict, annonces: list) -> str:
    nom = recherche.get("nom_recherche", "Recherche")
    nb = len(annonces)
    lignes = [f"Carveille -- {nb} nouvelle{'s' if nb > 1 else ''} annonce{'s' if nb > 1 else ''} pour \"{nom}\""]
    lignes.append("-" * 60)
    for i, ann in enumerate(annonces, 1):
        lignes.append(_formater_annonce(ann, i))
        lignes.append("")
    return "\n".join(lignes)


def envoyer_telegram(message: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[WARN] Telegram non configure (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID manquants)")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={"chat_id": chat_id, "text": message, "disable_web_page_preview": True})
    if resp.ok:
        print("[OK] Notification Telegram envoyee.")
        return True
    print(f"[ERR] Erreur Telegram : {resp.text}")
    return False


def envoyer_email(message: str, sujet: str = "Carveille -- Nouvelles annonces") -> bool:
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    dest = os.getenv("SMTP_DEST", user)
    if not user or not password:
        print("[WARN] Email non configure (SMTP_USER / SMTP_PASSWORD manquants)")
        return False
    try:
        msg = MIMEText(message, "plain", "utf-8")
        msg["Subject"] = sujet
        msg["From"] = user
        msg["To"] = dest
        with smtplib.SMTP(host, port) as s:
            s.starttls()
            s.login(user, password)
            s.sendmail(user, [dest], msg.as_string())
        print(f"[OK] Email envoye a {dest}.")
        return True
    except Exception as e:
        print(f"[ERR] Erreur email : {e}")
        return False


def notifier(recherche: dict, annonces: list):
    if not annonces:
        return
    message = formater_message(recherche, annonces)
    print("\n" + message)

    canal = os.getenv("CANAL_NOTIFICATION", "console").lower()
    if canal == "telegram":
        envoyer_telegram(message)
    elif canal == "email":
        envoyer_email(message)
