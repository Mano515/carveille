"""
Scraper mobile.de

Construit l'URL de recherche à partir des critères de la recherche,
récupère la page (SSR Next.js) et extrait les annonces depuis __NEXT_DATA__.

Si la recherche a un champ `mobile_de_url`, cette URL est utilisée directement
(pratique : l'utilisateur fait sa recherche sur mobile.de, copie l'URL, la colle).
Sinon, l'URL est construite automatiquement depuis les champs marque/modele/budget...
"""

import json
import re
import time
import random
from urllib.parse import urlencode, urljoin

# curl_cffi imite le fingerprint TLS de Chrome, ce qui contourne le blocage 403 de mobile.de
from curl_cffi import requests

from config import (
    MAKES_MOBILE_DE, MODELS_MOBILE_DE,
    TRANSMISSION_MOBILE_DE, FUEL_MOBILE_DE,
)

BASE_URL = "https://suchen.mobile.de/fahrzeuge/search.html"
BASE_DETAIL_URL = "https://www.mobile.de"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,de;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


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
        params["isSearchRequest"] = "true"
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


def _scrape_page(session: requests.Session, url: str) -> tuple[list, int]:
    """Retourne (annonces, nb_total)."""
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [ERR] Erreur HTTP : {e}")
        return [], 0

    data = _extract_next_data(resp.text)
    if not data:
        print("  [ERR] __NEXT_DATA__ introuvable. mobile.de a peut-etre bloque la requete.")
        print(f"        URL tentee : {url}")
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


def charger(recherche: dict, max_pages: int = 3) -> list:
    """
    Charge les annonces depuis mobile.de.
    Utilise `mobile_de_url` si fourni, sinon construit l'URL automatiquement.
    """
    # impersonate="chrome124" : curl_cffi imite le TLS/JA3 de Chrome pour passer la détection de bot
    session = requests.Session(impersonate="chrome124")
    session.headers.update(HEADERS)

    base_url = recherche.get("mobile_de_url") or _build_url(recherche, page=1)
    print(f"  [WEB] Scraping : {base_url[:80]}...")

    toutes = []
    for page in range(1, max_pages + 1):
        if page == 1:
            url = base_url
        else:
            # Remplace ou ajoute pageNumber dans l'URL
            if "pageNumber" in base_url:
                url = re.sub(r"pageNumber=\d+", f"pageNumber={page}", base_url)
            else:
                sep = "&" if "?" in base_url else "?"
                url = f"{base_url}{sep}pageNumber={page}"

        annonces, nb_total = _scrape_page(session, url)
        if not annonces:
            break

        toutes.extend(annonces)
        print(f"  [WEB] Page {page} : {len(annonces)} annonces ({nb_total} au total)")

        if len(toutes) >= nb_total:
            break

        time.sleep(random.uniform(1.5, 3.0))

    print(f"  [WEB] Total scrape : {len(toutes)} annonces")
    return toutes
