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


def _build_url(recherche: dict, marque: str = "", modele: str = "", page: int = 1) -> str:
    """URL de recherche complète avec make/model en paramètres URL directs."""
    parts = []

    # Marque et modèle directement dans l'URL (mk/mo) — plus fiable que le Selenium dropdown
    if marque:
        make_code = MAKES_MOBILE_DE.get(marque, marque.upper().replace(" ", "_").replace("-", "_"))
        parts.append(("mk", make_code))
    if modele:
        model_code = MODELS_MOBILE_DE.get(modele, modele.upper().replace(" ", "_").replace("-", "_"))
        parts.append(("mo", model_code))

    if recherche.get("annee_min"):
        parts.append(("fr", f"{recherche['annee_min']}:"))

    parts.append(("isSearchRequest", "true"))

    if recherche.get("km_max"):
        parts.append(("ml", f":{int(recherche['km_max'])}"))

    parts.append(("od", "down"))

    prix_min = recherche.get("prix_min")
    prix_max = recherche.get("budget_max")
    if prix_min or prix_max:
        p_min = int(prix_min) if prix_min else ""
        p_max = int(prix_max) if prix_max else ""
        parts.append(("p", f"{p_min}:{p_max}"))

    parts.append(("s", "Car"))
    parts.append(("sb", "doc"))
    parts.append(("vc", "Car"))

    # Filtre couleur (uniquement si impératif)
    if recherche.get("couleur_imperatif") and recherche.get("couleur"):
        for c in recherche["couleur"].split(","):
            code = _COULEUR_FR_TO_CODE.get(c.strip().lower())
            if code:
                parts.append(("extCol", code))

    vendeur = (recherche.get("vendeur_filtre") or "pro").lower()
    if vendeur == "particulier":
        parts.append(("seller", "private"))
    else:
        parts.append(("seller", "dealer"))

    if page > 1:
        parts.append(("pgn", page))

    return f"{BASE_URL}?{urlencode(parts)}"


def _url_via_detailsuche(driver, marque: str, modele: str) -> str | None:
    """
    Navigue vers le formulaire detailsuche de mobile.de, sélectionne marque/modèle
    via JavaScript (plus fiable que les sélecteurs Selenium), soumet et retourne
    l'URL résultante (format correct garanti par mobile.de).
    """
    make_code = MAKES_MOBILE_DE.get(marque, marque.upper().replace(" ", "_").replace("-", "_")) if marque else ""
    model_code = MODELS_MOBILE_DE.get(modele, modele.upper().replace(" ", "_").replace("-", "_")) if modele else ""

    if not make_code:
        return None

    try:
        driver.get("https://suchen.mobile.de/fahrzeuge/detailsuche?dam=false&s=Car&vc=Car&isSearchRequest=true")
        time.sleep(3.0)
        _accepter_cookies_gdpr(driver)
        time.sleep(1.5)

        # Sélectionner la marque via JS (cherche tout select dont name/id contient make/marke/hersteller)
        chosen_make = driver.execute_script("""
            const code = arguments[0];
            const selects = document.querySelectorAll('select');
            for (const sel of selects) {
                const key = (sel.name + sel.id + (sel.getAttribute('data-testid') || '')).toLowerCase();
                if (!key.match(/make|marke|hersteller/)) continue;
                for (const opt of sel.options) {
                    if (opt.value.toUpperCase() === code.toUpperCase()) {
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        return opt.value;
                    }
                }
                // Fallback : cherche le texte de l'option
                for (const opt of sel.options) {
                    if (opt.text.toUpperCase().includes(code.toUpperCase())) {
                        sel.value = opt.value;
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        return opt.value;
                    }
                }
            }
            return null;
        """, make_code)

        if not chosen_make:
            print(f"  [WARN] Detailsuche : marque {make_code} non trouvée dans les options")
            return None
        print(f"  [WEB] Detailsuche : marque sélectionnée (id={chosen_make})")
        time.sleep(2.5)  # laisser les modèles se charger

        chosen_model = None
        if model_code:
            chosen_model = driver.execute_script("""
                const code = arguments[0];
                const selects = document.querySelectorAll('select');
                for (const sel of selects) {
                    const key = (sel.name + sel.id + (sel.getAttribute('data-testid') || '')).toLowerCase();
                    if (!key.match(/model|modell/)) continue;
                    for (const opt of sel.options) {
                        if (opt.value.toUpperCase() === code.toUpperCase()) {
                            sel.value = opt.value;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            return opt.value;
                        }
                    }
                    for (const opt of sel.options) {
                        if (opt.text.toUpperCase().includes(code.toUpperCase())) {
                            sel.value = opt.value;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            return opt.value;
                        }
                    }
                }
                return null;
            """, model_code)
            if chosen_model:
                print(f"  [WEB] Detailsuche : modèle sélectionné (id={chosen_model})")
            else:
                print(f"  [WEB] Detailsuche : modèle {model_code} non trouvé, continue sans modèle")

        # Essayer de cliquer le bouton Suchen avec Selenium (plus fiable que JS click sur React)
        url_avant = driver.current_url
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        clicked = False
        try:
            # Chercher un bouton visible dont le texte contient un mot-clé de recherche
            keywords = ["suchen", "ergebnis", "treffer", "anzeigen", "search"]
            for btn in driver.find_elements(By.CSS_SELECTOR, "button, a[role='button']"):
                try:
                    txt = btn.text.strip().lower()
                    if any(k in txt for k in keywords) and btn.is_displayed() and btn.is_enabled():
                        btn.click()
                        clicked = True
                        print(f"  [WEB] Detailsuche : submit Selenium ({btn.text.strip()!r})")
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if clicked:
            try:
                # Attendre que l'URL change — la SPA React met à jour l'URL avec ms=makeId;modelId
                WebDriverWait(driver, 10).until(EC.url_changes(url_avant))
                time.sleep(1.0)
                result_url = driver.current_url
                print(f"  [WEB] Detailsuche URL après submit : {result_url[:120]}")

                if "search.html" in result_url:
                    return result_url

                # mobile.de met à jour detailsuche avec ms=<makeId>;<modelId> sans naviguer.
                # Extraire ms= et construire l'URL search.html avec ce paramètre natif.
                from urllib.parse import urlparse, parse_qs, urlencode
                qs = parse_qs(urlparse(result_url).query, keep_blank_values=True)
                ms = qs.get("ms", [None])[0]
                if ms:
                    print(f"  [WEB] Detailsuche : paramètre natif ms={ms!r} extrait")
                    return f"https://suchen.mobile.de/fahrzeuge/search.html?ms={ms}&isSearchRequest=true&s=Car&vc=Car&od=down&sb=doc"
                print(f"  [WARN] Detailsuche : ms= absent de l'URL, fallback")
            except Exception as e:
                print(f"  [WARN] Detailsuche : pas de navigation après submit ({e})")

        # Fallback : on retourne None → l'appelant utilise _build_url + filtres titre côté client.
        return None

    except Exception as e:
        print(f"  [WARN] Detailsuche échoué : {type(e).__name__}: {e}")
        return None



