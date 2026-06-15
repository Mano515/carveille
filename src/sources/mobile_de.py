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


def _build_url_sans_make(recherche: dict, page: int = 1) -> str:
    """URL de recherche sans make/model (sert de fallback et de base pour les filtres)."""
    parts = []

    if recherche.get("annee_min"):
        parts.append(("fr", f"{recherche['annee_min']}:"))

    parts.append(("isSearchRequest", "true"))

    if recherche.get("km_max"):
        parts.append(("ml", f":{int(recherche['km_max'])}"))

    parts.append(("od", "down"))

    if recherche.get("budget_max"):
        parts.append(("p", f":{int(recherche['budget_max'])}"))

    parts.append(("s", "Car"))
    parts.append(("sb", "doc"))
    parts.append(("vc", "Car"))

    vendeur = (recherche.get("vendeur_filtre") or "indifferent").lower()
    if vendeur == "pro":
        parts.append(("seller", "dealer"))
    elif vendeur == "particulier":
        parts.append(("seller", "private"))

    if page > 1:
        parts.append(("pgn", page))

    return f"{BASE_URL}?{urlencode(parts)}"


def _url_via_detailsuche(driver, recherche: dict) -> str | None:
    """
    Navigue vers le formulaire detailsuche de mobile.de, sélectionne la marque
    et le modèle via les dropdowns natifs, puis retourne l'URL de résultats
    générée par mobile.de lui-même (format toujours correct).
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    marque = recherche.get("marque", "")
    modele = recherche.get("modele", "")
    make_code = MAKES_MOBILE_DE.get(marque, marque.upper().replace(" ", "_")) if marque else ""
    model_code = MODELS_MOBILE_DE.get(modele, modele.upper().replace(" ", "_")) if modele else ""

    if not make_code:
        return None

    try:
        driver.get("https://suchen.mobile.de/fahrzeuge/detailsuche?dam=false&s=Car&vc=Car")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "form"))
        )
        time.sleep(1.5)

        # Trouver et remplir le select "marque"
        make_sel = driver.find_element(By.CSS_SELECTOR,
            'select[name*="make"], select[id*="make"], select[data-testid*="make"]')
        Select(make_sel).select_by_value(make_code)
        print(f"  [WEB] Detailsuche : marque {make_code} sélectionnée")
        time.sleep(2.0)  # attendre le chargement des modèles

        if model_code:
            try:
                model_sel = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        'select[name*="model"], select[id*="model"], select[data-testid*="model"]'))
                )
                Select(model_sel).select_by_value(model_code)
                print(f"  [WEB] Detailsuche : modèle {model_code} sélectionné")
                time.sleep(0.5)
            except Exception as e:
                print(f"  [WEB] Detailsuche : modèle non trouvé ({e}), on continue sans")

        # Soumettre le formulaire
        submit = driver.find_element(By.CSS_SELECTOR, 'button[type="submit"], input[type="submit"]')
        submit.click()
        WebDriverWait(driver, 10).until(EC.url_changes(driver.current_url))
        time.sleep(2.0)

        result_url = driver.current_url
        print(f"  [WEB] Detailsuche URL résultat : {result_url[:120]}")
        return result_url

    except Exception as e:
        print(f"  [WARN] Detailsuche échoué : {e}")
        return None


def _appliquer_filtre_make_model(driver, make_name: str, model_name: str) -> str | None:
    """
    Ouvre le panneau de filtres du SRP mobile.de, sélectionne la marque et le modèle,
    soumet la recherche et retourne la nouvelle URL filtrée (ou None si échec).
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC

    url_avant = driver.current_url

    try:
        # 1. Ouvrir le panneau de filtres complets
        more_btn = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, '[data-testid="more-filters-button"]'))
        )
        more_btn.click()
        time.sleep(2.5)

        # 2. Sélectionner la marque (select data-testid="make-incl-0")
        make_sel_el = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="make-incl-0"]'))
        )
        make_sel = Select(make_sel_el)

        # Chercher l'option dont le texte correspond à make_name (insensible à la casse)
        selected_make = False
        for opt in make_sel.options:
            if make_name.lower() == opt.text.lower().strip():
                make_sel.select_by_value(opt.get_attribute('value'))
                selected_make = True
                break
        if not selected_make:
            # Cherche par inclusion
            for opt in make_sel.options:
                if make_name.lower() in opt.text.lower():
                    make_sel.select_by_value(opt.get_attribute('value'))
                    selected_make = True
                    break

        if not selected_make:
            print(f"  [WARN] Filtre : marque {make_name!r} non trouvée dans le select")
            return None

        print(f"  [WEB] Marque sélectionnée : {make_name}")
        time.sleep(2.5)  # attendre le chargement des modèles

        # 3. Sélectionner le modèle si spécifié
        if model_name:
            try:
                model_sel_el = WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="model-incl-0"]'))
                )
                model_sel = Select(model_sel_el)
                opts = [(o.text.strip(), o.get_attribute('value')) for o in model_sel.options]

                # Code interne mobile.de du modèle (ex: "Serie 1" → "1ER")
                model_code = MODELS_MOBILE_DE.get(model_name, "").lower()

                # Termes de recherche par ordre de priorité
                search_terms = []
                if model_code:
                    search_terms.append(model_code)
                search_terms.append(model_name.lower())

                selected_model = False
                for term in search_terms:
                    if selected_model:
                        break
                    # Correspondance exacte d'abord, puis par inclusion
                    for txt, val in opts:
                        if term == txt.lower():
                            model_sel.select_by_value(val)
                            selected_model = True
                            print(f"  [WEB] Modèle sélectionné (exact) : {txt!r}")
                            break
                    if not selected_model:
                        for txt, val in opts:
                            if term in txt.lower():
                                model_sel.select_by_value(val)
                                selected_model = True
                                print(f"  [WEB] Modèle sélectionné (partiel) : {txt!r}")
                                break

                if not selected_model:
                    print(f"  [WEB] Options modèle ({len(opts)}) : {opts[:8]}")
                    print(f"  [WARN] Modèle {model_name!r} (code: {model_code!r}) non trouvé, on continue sans")
                time.sleep(0.5)
            except Exception as e:
                print(f"  [WARN] Sélection modèle : {e}")

        # 4. Cliquer sur le bouton "Ergebnisse anzeigen" / "Suchen"
        submit_btn = None
        for testid in ['search-button', 'submit-button', 'apply-filters-button']:
            try:
                submit_btn = driver.find_element(By.CSS_SELECTOR, f'[data-testid="{testid}"]')
                break
            except Exception:
                pass
        if not submit_btn:
            # Chercher un bouton contenant "Ergebnisse" ou "Suchen"
            for btn in driver.find_elements(By.CSS_SELECTOR, 'button'):
                txt = btn.text.strip().lower()
                if 'ergebnis' in txt or 'suchen' in txt or 'anzeigen' in txt:
                    submit_btn = btn
                    break
        if not submit_btn:
            print("  [WARN] Bouton submit non trouvé dans le panneau filtres")
            return None

        print(f"  [WEB] Clic sur : {submit_btn.text.strip()!r}")
        submit_btn.click()

        # 5. Attendre que l'URL change
        WebDriverWait(driver, 10).until(EC.url_changes(url_avant))
        time.sleep(2.5)

        new_url = driver.current_url
        print(f"  [WEB] URL filtrée : {new_url[:150]}")
        return new_url

    except Exception as e:
        print(f"  [WARN] Filtre make/model ({type(e).__name__}) : {str(e)[:200]}")
        return None


