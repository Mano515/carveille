"""
Scraper mobile.de

Utilise Playwright (vrai navigateur Chromium) pour contourner la protection
Cloudflare de mobile.de, qui bloque les requêtes HTTP simples.

Si la recherche a un champ `mobile_de_url`, cette URL est utilisée directement.
Sinon, l'URL est construite automatiquement depuis les champs marque/modele/budget...
"""

import json
import re
import time
import random
from urllib.parse import urlencode, urljoin

from config import (
    MAKES_MOBILE_DE, MODELS_MOBILE_DE,
    TRANSMISSION_MOBILE_DE, FUEL_MOBILE_DE,
)

BASE_URL = "https://suchen.mobile.de/fahrzeuge/search.html"
BASE_DETAIL_URL = "https://www.mobile.de"


def _build_url(recherche: dict, page: int = 1) -> str:
    """Construit l'URL de recherche mobile.de depuis les critères."""
    params = {
        "isSearchRequest": "true",
        "sortOption.sortBy": "creationTime",
        "sortOption.sortOrder": "DESCENDING",
    }

    marque = recherche.get("marque", "")
    modele = recherche.get("modele", "")

    make_code = MAKES_MOBILE_DE.get(marque, marque.upper().replace(" ", "_")) if marque else ""
    model_code = MODELS_MOBILE_DE.get(modele, modele.upper().replace(" ", "_")) if modele else ""

    if make_code:
        params["makeModelVariant1.make"] = make_code
    if model_code:
        params["makeModelVariant1.model"] = model_code

    if recherche.get("budget_max"):
        params["maxPrice"] = int(recherche["budget_max"])

    if recherche.get("km_max"):
        params["maxMileage"] = int(recherche["km_max"])

    if recherche.get("annee_min"):
        params["minFirstRegistrationDate"] = f"{recherche['annee_min']}-01-01"

    boite = (recherche.get("boite") or "indifferent").lower()
    trans_code = TRANSMISSION_MOBILE_DE.get(boite)
    if trans_code:
        params["transmissionType"] = trans_code

    carburant = (recherche.get("carburant") or "indifferent").lower()
    fuel_code = FUEL_MOBILE_DE.get(carburant)
    if fuel_code:
        params["fuelType"] = fuel_code

    vendeur = (recherche.get("vendeur_filtre") or "indifferent").lower()
    if vendeur == "pro":
        params["damageUnrepaired"] = "NO_DAMAGE_UNREPAIRED"
        params["seller"] = "dealer"
    elif vendeur == "particulier":
        params["seller"] = "private"

    if page > 1:
        params["pageNumber"] = page

    return f"{BASE_URL}?{urlencode(params)}"


def _extract_next_data(html: str) -> dict | None:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def _parse_transmission(val: str) -> str:
    mapping = {
        "AUTOMATIC_GEAR": "auto",
        "MANUAL_GEAR": "manuelle",
        "SEMI_AUTOMATIC_GEAR": "semi-auto",
    }
    return mapping.get(val, val.lower() if val else "")


def _parse_fuel(val: str) -> str:
    mapping = {
        "DIESEL": "diesel",
        "PETROL": "essence",
        "ELECTRIC": "electrique",
        "HYBRID_PETROL": "hybride",
        "HYBRID_DIESEL": "hybride",
        "LPG": "gpl",
        "CNG": "gaz",
    }
    return mapping.get(val, val.lower() if val else "")


def _parse_vendeur(val: str) -> str:
    return "pro" if val in ("DEALER", "dealer") else "particulier"


def _parse_item(item: dict) -> dict | None:
    try:
        listing_id = str(item.get("id", ""))
        if not listing_id:
            return None

        price_data = item.get("price") or {}
        prix = price_data.get("grossAmount") or price_data.get("amount")

        mileage_data = item.get("mileage") or {}
        km = mileage_data.get("value")

        first_reg = item.get("firstRegistration") or ""
        date_immat = first_reg if first_reg else None
        annee = int(first_reg[:4]) if first_reg and len(first_reg) >= 4 else None

        attrs = item.get("attributes") or {}
        boite = _parse_transmission(attrs.get("transmission", ""))
        carburant = _parse_fuel(attrs.get("fuel", ""))

        seller = item.get("seller") or {}
        vendeur_type = _parse_vendeur(seller.get("type", ""))
        ville = seller.get("city") or seller.get("location") or ""

        images = item.get("images") or []
        image_url = images[0].get("uri") if images else None

        titre = item.get("title") or item.get("name") or ""
        creation = item.get("creationDate") or item.get("firstActivationDate") or ""

        features = item.get("features") or []
        if isinstance(features, list):
            options_texte = ", ".join(f for f in features if isinstance(f, str))
        else:
            options_texte = ""

        rel_url = item.get("relativeUrl") or item.get("url") or ""
        url = urljoin(BASE_DETAIL_URL, rel_url) if rel_url else ""

        return {
            "listing_id": listing_id,
            "url": url,
            "titre": titre,
            "prix": float(prix) if prix is not None else None,
            "km": float(km) if km is not None else None,
            "annee": annee,
            "date_immat": date_immat,
            "boite": boite,
            "carburant": carburant,
            "couleur": None,
            "vendeur_type": vendeur_type,
            "ville": ville,
            "image_url": image_url,
            "options_texte": options_texte,
            "date_publication": creation,
        }
    except Exception as e:
        print(f"  [WARN] Impossible de parser un item : {e}")
        return None