def _extract_next_data(html: str) -> dict | None:
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  [WARN] __NEXT_DATA__ trouvé mais JSON invalide : {e}")
        return None


def _parse_dom_listings(driver) -> tuple[list, int]:
    """
    Extrait les annonces directement depuis le DOM du SRP mobile.de.
    Utilisé depuis mobile.de Next.js 13 App Router qui ne génère plus __NEXT_DATA__.
    """
    result = driver.execute_script(r"""
        const detailLinks = Array.from(document.querySelectorAll('a[href*="details.html?id="], a[href*="/fahrzeuge/details.html"]'));
        const seen = new Set();
        const listings = [];

        for (const a of detailLinks) {
            const url = a.href;
            const idMatch = url.match(/[?&]id=(\d+)/);
            if (!idMatch) continue;
            const id = idMatch[1];
            if (seen.has(id)) continue;
            seen.add(id);

            // Remonter jusqu'au container individuel de la card.
            // Règle : s'arrêter dès que le PARENT contient >1 lien details
            // (on serait sorti de la card dans la liste).
            let card = a;
            for (let i = 0; i < 15; i++) {
                const p = card.parentElement;
                if (!p || p.tagName === 'MAIN' || p.tagName === 'BODY') break;
                const linksInParent = p.querySelectorAll('a[href*="details.html?id="]').length;
                if (linksInParent > 1) break;
                card = p;
            }

            const cardText = card.innerText || '';

            // Prix : "14.990 €" ou "9 900 €"
            const priceMatch = cardText.match(/(\d[\d.\s]*)\s*€/);
            const priceStr = priceMatch ? priceMatch[1].replace(/[\s.]/g, '') : '';
            const price = priceStr ? parseInt(priceStr) : null;

            // Titre : h2 ou h3 dans la card
            const titleEl = card.querySelector('h2,h3,h1');
            let title = titleEl ? titleEl.innerText.trim() : '';
            // Nettoyer les préfixes "Gesponsert" et "NEU"
            title = title.replace(/^(gesponsert|neu)\s*/i, '').replace(/\n[\s\S]*/s, '').trim();

            // km : "45.321 km" ou "45 321 km"
            const kmMatch = cardText.match(/(\d[\d.\s]+)\s*km/);
            const kmStr = kmMatch ? kmMatch[1].replace(/[\s.]/g, '') : '';
            const km = kmStr ? parseInt(kmStr) : null;

            // Année : format "MM/YYYY" seulement (ex: "03/2021"), évite de capter l'année courante
            const yearMatch = cardText.match(/\b(0[1-9]|1[0-2])\/(20[012]\d)\b/);
            const year = yearMatch ? parseInt(yearMatch[2]) : null;

            // Boite
            const boiteMatch = cardText.match(/\b(Automatik|Schaltgetriebe|Halbautomatik)\b/i);
            const boite = boiteMatch ? (boiteMatch[1].toLowerCase().includes('auto') ? 'auto' : 'manuelle') : '';

            // Carburant
            const fuelMatch = cardText.match(/\b(Diesel|Benzin|Elektro|Hybrid|LPG|Erdgas|CNG)\b/i);
            const fuel = fuelMatch ? fuelMatch[1].toLowerCase() : '';

            // Ville : dernière ligne non-vide du card ne contenant pas de chiffres
            const lignes = cardText.split('\n').map(l => l.trim()).filter(Boolean);
            const ville = lignes.slice(-4).reverse().find(l =>
                /^[A-ZÄÖÜ]/.test(l) && !/\d/.test(l) && l.length > 2 && l.length < 45
            ) || '';

            // Image
            const img = card.querySelector('img[src]');
            const image_url = img ? img.src : null;

            // Couleur : chercher dans le texte ET dans les attributs title/aria-label/data-*
            // (mobile.de utilise souvent des swatches avec title="Orange Metallic")
            const couleurMap = {
                'orange': 'orange', 'rot': 'rouge', 'red': 'rouge',
                'weiss': 'blanc', 'weiß': 'blanc', 'white': 'blanc',
                'schwarz': 'noir', 'black': 'noir',
                'blau': 'bleu', 'blue': 'bleu',
                'grün': 'vert', 'gruen': 'vert', 'green': 'vert',
                'grau': 'gris', 'gray': 'gris', 'grey': 'gris',
                'silber': 'argent', 'silver': 'argent',
                'beige': 'beige',
                'braun': 'marron', 'brown': 'marron',
                'gelb': 'jaune', 'yellow': 'jaune',
                'violett': 'violet', 'lila': 'violet', 'purple': 'violet',
                'gold': 'or',
            };
            let couleur = null;
            // 1. Attributs title/aria-label/data-color (swatches avec label)
            const attrTexts = Array.from(card.querySelectorAll('[title],[aria-label],[data-color],[data-testid*="color"]'))
                .map(el => (el.getAttribute('title') || el.getAttribute('aria-label') || el.getAttribute('data-color') || '').toLowerCase())
                .join(' ');
            // 2. Texte brut de la card
            const cardTextLower = (attrTexts + ' ' + cardText).toLowerCase();
            for (const [de, fr] of Object.entries(couleurMap)) {
                if (cardTextLower.includes(de)) { couleur = fr; break; }
            }

            // 3. Swatches CSS : background-color inline (mobile.de utilise souvent des cercles colorés)
            if (!couleur) {
                const cssColorMap = {
                    // Orange et variantes
                    'rgb(255, 102, 0)': 'orange', 'rgb(255, 128, 0)': 'orange',
                    'rgb(230, 88, 0)': 'orange', 'rgb(255, 165, 0)': 'orange',
                    'rgb(255, 140, 0)': 'orange', 'rgb(238, 113, 25)': 'orange',
                    'orange': 'orange', 'darkorange': 'orange',
                    // Rouge
                    'red': 'rouge', 'darkred': 'rouge', 'rgb(255, 0, 0)': 'rouge',
                    'rgb(197, 0, 0)': 'rouge', 'rgb(180, 0, 0)': 'rouge',
                    // Noir
                    'black': 'noir', 'rgb(0, 0, 0)': 'noir', 'rgb(26, 26, 26)': 'noir',
                    // Blanc
                    'white': 'blanc', 'rgb(255, 255, 255)': 'blanc',
                    // Gris
                    'grey': 'gris', 'gray': 'gris', 'rgb(128, 128, 128)': 'gris',
                    'silver': 'argent',
                    // Bleu
                    'blue': 'bleu', 'navy': 'bleu', 'rgb(0, 0, 255)': 'bleu',
                    // Vert
                    'green': 'vert', 'rgb(0, 128, 0)': 'vert',
                    // Marron/beige
                    'brown': 'marron', 'beige': 'beige',
                    // Jaune
                    'yellow': 'jaune', 'rgb(255, 255, 0)': 'jaune',
                };
                for (const el of card.querySelectorAll('[style*="background"]')) {
                    const bg = (el.style.backgroundColor || el.style.background || '').toLowerCase().trim();
                    if (!bg) continue;
                    // Cherche correspondance exacte puis heuristique RGB orange
                    if (cssColorMap[bg]) { couleur = cssColorMap[bg]; break; }
                    // Heuristique : orange si R élevé, G moyen, B bas
                    const m = bg.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
                    if (m) {
                        const [r, g, b] = [+m[1], +m[2], +m[3]];
                        if (r > 180 && g > 60 && g < 160 && b < 50) { couleur = 'orange'; break; }
                        if (r > 180 && g < 50 && b < 50) { couleur = 'rouge'; break; }
                        if (r < 50 && g < 50 && b < 50) { couleur = 'noir'; break; }
                        if (r > 200 && g > 200 && b > 200) { couleur = 'blanc'; break; }
                    }
                }
            }

            listings.push({
                listing_id: id,
                url: 'https://suchen.mobile.de/fahrzeuge/details.html?id=' + id,
                titre: title,
                prix: price,
                km: km,
                annee: year,
                boite: boite,
                carburant: fuel,
                ville: ville,
                image_url: image_url,
                couleur: couleur,
            });
        }

        // Nombre total : compteur global de résultats "X Angebote"
        const allText = document.body.innerText;
        const totalMatch = allText.match(/(\d[\d.]+)\s*Angebote/);
        const total = totalMatch ? parseInt(totalMatch[1].replace(/\./g, '')) : listings.length;

        return {listings, total};
    """)

    if not result or not result.get("listings"):
        return [], 0

    annonces = []
    for item in result["listings"]:
        fuel = item.get("carburant", "").lower()
        fuel_map = {"diesel": "diesel", "benzin": "essence", "elektro": "electrique",
                    "hybrid": "hybride", "lpg": "gpl", "erdgas": "gaz"}
        carburant = fuel_map.get(fuel, fuel)

        annonces.append({
            "listing_id": item["listing_id"],
            "url": item["url"],
            "titre": item.get("titre") or "",
            "prix": float(item["prix"]) if item.get("prix") else None,
            "km": float(item["km"]) if item.get("km") else None,
            "annee": item.get("annee"),
            "date_immat": None,
            "boite": item.get("boite") or "",
            "carburant": carburant,
            "carrosserie": "",
            "couleur": item.get("couleur") or None,
            "vendeur_type": "",
            "ville": item.get("ville") or "",
            "image_url": item.get("image_url"),
            "images_urls": None,
            "options_texte": "",
            "date_publication": "",
        })

    total = result.get("total") or len(annonces)

    # Log diagnostic couleur (1 ligne)
    avec_couleur = sum(1 for a in annonces if a.get("couleur"))
    couleurs = list({a["couleur"] for a in annonces if a.get("couleur")})
    print(f"  [DOM] Couleurs extraites : {avec_couleur}/{len(annonces)} annonces — {couleurs[:8]}")

    return annonces, total


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
        "HYBRID_PETROL": "hybride essence",
        "HYBRID_DIESEL": "hybride diesel",
        "LPG": "gpl",
        "CNG": "gaz",
    }
    return mapping.get(val, val.lower() if val else "")