def _build_url(recherche: dict, page: int = 1) -> str:
    """
    Construit une URL de recherche mobile.de sans make/model.
    Les recherches avec marque/modèle passent par _url_via_detailsuche() à l'exécution.
    """
    return _build_url_sans_make(recherche, page)


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

            listings.push({
                listing_id: id,
                url: url.split('&searchId')[0].split('&ref=')[0],
                titre: title,
                prix: price,
                km: km,
                annee: year,
                boite: boite,
                carburant: fuel,
                ville: ville,
                image_url: image_url,
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
            "couleur": None,
            "vendeur_type": "",
            "ville": item.get("ville") or "",
            "image_url": item.get("image_url"),
            "options_texte": "",
            "date_publication": "",
        })

    total = result.get("total") or len(annonces)
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

    driver = uc.Chrome(options=options, headless=False, use_subprocess=True)

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
            pass

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
    filtre_ui_applique = False
    if recherche.get("mobile_de_url"):
        base_url = recherche["mobile_de_url"]
    else:
        marque = recherche.get("marque", "")
        modele = recherche.get("modele", "")
        initial_url = _build_url(recherche, page=1)

        if marque:
            # Naviguer vers la page de recherche sans make/model, puis ouvrir les filtres
            # pour laisser mobile.de générer lui-même l'URL correcte avec make/model.
            driver.get(initial_url)
            # Accepter le GDPR si la bannière réapparaît sur suchen.mobile.de
            time.sleep(1.5)
            _accepter_cookies_gdpr(driver)
            # Attendre que le SRP soit chargé (bouton filtres visible)
            try:
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                from selenium.webdriver.common.by import By
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="more-filters-button"]'))
                )
            except Exception:
                pass
            time.sleep(2.0)
            filtered_url = _appliquer_filtre_make_model(driver, marque, modele)
            if filtered_url:
                base_url = filtered_url
                filtre_ui_applique = True
            else:
                base_url = initial_url
        else:
            base_url = initial_url

    print(f"  [WEB] Scraping : {base_url[:80]}...")

    annonces_p1, nb_total = _scrape_page(base_url)
    if not annonces_p1:
        print("  [WEB] Total scrape : 0 annonces")
        return []

    print(f"  [WEB] Page 1 : {len(annonces_p1)} annonces ({nb_total} au total)")
    toutes = list(annonces_p1)

    page_num = 2
    while len(toutes) < nb_total and page_num <= max_pages:
        if "pgn=" in base_url:
            url_page = re.sub(r"pgn=\d+", f"pgn={page_num}", base_url)
        elif "pageNumber=" in base_url:
            url_page = re.sub(r"pageNumber=\d+", f"pageNumber={page_num}", base_url)
        else:
            sep = "&" if "?" in base_url else "?"
            url_page = f"{base_url}{sep}pgn={page_num}"

        time.sleep(random.uniform(2.0, 3.5))
        annonces, _ = _scrape_page(url_page)
        if not annonces:
            break
        toutes.extend(annonces)
        print(f"  [WEB] Page {page_num} : {len(annonces)} annonces")
        page_num += 1

    print(f"  [WEB] Total scrape : {len(toutes)} annonces (avant filtre marque/modèle)")

    # Filtre côté client par marque (sanity check sur le titre) — uniquement quand le
    # filtre UI n'a pas pu être appliqué. Quand filtre_ui_applique=True, l'URL ms= gère
    # déjà la marque et le modèle côté serveur, pas besoin de refilter.
    marque_lower = (recherche.get("marque") or "").strip().lower()
    modele_lower = (recherche.get("modele") or "").strip().lower()
    if not filtre_ui_applique and (marque_lower or modele_lower):
        avant = len(toutes)
        def _correspond(ann: dict) -> bool:
            titre = (ann.get("titre") or "").lower()
            if marque_lower and marque_lower not in titre:
                return False
            if modele_lower and modele_lower not in titre:
                return False
            return True
        toutes = [a for a in toutes if _correspond(a)]
        print(f"  [WEB] Après filtre marque/modèle (client) : {len(toutes)} annonces (sur {avant})")

    print(f"  [WEB] Total final : {len(toutes)} annonces")
    return toutes