def _parse_html(html: str, url: str) -> tuple[list, int]:
    """Extrait les annonces depuis le HTML d'une page de résultats mobile.de."""
    data = _extract_next_data(html)
    if not data:
        print("  [ERR] __NEXT_DATA__ introuvable. mobile.de a peut-etre bloque la requete.")
        print(f"        URL tentee : {url}")
        # Afficher le titre et un extrait du HTML pour diagnostiquer
        titre_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
        if titre_match:
            print(f"        Titre de la page recue : {titre_match.group(1).strip()[:120]}")
        print(f"        Debut HTML : {html[:300].replace(chr(10), ' ')}")
        return [], 0

    try:
        page_props = data["props"]["pageProps"]
        search_result = (
            page_props.get("searchResult")
            or page_props.get("searchResults")
            or {}
        )
        items = search_result.get("items") or search_result.get("ads") or []
        nb_total = (
            search_result.get("numTotalResults")
            or search_result.get("totalCount")
            or len(items)
        )
    except (KeyError, TypeError) as e:
        print(f"  [ERR] Structure __NEXT_DATA__ inattendue : {e}")
        print("        Cles disponibles :", list(data.get("props", {}).get("pageProps", {}).keys()))
        return [], 0

    annonces = [a for a in (_parse_item(i) for i in items) if a]
    return annonces, nb_total


def _chrome_user_data_dir() -> str | None:
    """Retourne le chemin du profil Chrome de l'utilisateur Windows, ou None si introuvable."""
    import pathlib
    candidate = pathlib.Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data"
    return str(candidate) if candidate.exists() else None


def _scrape_avec_playwright(urls: list[str]) -> list[tuple[list, int]]:
    """
    Scrape plusieurs pages via Playwright avec le vrai Chrome de l'utilisateur
    (profil réel = cookies + historique = indétectable par mobile.de).
    Chrome s'ouvre en arrière-plan le temps du scraping puis se ferme.
    """
    from playwright.sync_api import sync_playwright

    user_data_dir = _chrome_user_data_dir()

    resultats = []
    with sync_playwright() as p:
        if user_data_dir:
            # Lance Chrome avec le profil réel de l'utilisateur
            print("  [WEB] Lancement de Chrome (peut prendre quelques secondes)...")
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                channel="chrome",
                headless=False,   # doit être visible pour passer la détection
                args=["--window-position=-32000,-32000"],  # fenêtre hors écran
            )
            owns_browser = False  # launch_persistent_context gère lui-même le cycle de vie
        else:
            # Fallback : Chromium headless si Chrome n'est pas trouvé
            print("  [WEB] Chrome non trouve, utilisation de Chromium...")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(locale="fr-FR", viewport={"width": 1280, "height": 800})
            owns_browser = True

        page = context.new_page()
        page.route("**/*.{png,jpg,jpeg,gif,webp,avif,svg,woff,woff2,ttf}", lambda r: r.abort())

        for i, url in enumerate(urls):
            try:
                page.goto(url, wait_until="networkidle", timeout=45000)
                html = page.content()
                resultats.append(_parse_html(html, url))
            except Exception as e:
                print(f"  [ERR] Playwright : {e}")
                resultats.append(([], 0))

            if i < len(urls) - 1:
                time.sleep(random.uniform(2.0, 3.5))

        context.close()
        if owns_browser:
            browser.close()

    return resultats


def charger(recherche: dict, max_pages: int = 3) -> list:
    """
    Charge les annonces depuis mobile.de via Playwright (vrai navigateur Chromium).
    Utilise `mobile_de_url` si fourni, sinon construit l'URL automatiquement.
    """
    base_url = recherche.get("mobile_de_url") or _build_url(recherche, page=1)
    print(f"  [WEB] Scraping : {base_url[:80]}...")

    # Construire la liste des URLs à scraper (on commence par la page 1)
    urls_a_scraper = [base_url]

    # Scraper la première page pour connaître le total avant de planifier la suite
    resultats_p1 = _scrape_avec_playwright([base_url])
    annonces_p1, nb_total = resultats_p1[0]

    if not annonces_p1:
        print(f"  [WEB] Total scrape : 0 annonces")
        return []

    print(f"  [WEB] Page 1 : {len(annonces_p1)} annonces ({nb_total} au total)")
    toutes = list(annonces_p1)

    # Scraper les pages suivantes si nécessaire
    page = 2
    while len(toutes) < nb_total and page <= max_pages:
        if "pageNumber" in base_url:
            url_page = re.sub(r"pageNumber=\d+", f"pageNumber={page}", base_url)
        else:
            sep = "&" if "?" in base_url else "?"
            url_page = f"{base_url}{sep}pageNumber={page}"

        resultats = _scrape_avec_playwright([url_page])
        annonces, _ = resultats[0]
        if not annonces:
            break

        toutes.extend(annonces)
        print(f"  [WEB] Page {page} : {len(annonces)} annonces")
        page += 1

    print(f"  [WEB] Total scrape : {len(toutes)} annonces")
    return toutes