def _parse_carrosserie(val: str) -> str:
    mapping = {
        "LIMOUSINE": "berline",
        "SEDAN": "berline",
        "KOMBI": "break",
        "ESTATE": "break",
        "SUV": "suv",
        "COUPE": "coupé",
        "CABRIO": "cabriolet",
        "CONVERTIBLE": "cabriolet",
        "VAN": "monospace",
        "MINIVAN": "monospace",
        "KLEINWAGEN": "citadine",
        "CITY_CAR": "citadine",
        "PICKUP": "pickup",
    }
    return mapping.get(val, val.lower() if val else "")


# Mapping couleur mobile.de (code interne) → français
_COULEUR_MAP = {
    "ORANGE": "orange",
    "WEISS": "blanc", "WHITE": "blanc",
    "SCHWARZ": "noir", "BLACK": "noir",
    "ROT": "rouge", "RED": "rouge",
    "BLAU": "bleu", "BLUE": "bleu",
    "GRUEN": "vert", "GREEN": "vert",
    "GRAU": "gris", "GRAY": "gris", "GREY": "gris",
    "SILBER": "argent", "SILVER": "argent",
    "BEIGE": "beige",
    "BRAUN": "marron", "BROWN": "marron",
    "GELB": "jaune", "YELLOW": "jaune",
    "VIOLETT": "violet", "PURPLE": "violet",
    "GOLD": "or",
}

# Mapping couleur français → code mobile.de pour l'URL (extCol) — codes allemands prioritaires
_COULEUR_FR_TO_CODE = {
    "orange": "ORANGE", "blanc": "WEISS", "noir": "SCHWARZ", "rouge": "ROT",
    "bleu": "BLAU", "vert": "GRUEN", "gris": "GRAU", "argent": "SILBER",
    "beige": "BEIGE", "marron": "BRAUN", "jaune": "GELB", "violet": "VIOLETT",
    "or": "GOLD",
}


def _parse_couleur(val: str) -> str:
    if not val:
        return ""
    return _COULEUR_MAP.get(val.upper().strip(), val.lower().strip())


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
        carrosserie = _parse_carrosserie(attrs.get("category", "") or attrs.get("bodyType", "") or item.get("category", ""))
        couleur_raw = attrs.get("color") or attrs.get("exteriorColor") or item.get("color") or item.get("exteriorColor") or ""
        couleur = _parse_couleur(str(couleur_raw))

        seller = item.get("seller") or {}
        vendeur_type = _parse_vendeur(seller.get("type", ""))
        ville = seller.get("city") or seller.get("location") or ""

        images = item.get("images") or []
        image_url = images[0].get("uri") if images else None
        images_urls = "\n".join(img.get("uri", "") for img in images if img.get("uri")) or None

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
            "carrosserie": carrosserie,
            "couleur": couleur or None,
            "vendeur_type": vendeur_type,
            "ville": ville,
            "image_url": image_url,
            "images_urls": images_urls,
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


def _scraping_profile_dir() -> str:
    """Dossier de profil Chrome dédié au scraping, dans le dossier Carveille."""
    import pathlib
    profile = pathlib.Path(__file__).parent.parent / "scraping_profile"
    profile.mkdir(exist_ok=True)
    return str(profile)


# Session Chrome globale — partagée pour tout un run (toutes les recherches)
# pour n'ouvrir Chrome qu'une seule fois et établir les cookies une seule fois.
_session: dict | None = None


def _accepter_cookies_gdpr(driver):
    """
    Accepte le bandeau GDPR de mobile.de.
    Sans ça, le consentement bloque le chargement des annonces.
    """
    result = driver.execute_script("""
        // Chercher le bouton "Tout accepter" par son texte
        const allButtons = Array.from(document.querySelectorAll('button, a[role="button"]'));
        const keywords = ['alle akzept', 'accept all', 'alles akzept', 'zustimmen', 'einverstanden', 'akzeptieren'];
        const btn = allButtons.find(b => {
            const t = b.textContent.trim().toLowerCase();
            return keywords.some(k => t.includes(k));
        });
        if (btn) { btn.click(); return 'cliqué: ' + btn.textContent.trim(); }

        // Fallback: cliquer via data-testid consent
        const consent = document.querySelector('[data-testid*="accept"], [data-testid*="consent-accept"]');
        if (consent) { consent.click(); return 'consent testid: ' + consent.dataset.testid; }

        return 'aucun bouton trouvé';
    """)
    print(f"  [WEB] GDPR : {result}")
    if result and result != 'aucun bouton trouvé':
        time.sleep(1.5)


def _injecter_cookies_chrome(driver):
    """
    Copie les cookies mobile.de du Chrome de l'utilisateur dans le driver.
    Permet de paraître comme une vraie session avec historique.
    """
    try:
        import browser_cookie3
        cookies = list(browser_cookie3.chrome(domain_name='.mobile.de'))
        if not cookies:
            return
        injected = 0
        for c in cookies:
            try:
                cookie = {'name': c.name, 'value': c.value, 'path': c.path or '/'}
                # Normaliser le domaine (selenium exige le point initial)
                domain = c.domain or '.mobile.de'
                if not domain.startswith('.'):
                    domain = '.' + domain
                cookie['domain'] = domain
                if c.secure:
                    cookie['secure'] = True
                driver.add_cookie(cookie)
                injected += 1
            except Exception:
                pass
        if injected:
            print(f"  [WEB] {injected} cookies mobile.de injectés depuis Chrome")
            driver.refresh()
            time.sleep(2.0)
    except Exception as e:
        print(f"  [WEB] Injection cookies ignorée : {e}")


def ouvrir_session():
    """
    Lance Chrome via undetected-chromedriver une fois pour tout le run,
    puis injecte les cookies mobile.de du vrai Chrome de l'utilisateur
    pour paraître comme une session authentique.
    """
    global _session
    if _session is not None:
        return

    import undetected_chromedriver as uc

    print("[WEB] Ouverture de Chrome pour le scraping mobile.de...")

    options = uc.ChromeOptions()
    # Pas de --start-minimized : document.visibilityState doit être "visible"
    # pour passer la détection de mobile.de.
    # La fenêtre Chrome apparaîtra brièvement pendant le scraping, c'est normal.

    driver = uc.Chrome(options=options, headless=False, use_subprocess=True, version_main=149)

    # Charger la homepage pour initialiser le domaine (requis avant add_cookie)
    driver.get("https://www.mobile.de")
    # Attente plus longue : DataDome peut afficher un challenge JS avant de laisser passer
    time.sleep(5.0)

    # Vérifier si bloqué par DataDome / "Zugriff verweigert" — attendre jusqu'à 20s
    for _attempt in range(4):
        title = driver.title
        if "verweigert" not in title.lower() and "denied" not in title.lower() and "datadome" not in title.lower():
            break
        print(f"  [WEB] Challenge détecté (tentative {_attempt+1}/4), attente 5s...")
        time.sleep(5.0)

    # Diagnostic : vérifier si la homepage elle-même est bloquée
    title = driver.title
    src_debut = driver.page_source[:200].replace('\n', ' ')
    print(f"  [DIAG] Homepage titre : {title!r}")
    if "verweigert" in title.lower() or "denied" in title.lower():
        print(f"  [WARN] Homepage toujours bloquée après attentes. Continuation quand même.")

    # Accepter le bandeau GDPR (bloque le chargement des annonces sans ça)
    _accepter_cookies_gdpr(driver)

    # Injecter les cookies du vrai Chrome → session authentique
    _injecter_cookies_chrome(driver)

    time.sleep(1.0)

    _session = {"driver": driver}
    print("[WEB] Chrome prêt.")


def fermer_session():
    """Ferme Chrome après le run."""
    global _session
    if _session is None:
        return
    try:
        _session["driver"].quit()
    except Exception:
        pass
    _session = None
    print("[WEB] Chrome fermé.")


def _intercepter_api(driver) -> dict | None:
    """
    Tente de récupérer les données de recherche depuis le contexte JS de la page.
    Mobile.de (Next.js 13 App Router) ne génère plus __NEXT_DATA__ côté serveur,
    mais expose les données via des variables ou via l'API interne de Next.js.
    """
    # 1. Tenter via window.__NEXT_DATA__ (pages encore SSR)
    try:
        data = driver.execute_script("return window.__NEXT_DATA__")
        if data:
            return data
    except Exception:
        pass

    # 2. Tenter de lire les balises <script type="application/json"> injectées par RSC
    try:
        scripts = driver.find_elements("css selector", 'script[type="application/json"]')
        for s in scripts:
            txt = s.get_attribute("innerHTML") or ""
            if '"items"' in txt or '"ads"' in txt or '"numTotalResults"' in txt:
                return json.loads(txt)
    except Exception:
        pass

    # 3. Tenter via les logs de performance (requêtes XHR interceptées)
    try:
        logs = driver.execute_script("""
            return window.__carveille_api_responses__ || null;
        """)
        if logs:
            return logs
    except Exception:
        pass

    return None


def _injecter_intercepteur(driver):
    """
    Injecte un intercepteur fetch+XHR dans la page pour capturer les réponses
    de l'API de recherche mobile.de et logger tous les appels réseau.
    """
    driver.execute_script("""
        if (window.__carveille_intercepted__) return;
        window.__carveille_intercepted__ = true;
        window.__carveille_api_responses__ = null;
        window.__carveille_api_logs__ = [];

        const _log = (url, status) => {
            window.__carveille_api_logs__.push({url: (url||'').substring(0,200), status, ts: Date.now()});
        };
        const _tryParse = (text, url) => {
            try {
                const p = JSON.parse(text);
                if (p && (p.items || p.ads || p.numTotalResults !== undefined || p.listings)) {
                    window.__carveille_api_responses__ = p;
                }
            } catch(e) {}
        };

        // Intercepter fetch
        const origFetch = window.fetch;
        window.fetch = async function(...args) {
            const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
            let resp;
            try { resp = await origFetch(...args); } catch(e) { _log(url, 'ERR'); throw e; }
            _log(url, resp.status);
            try { const clone = resp.clone(); const text = await clone.text(); _tryParse(text, url); } catch(e) {}
            return resp;
        };

        // Intercepter XHR
        const origOpen = XMLHttpRequest.prototype.open;
        const origSend = XMLHttpRequest.prototype.send;
        XMLHttpRequest.prototype.open = function(m, url, ...r) {
            this.__url = url; return origOpen.call(this, m, url, ...r);
        };
        XMLHttpRequest.prototype.send = function(...args) {
            this.addEventListener('load', function() {
                _log(this.__url, this.status);
                _tryParse(this.responseText, this.__url);
            });
            return origSend.call(this, ...args);
        };
    """)


def _scrape_page(url: str) -> tuple[list, int]:
    """Scrape une page de résultats avec le driver Chrome déjà ouvert."""
    from selenium.webdriver.support.ui import WebDriverWait

    if _session is None:
        raise RuntimeError("Session non ouverte — appelez ouvrir_session() d'abord.")
    driver = _session["driver"]
    try:
        # Injecter l'intercepteur fetch AVANT de naviguer
        try:
            _injecter_intercepteur(driver)
        except Exception:
            pass

        driver.get(url)

        # Injecter de nouveau car la navigation réinitialise le contexte JS
        try:
            _injecter_intercepteur(driver)
        except Exception:
            pass

        # Scroller lentement pour déclencher le chargement des annonces (lazy loading)
        for scroll_y in [400, 800, 1200, 1600]:
            driver.execute_script(f"window.scrollTo(0, {scroll_y});")
            time.sleep(0.5)
        driver.execute_script("window.scrollTo(0, 0);")

        # Attendre que les résultats soient disponibles (30 s max)
        try:
            WebDriverWait(driver, 30).until(lambda d: (
                "__NEXT_DATA__" in d.page_source
                or d.execute_script("return !!window.__carveille_api_responses__")
                or len(d.find_elements("css selector", "article")) > 2
                or d.find_elements("css selector", '[data-testid*="result-item"]')
                or d.find_elements("css selector", 'a[href*="/fahrzeuge/details"]')
                or d.find_elements("css selector", 'a[href*="/fahrzeuge/gebrauchtwagen"]')
            ))
        except Exception:
            print("  [WARN] Timeout 30s : page pas encore prête (on continue quand même)")

        time.sleep(2.0)

        # Diagnostic URL + titre (pour vérifier que la page est un vrai SRP)
        current_url = driver.current_url
        page_title = driver.title
        print(f"  [DIAG] URL actuelle : {current_url[:120]}")
        print(f"  [DIAG] Titre page   : {page_title!r}")


        # Essayer d'abord les données via l'API interceptée ou JS
        api_data = _intercepter_api(driver)
        if api_data:
            try:
                items = api_data.get("items") or api_data.get("ads") or []
                nb_total = api_data.get("numTotalResults") or api_data.get("totalCount") or len(items)
                annonces = [a for a in (_parse_item(i) for i in items) if a]
                if annonces:
                    return annonces, nb_total
            except Exception as e:
                print(f"  [WARN] Parse API data : {e}")

        # Extraire directement depuis le DOM (Next.js App Router — plus de __NEXT_DATA__)
        dom_annonces, dom_total = _parse_dom_listings(driver)
        if dom_annonces:
            first = dom_annonces[0]
            print(f"  [WEB] DOM parser : {len(dom_annonces)} annonces | ex: titre={first['titre']!r} prix={first['prix']} km={first['km']} annee={first['annee']}")
            return dom_annonces, dom_total

        # Fallback : parser le HTML complet (pour les pages encore SSR)
        html = driver.page_source
        result = _parse_html(html, url)

        # Diagnostic de la structure d'une card (premier appel seulement)
        if not getattr(_scrape_page, '_diag_card_done', False):
            _scrape_page._diag_card_done = True
            try:
                card_html = driver.execute_script(r"""
                    const a = document.querySelector('a[href*="details.html?id="]');
                    if (!a) return 'Pas de lien details';
                    // Remonter jusqu'à trouver un container avec prix ET km
                    let card = a;
                    for (let i = 0; i < 10; i++) {
                        const p = card.parentElement;
                        if (!p || p.tagName === 'MAIN' || p.tagName === 'BODY') break;
                        card = p;
                        const hasPrice = !!(card.querySelector('[class*="price"],[class*="Price"]'));
                        const hasMileage = card.innerText.includes(' km');
                        if (hasPrice && hasMileage) break;
                    }
                    return {
                        html: card.outerHTML.substring(0, 2000),
                        innerText: card.innerText.substring(0, 300),
                        priceEl: (card.querySelector('[class*="price"],[class*="Price"]') || {}).outerHTML || 'absent',
                        titleEl: (card.querySelector('h2,h3,h1,[class*="title"],[class*="Title"]') || {}).innerText || 'absent',
                    };
                """)
                print(f"  [DIAG-CARD] innerText : {str(card_html.get('innerText',''))[:200]!r}")
                print(f"  [DIAG-CARD] priceEl   : {str(card_html.get('priceEl',''))[:200]}")
                print(f"  [DIAG-CARD] titleEl   : {str(card_html.get('titleEl',''))[:100]!r}")
                print(f"  [DIAG-CARD] HTML (2k) : {str(card_html.get('html',''))[:800]}")
            except Exception as e:
                print(f"  [DIAG-CARD] Erreur : {e}")

        # Diagnostic si toujours vide
        if not result[0]:
            # Afficher les appels API capturés
            try:
                api_logs = driver.execute_script("return window.__carveille_api_logs__ || []")
                print(f"  [DIAG] Appels réseau ({len(api_logs)}) :")
                for log in api_logs[:15]:
                    print(f"         {log.get('status')} {log.get('url','')[:100]}")
            except Exception:
                pass

            info = driver.execute_script("""
                // Articles et structure DOM
                const articles = Array.from(document.querySelectorAll('article'));
                const firstArt = articles[0];

                // Chercher les liens d'annonces (détails véhicule)
                const liensDetails = Array.from(document.querySelectorAll('a[href]'))
                    .map(a => a.href)
                    .filter(h => h.includes('/fahrzeuge/') && h.includes('/details'))
                    .slice(0, 5);

                // Chercher les éléments avec prix
                const elsPrix = Array.from(document.querySelectorAll('[class*="price"],[class*="Price"],[data-testid*="price"]'));

                // Chercher les éléments ressemblant à des listing cards
                const listingEls = Array.from(document.querySelectorAll(
                    '[class*="listing"],[class*="Listing"],[class*="result-item"],[class*="VehicleCard"],[class*="vehicleCard"],[class*="SearchResult"]'
                ));

                // data-testids présents dans la page
                const testids = [...new Set(
                    Array.from(document.querySelectorAll('[data-testid]'))
                        .map(el => el.getAttribute('data-testid'))
                )];

                // Premier article HTML
                const srp = document.querySelector('[data-testid="srp"]');

                return {
                    nb_articles: articles.length,
                    first_article_html: firstArt ? firstArt.outerHTML.substring(0, 800) : 'aucun',
                    nb_prix: elsPrix.length,
                    nb_listing_els: listingEls.length,
                    first_listing_html: listingEls[0] ? listingEls[0].outerHTML.substring(0, 400) : 'aucun',
                    liens_details: liensDetails,
                    testids: testids.slice(0, 30),
                    srp_present: !!srp,
                };
            """)
            print(f"  [DIAG] articles={info['nb_articles']}, prix={info['nb_prix']}, listing_els={info['nb_listing_els']}")
            print(f"  [DIAG] 1er article : {info['first_article_html'][:400]}")
            print(f"  [DIAG] 1er listing el : {info['first_listing_html']}")
            print(f"  [DIAG] Liens détails : {info['liens_details']}")
            print(f"  [DIAG] testids ({len(info['testids'])}) : {info['testids'][:20]}")

        return result
    except Exception as e:
        print(f"  [ERR] Chrome : {e}")
        return [], 0


def charger(recherche: dict, max_pages: int = 3) -> list:
    """
    Charge les annonces depuis mobile.de.
    Utilise `mobile_de_url` si fourni, sinon construit l'URL depuis les critères.
    Si une marque est spécifiée, passe par le formulaire detailsuche pour obtenir
    une URL de résultats valide (le format make/model de l'API a changé).
    La session Chrome doit être ouverte via ouvrir_session() avant l'appel.
    """
    # Ouvrir la session si elle n'est pas encore ouverte (appel unitaire hors runner)
    if _session is None:
        ouvrir_session()

    driver = _session["driver"]

    _session["_recherche_courante"] = recherche

    # Déterminer l'URL de base
    if recherche.get("mobile_de_url"):
        toutes = _scraper_url(driver, recherche["mobile_de_url"], max_pages)
    else:
        marque = recherche.get("marque", "")
        modeles_raw = recherche.get("modele", "") or ""
        modeles = [m.strip() for m in modeles_raw.split(",") if m.strip()]

        if not modeles:
            modeles = [""]  # pas de filtre modèle

        toutes_ids: set = set()
        toutes: list = []

        for modele in modeles:
            if len(modeles) > 1:
                print(f"  [WEB] Passage modèle : {modele or '(tous)'}")
            annonces = _scraper_avec_filtre(driver, recherche, marque, modele, max_pages)
            for a in annonces:
                lid = a.get("listing_id")
                if lid not in toutes_ids:
                    toutes_ids.add(lid)
                    toutes.append(a)

    print(f"  [WEB] Total final : {len(toutes)} annonces")
    return toutes


def _scraper_url(driver, base_url: str, max_pages: int) -> list:
    """Scrape une URL directe (mobile_de_url fourni manuellement), sans filtre UI."""
    print(f"  [WEB] Scraping : {base_url[:80]}...")
    annonces_p1, nb_total = _scrape_page(base_url)
    if not annonces_p1:
        print("  [WEB] Total scrape : 0 annonces")
        return []
    print(f"  [WEB] Page 1 : {len(annonces_p1)} annonces ({nb_total} au total)")
    toutes = list(annonces_p1)
    page_num = 2
    while len(toutes) < nb_total and page_num <= max_pages:
        url_page = _url_page(base_url, page_num)
        time.sleep(random.uniform(2.0, 3.5))
        annonces, _ = _scrape_page(url_page)
        if not annonces:
            break
        toutes.extend(annonces)
        print(f"  [WEB] Page {page_num} : {len(annonces)} annonces")
        page_num += 1
    return toutes


def _scraper_avec_filtre(driver, recherche: dict, marque: str, modele: str, max_pages: int) -> list:
    """Scrape mobile.de pour une combinaison marque/modèle unique.
    Priorité 1 : _url_via_detailsuche (URL générée par mobile.de, toujours correcte).
    Priorité 2 : _build_url (mk=/mo= dans l'URL) + filtre titre côté client en fallback.
    """
    filtre_url_ok = False
    base_url = None

    # Priorité 1 : detailsuche via JS — génère des URLs que mobile.de reconnaît
    if marque:
        base_url = _url_via_detailsuche(driver, marque, modele)
        if base_url:
            # Ajouter les filtres supplémentaires (couleur, prix, km, etc.) à l'URL retournée
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(base_url)
            qs = parse_qs(parsed.query, keep_blank_values=True)
            extra = _build_url(recherche, page=1)
            extra_parsed = urlparse(extra)
            extra_qs = parse_qs(extra_parsed.query, keep_blank_values=True)
            # Fusionner : garder les params detailsuche, ajouter ceux de _build_url qui manquent
            for k, v in extra_qs.items():
                if k not in qs and k not in ("mk", "mo", "s", "vc", "isSearchRequest"):
                    qs[k] = v
            new_query = urlencode({k: v[0] for k, v in qs.items()})
            base_url = urlunparse(parsed._replace(query=new_query))
            filtre_url_ok = True
            print(f"  [WEB] Scraping (detailsuche) : {base_url[:200]}...")

    # Priorité 2 : URL directe avec mk/mo (peut être ignoré par mobile.de)
    if not base_url:
        base_url = _build_url(recherche, marque=marque, modele=modele, page=1)
        print(f"  [WEB] Scraping (fallback URL) : {base_url[:200]}...")

    annonces_p1, nb_total = _scrape_page(base_url)
    if not annonces_p1:
        print("  [WEB] 0 annonces")
        return []
    print(f"  [WEB] Page 1 : {len(annonces_p1)} annonces ({nb_total} au total)")
    toutes = list(annonces_p1)
    page_num = 2
    while len(toutes) < nb_total and page_num <= max_pages:
        url_page = _url_page(base_url, page_num)
        time.sleep(random.uniform(2.0, 3.5))
        annonces, _ = _scrape_page(url_page)
        if not annonces:
            break
        toutes.extend(annonces)
        print(f"  [WEB] Page {page_num} : {len(annonces)} annonces")
        page_num += 1

    print(f"  [WEB] Total scrape : {len(toutes)} annonces (avant filtre client)")

    if marque:
        marque_lower = marque.strip().lower()
        avant = len(toutes)
        # La marque est toujours filtrée côté client — contrainte dure, pas un critère de score.
        # mobile.de peut ignorer mk= ou mk=<id> selon son humeur ; on ne fait pas confiance à l'URL.
        toutes = [a for a in toutes if marque_lower in (a.get("titre") or "").lower()]
        print(f"  [WEB] Filtre marque '{marque}' : {len(toutes)} annonces (sur {avant})")

        if modele:
            modele_lower = modele.strip().lower()
            avant2 = len(toutes)
            toutes = [a for a in toutes if modele_lower in (a.get("titre") or "").lower()]
            print(f"  [WEB] Filtre modèle '{modele}' : {len(toutes)} annonces (sur {avant2})")

    # Filtre couleur côté client quand impératif et couleur connue (mauvaise couleur → éliminé)
    couleur_imp = recherche.get("couleur_imperatif") and recherche.get("couleur")
    if couleur_imp:
        couleurs_voulues = [c.strip().lower() for c in recherche["couleur"].split(",") if c.strip()]
        avant_c = len(toutes)
        toutes = [a for a in toutes if
                  not a.get("couleur")  # couleur inconnue : garde (scoring appliquera -8)
                  or any(cv in (a.get("couleur") or "") for cv in couleurs_voulues)]
        eliminees = avant_c - len(toutes)
        if eliminees:
            print(f"  [WEB] Filtre couleur '{recherche['couleur']}' : {eliminees} annonce(s) exclue(s) (mauvaise couleur connue)")

    return toutes


def _url_page(base_url: str, page_num: int) -> str:
    if "pgn=" in base_url:
        return re.sub(r"pgn=\d+", f"pgn={page_num}", base_url)
    if "pageNumber=" in base_url:
        return re.sub(r"pageNumber=\d+", f"pageNumber={page_num}", base_url)
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}pgn={page_num}"
