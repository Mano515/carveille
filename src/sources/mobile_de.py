# -*- coding: utf-8 -*-
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
import psutil
from urllib.parse import urlencode, urljoin, urlparse, parse_qs, urlunparse, quote

from config import (
    MAKES_MOBILE_DE, MODELS_MOBILE_DE, FINITION_ALIASES,
    TRANSMISSION_MOBILE_DE, FUEL_MOBILE_DE, CARROSSERIE_MOBILE_DE,
)

# Mots-clés de titre pour retrouver un modèle dans les titres allemands mobile.de.
# Ex : "Série 3" → chercher "320", "330", "3er"… car mobile.de affiche "BMW 320d" et pas "Série 3".
MODEL_TITLE_KEYWORDS = {
    "Série 1": ["116", "118", "120", "125", "130", "serie 1", "1er"],
    "Serie 1":  ["116", "118", "120", "125", "130", "serie 1", "1er"],
    "Série 2": ["218", "220", "225", "230", "serie 2", "2er"],
    "Serie 2":  ["218", "220", "225", "230", "serie 2", "2er"],
    "Série 3": ["316", "318", "320", "325", "328", "330", "335", "340", "serie 3", "3er"],
    "Serie 3":  ["316", "318", "320", "325", "328", "330", "335", "340", "serie 3", "3er"],
    "Série 4": ["418", "420", "425", "430", "435", "440", "serie 4", "4er"],
    "Serie 4":  ["418", "420", "425", "430", "435", "440", "serie 4", "4er"],
    "Série 5": ["518", "520", "523", "525", "528", "530", "535", "540", "serie 5", "5er"],
    "Série 7": ["730", "735", "740", "745", "750", "serie 7", "7er"],
    "Classe A": ["a 180", "a 200", "a 220", "a 250", "a-klasse"],
    "Classe C": ["c 180", "c 200", "c 220", "c 250", "c 300", "c-klasse"],
    "Classe E": ["e 200", "e 220", "e 250", "e 300", "e 350", "e-klasse"],
}

BASE_URL = "https://suchen.mobile.de/fahrzeuge/search.html"
BASE_DETAIL_URL = "https://www.mobile.de"
LANG_PARAM = ("lang", "fr")

# Progression partagée — lue par main.py via /status
progression = {"actuel": 0, "total": 0, "etape": ""}


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

    # Boîte de vitesses
    boite_vals = [b.strip() for b in (recherche.get("boite") or "").split(",")
                  if b.strip() and b.strip() != "indifferent"]
    boite_codes = [TRANSMISSION_MOBILE_DE[b] for b in boite_vals if b in TRANSMISSION_MOBILE_DE and TRANSMISSION_MOBILE_DE[b]]
    if len(boite_codes) == 1:  # si les deux sont cochées = indifférent → on n'envoie rien
        parts.append(("tr", boite_codes[0]))

    # Carburant (plusieurs valeurs possibles)
    fuel_vals = [c.strip() for c in (recherche.get("carburant") or "").split(",")
                 if c.strip() and c.strip() != "indifferent"]
    fuel_codes = list({FUEL_MOBILE_DE[v] for v in fuel_vals if v in FUEL_MOBILE_DE and FUEL_MOBILE_DE[v]})
    for code in fuel_codes:
        parts.append(("fuel", code))

    # Carrosserie (plusieurs valeurs possibles)
    carro_vals = [c.strip() for c in (recherche.get("carrosserie") or "").split(",") if c.strip()]
    for v in carro_vals:
        code = CARROSSERIE_MOBILE_DE.get(v.lower())
        if code:
            parts.append(("cat", code))

    # Couleur (uniquement si impératif)
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

    parts.append(LANG_PARAM)
    return f"{BASE_URL}?{urlencode(parts)}"


# IDs numériques mobile.de pour le format d'URL français (ms=makeId;modelId)
# Confirmés depuis les URLs de recherche mobile.de/fr
_MS_IDS: dict[str, dict[str, str]] = {
    "BMW":            {"_make": "3500", "Série 1": "1", "Serie 1": "1", "Série 2": "2", "Serie 2": "2",
                       "Série 3": "10", "Serie 3": "10", "320": "10",
                       "Série 4": "4", "Série 5": "5", "Serie 5": "5",
                       "Série 6": "6", "Série 7": "7",
                       "X1": "32", "X2": "25", "X3": "34", "X4": "35", "X5": "36", "X6": "37", "X7": "38",
                       "Z4": "20", "M3": "12", "M5": "14"},
    "Audi":           {"_make": "1900", "A1": "1", "A3": "3", "A4": "4", "A5": "5", "A6": "6",
                       "A7": "7", "A8": "8", "Q2": "33", "Q3": "18", "Q5": "20", "Q7": "19", "Q8": "28",
                       "TT": "11", "R8": "16", "e-tron": "26"},
    "Mercedes-Benz":  {"_make": "17200", "Classe A": "1", "Classe B": "3", "Classe C": "4",
                       "Classe E": "6", "Classe S": "10", "GLA": "26", "GLB": "36", "GLC": "22",
                       "GLE": "16", "GLS": "17", "CLA": "19", "CLS": "20"},
    "Peugeot":        {"_make": "23600", "208": "61", "308": "62", "408": "64", "508": "63",
                       "2008": "56", "3008": "57", "5008": "58"},
    "Volkswagen":     {"_make": "30000", "Golf": "6", "Polo": "8", "Passat": "7", "Tiguan": "15",
                       "Touareg": "16", "T-Roc": "19", "ID.3": "25", "ID.4": "26"},
    "Renault":        {"_make": "24100", "Clio": "3", "Mégane": "14", "Captur": "26",
                       "Kadjar": "34", "Austral": "45"},
    "Citroën":        {"_make": "6500", "C3": "5", "C4": "6", "C5": "10"},
    "Porsche":        {"_make": "24000", "911": "1", "Cayenne": "7", "Macan": "8", "Panamera": "9",
                       "Taycan": "11"},
}


def build_url_fr(recherche: dict, marque: str = "", modele: str = "") -> str:
    """URL de recherche au format mobile.de/fr — directement utilisable sans redirection."""
    BASE_FR = "https://www.mobile.de/fr/voiture/recherche.html"
    parts: list[tuple] = [("isSearchRequest", "true"), ("s", "Car"), ("vc", "Car")]

    # Marque + modèle via IDs numériques si disponibles, sinon on laisse sans filtre
    make_ids = _MS_IDS.get(marque, {})
    make_id = make_ids.get("_make", "")
    model_id = make_ids.get(modele, "") if modele else ""
    if make_id and model_id:
        parts.append(("ms", f"{make_id};{model_id}"))
    elif make_id:
        parts.append(("ms", f"{make_id};"))

    if recherche.get("prix_min") or recherche.get("budget_max"):
        p_min = int(recherche["prix_min"]) if recherche.get("prix_min") else ""
        p_max = int(recherche["budget_max"]) if recherche.get("budget_max") else ""
        parts.append(("p", f"{p_min}:{p_max}"))

    if recherche.get("annee_min"):
        parts.append(("fr", str(int(recherche["annee_min"]))))

    if recherche.get("km_max"):
        parts.append(("ml", f":{int(recherche['km_max'])}"))

    # Carburant : ft= au lieu de fuel=
    fuel_vals = [c.strip() for c in (recherche.get("carburant") or "").split(",")
                 if c.strip() and c.strip() != "indifferent"]
    from config import FUEL_MOBILE_DE
    for v in fuel_vals:
        code = FUEL_MOBILE_DE.get(v)
        if code:
            parts.append(("ft", code))

    # Boîte
    boite_vals = [b.strip() for b in (recherche.get("boite") or "").split(",")
                  if b.strip() and b.strip() != "indifferent"]
    from config import TRANSMISSION_MOBILE_DE
    boite_codes = [TRANSMISSION_MOBILE_DE[b] for b in boite_vals if b in TRANSMISSION_MOBILE_DE and TRANSMISSION_MOBILE_DE[b]]
    if len(boite_codes) == 1:
        parts.append(("tr", boite_codes[0]))

    vendeur = (recherche.get("vendeur_filtre") or "pro").lower()
    parts.append(("seller", "private" if vendeur == "particulier" else "dealer"))

    return f"{BASE_FR}?{urlencode(parts)}"


def _url_via_detailsuche(driver, marque: str, modele: str, recherche: dict | None = None) -> str | None:
    """
    Navigue vers le formulaire detailsuche de mobile.de, sélectionne marque/modèle
    (et couleur si impérative) via JavaScript, soumet et retourne l'URL résultante.
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

        # Sélectionner la couleur si impérative
        if recherche and recherche.get("couleur_imperatif") and recherche.get("couleur"):
            for couleur_fr in [c.strip().lower() for c in recherche["couleur"].split(",") if c.strip()]:
                couleur_code = _COULEUR_FR_TO_CODE.get(couleur_fr, couleur_fr.upper())
                chosen_color = driver.execute_script("""
                    const code = arguments[0];
                    const selects = document.querySelectorAll('select');
                    for (const sel of selects) {
                        const key = (sel.name + sel.id + (sel.getAttribute('data-testid') || '')).toLowerCase();
                        if (!key.match(/color|farbe|extcol|colour/)) continue;
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
                """, couleur_code)
                if chosen_color:
                    print(f"  [WEB] Detailsuche : couleur sélectionnée via select (id={chosen_color})")
                    break

                # Le filtre couleur n'est pas un <select> — chercher checkbox/swatch cliquable
                clicked_color = driver.execute_script("""
                    const code = arguments[0];  // ex: "ORANGE"
                    const codeLower = code.toLowerCase();

                    // 1. Checkbox avec label ou texte contenant la couleur
                    for (const inp of document.querySelectorAll('input[type="checkbox"]')) {
                        const label = inp.labels && inp.labels[0] ? inp.labels[0].textContent.toLowerCase() : '';
                        const ariaLabel = (inp.getAttribute('aria-label') || '').toLowerCase();
                        const id = inp.id || '';
                        // Trouver le label associé via for=
                        const forLabel = id ? (document.querySelector('label[for="'+id+'"]') || {textContent:''}).textContent.toLowerCase() : '';
                        if ([label, ariaLabel, forLabel].some(t => t.includes(codeLower))) {
                            if (!inp.checked) inp.click();
                            return 'checkbox:' + (label || ariaLabel || forLabel).trim().substring(0, 30);
                        }
                    }

                    // 2. Ãlément cliquable avec data-value, data-color, value ou aria-label = couleur
                    for (const el of document.querySelectorAll('[data-value],[data-color],[data-testid*="color"],[data-testid*="colour"],[data-testid*="farbe"]')) {
                        const val = (el.getAttribute('data-value') || el.getAttribute('data-color') || '').toUpperCase();
                        const label = (el.getAttribute('aria-label') || el.textContent || '').toLowerCase();
                        if (val === code || label.includes(codeLower)) {
                            el.click();
                            return 'swatch:' + val + '/' + label.trim().substring(0, 20);
                        }
                    }

                    // 3. Diagnostic : lister les checkboxes et leurs labels
                    const checks = Array.from(document.querySelectorAll('input[type="checkbox"]')).slice(0, 20).map(inp => {
                        const label = inp.labels && inp.labels[0] ? inp.labels[0].textContent.trim() : '';
                        const forEl = inp.id ? (document.querySelector('label[for="'+inp.id+'"]') || {textContent:''}).textContent.trim() : '';
                        return {id: inp.id, label: label || forEl, value: inp.value};
                    });
                    return {error: 'not_found', checkboxes: checks};
                """, couleur_code)

                if isinstance(clicked_color, str):
                    print(f"  [WEB] Detailsuche : couleur sélectionnée ({clicked_color})")
                    break
                else:
                    checks = (clicked_color or {}).get("checkboxes", [])
                    print(f"  [WEB] Detailsuche : couleur {couleur_code} introuvable (pas de select ni checkbox)")
                    if checks:
                        print(f"  [DIAG] Checkboxes ({len(checks)}) : {checks[:8]}")
                    break

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
                # Attendre que l'URL change — la SPA React met Ã  jour l'URL avec ms=makeId;modelId
                WebDriverWait(driver, 10).until(EC.url_changes(url_avant))
                time.sleep(1.0)
                result_url = driver.current_url
                print(f"  [WEB] Detailsuche URL après submit : {result_url[:120]}")

                if "search.html" in result_url:
                    return result_url

                # mobile.de met Ã  jour detailsuche avec ms=<makeId>;<modelId> sans naviguer.
                # Extraire ms= et construire l'URL search.html avec ce paramètre natif.
                qs = parse_qs(urlparse(result_url).query, keep_blank_values=True)
                ms = qs.get("ms", [None])[0]
                if ms:
                    # Récupérer les filtres natifs que detailsuche a ajoutés Ã  l'URL
                    extra = ""
                    for param in ("ecol", "intCol", "dam"):
                        val = qs.get(param, [None])[0]
                        if val:
                            extra += f"&{param}={quote(val, safe='')}"
                    print(f"  [WEB] Detailsuche : paramètre natif ms={ms!r} extrait{' + ' + extra.lstrip('&') if extra else ''}")
                    return f"https://suchen.mobile.de/fahrzeuge/search.html?ms={quote(ms, safe='')}&isSearchRequest=true&s=Car&vc=Car&od=down&sb=doc{extra}"
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

            // Titre : h2 ou h3, garder les 2 premières lignes (ex: "BMW 320d\nM Sport Touring")
            const titleEl = card.querySelector('h2,h3,h1');
            let titleRaw = titleEl ? titleEl.innerText.trim() : '';
            titleRaw = titleRaw.replace(/^((?:gesponsert|neu)[\s]*)+/i, '');
            const titleLines = titleRaw.split('\n').map(l => l.trim()).filter(Boolean);
            const title = titleLines.slice(0, 2).join(' ').trim();

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

            // Ãquipements : lignes de la carte qui ne sont pas titre/prix/km/date/ville
            const equipLignes = lignes.filter(l =>
                l.length > 2 && l.length < 100 &&
                !titleLines.includes(l) &&
                !/^\d+$/.test(l) &&
                !/\d+[\s.]*(km|€|EUR)/i.test(l) &&
                !/^\d{2}\/\d{4}$/.test(l) &&
                !/^(Automatik|Schaltgetriebe|Diesel|Benzin|Elektro|Hybrid)$/i.test(l)
            );
            const options_texte = equipLignes.join(' ').toLowerCase();

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
                options_texte: options_texte,
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

# Mapping mots-clés couleur allemand → couleur française
_COULEUR_DE_TO_FR = [
    ("orange",   "orange"),
    ("rot",      "rouge"),
    ("schwarz",  "noir"),
    ("weiß",     "blanc"), ("weiss", "blanc"),
    ("blau",     "bleu"),
    ("grün",     "vert"),  ("gruen", "vert"),
    ("grau",     "gris"),
    ("silber",   "argent"),
    ("beige",    "beige"),
    ("braun",    "marron"),
    ("gelb",     "jaune"),
    ("gold",     "or"),
    ("violett",  "violet"),
    ("bronze",   "marron"),
    ("champagner", "beige"),
    ("burgundy", "rouge"), ("bordeaux", "rouge"),
]


def _couleur_de_vers_fr(texte: str) -> str | None:
    """Convertit un texte de couleur allemand (ex: 'Grau Metallic') en couleur française."""
    if not texte:
        return None
    t = texte.lower()
    for mot, fr in _COULEUR_DE_TO_FR:
        if mot in t:
            return fr
    return None


_TITRES_BLOCAGE = ("zugriff verweigert", "access denied", "datadome", "robot", "captcha")

def _est_bloquee(driver) -> bool:
    """Retourne True si la page actuelle est une page de blocage anti-bot."""
    titre = (driver.title or "").lower()
    return any(mot in titre for mot in _TITRES_BLOCAGE)


def _detail_execute_script(driver, url: str, js: str, *args):
    """
    Navigue vers `url` (fiche détail) et exécute `js` dans le contexte de la page.
    Lève BlockedError si mobile.de renvoie une page anti-bot.
    Le sleep est géré par l'appelant (un seul appel = un seul sleep, évite les doublons).
    """
    driver.get(url)
    # Attente minimale pour laisser la SPA charger son contenu (React/Vue hydration)
    time.sleep(2.0)
    if _est_bloquee(driver):
        raise BlockedError(driver.title)
    return driver.execute_script(js, *args)


class BlockedError(Exception):
    """Levée quand mobile.de renvoie une page de blocage anti-bot."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# JS injecté dans la fiche détail pour détecter un terme de finition.
#
# Stratégie en 3 passes (du plus fiable au moins fiable) :
#
#   1. h1 — le titre principal (très stable, jamais du texte vendeur)
#   2. Éléments <li> courts (< 120 car.) — les équipements sont listés en
#      puces courtes sur mobile.de ; les descriptions vendeur sont en prose.
#   3. Page complète (fallback) — mais uniquement sur des lignes courtes
#      (< 120 car.) pour éviter d'attraper les signatures de concessionnaire
#      du type "Ihrem Partner für BMW M Performance".
#
# Retourne { terme, source, extrait } ou null.
# ─────────────────────────────────────────────────────────────────────────────
_JS_CHERCHER_FINITION = """
    const termes = arguments[0];

    // Cherche un terme dans `texte`. Si trouvé, renvoie { terme, source, extrait }.
    function match(texte, source) {
        if (!texte) return null;
        const t = texte.toLowerCase();
        for (const terme of termes) {
            if (t.includes(terme)) {
                const idx   = t.indexOf(terme);
                const debut = Math.max(0, idx - 50);
                const fin   = Math.min(texte.length, idx + terme.length + 50);
                const extrait = texte.substring(debut, fin).replace(/\\s+/g, ' ').trim();
                return { terme, source, extrait };
            }
        }
        return null;
    }

    // Passe 1 : titre h1 (jamais du texte vendeur)
    const h1 = document.querySelector('h1');
    const r1 = match(h1 ? h1.innerText : '', 'Titre de la fiche');
    if (r1) return r1;

    // Passe 2 : éléments <li> courts → les fiches équipement mobile.de
    // sont structurées en listes de puces, contrairement aux descriptions vendeur.
    for (const li of document.querySelectorAll('li')) {
        const txt = (li.innerText || '').trim();
        if (txt.length > 0 && txt.length < 120) {
            const r = match(txt, 'Liste equipements');
            if (r) return r;
        }
    }

    // Passe 3 : fallback page complète, mais seulement sur les lignes courtes.
    // Une ligne > 120 car. est très probablement de la prose (description vendeur,
    // mention de marque) et non un libellé d'équipement.
    const lignes = document.body.innerText.split('\\n');
    for (const ligne of lignes) {
        const t = ligne.trim();
        if (t.length > 0 && t.length < 120) {
            const r = match(t, 'Page complete (ligne courte)');
            if (r) return r;
        }
    }

    return null;
"""

# JS injecte pour lire la couleur via le data-testid stable de mobile.de.
_JS_LIRE_COULEUR = """
    const dt = document.querySelector('[data-testid="color-item"]');
    if (!dt) return null;
    const dd = dt.nextElementSibling;
    return dd ? dd.textContent.trim() : null;
"""

# JS pour extraire toutes les URLs d'images depuis la fiche détail.
# Parcourt récursivement __NEXT_DATA__ pour trouver les champs "uri" d'images.
_JS_LIRE_IMAGES = """
    function walk(obj, found) {
        if (!obj || typeof obj !== 'object') return;
        if (Array.isArray(obj)) { obj.forEach(i => walk(i, found)); return; }
        if (typeof obj.uri === 'string' && obj.uri.startsWith('http')) found.push(obj.uri);
        for (const k of Object.keys(obj)) {
            if (typeof obj[k] === 'object') walk(obj[k], found);
        }
    }
    const found = [];
    try { walk(window.__NEXT_DATA__, found); } catch(e) {}
    if (found.length === 0) {
        for (const img of document.querySelectorAll('img')) {
            const s = img.src || '';
            if (s.startsWith('http') && (s.includes('mobile.de') || s.includes('ebayimg.com'))) found.push(s);
        }
    }
    // Dédupliquer et exclure miniatures
    const seen = new Set();
    return found.filter(u => {
        const low = u.toLowerCase();
        if (seen.has(u)) return false;
        seen.add(u);
        return !low.includes('thumb') && !low.includes('/tn/') && !low.includes('_xs') && !low.includes('48x48') && !low.includes('favicon');
    });
"""


def fetch_images_annonce(url: str) -> list[str]:
    """
    Visite la fiche détail avec Selenium et retourne toutes les URLs d'images.
    Ouvre une session si aucune n'est active (à fermer par l'appelant).
    """
    session_ouverte_ici = False
    if _session is None:
        ouvrir_session()
        session_ouverte_ici = True
    driver = _session["driver"]
    try:
        urls = _detail_execute_script(driver, url, _JS_LIRE_IMAGES)
        return urls or []
    except BlockedError:
        print(f"  [BLOCK] fetch_images_annonce bloqué sur {url[-60:]}")
        return []
    except Exception as e:
        print(f"  [WARN] fetch_images_annonce : {e}")
        return []
    finally:
        if session_ouverte_ici:
            fermer_session()


def _chercher_finition_sur_detail(driver, url: str, termes: list[str]) -> tuple[str | None, str | None, bool]:
    """
    Visite la fiche détail et cherche les termes de finition dans la page.
    Retourne (terme_trouvé, citation, bloquée) :
      - (terme, citation, False) → Pack M trouvé
      - (None, None, False)     → Pack M absent (fiche lue correctement)
      - (None, None, True)      → page bloquée par anti-bot (résultat incertain)
    """
    try:
        result = _detail_execute_script(driver, url, _JS_CHERCHER_FINITION, termes)
        if result:
            citation = f"{result['terme']} — {result['source']} : « {result['extrait']} »"
            return result["terme"], citation, False
        return None, None, False
    except BlockedError as e:
        print(f"      [BLOCK] Anti-bot sur fiche ({url[-50:]}) : {e}")
        return None, None, True
    except Exception as e:
        print(f"      [WARN] Fiche inaccessible ({url[-50:]}) : {e}")
        return None, None, False


def _charger_couleur_depuis_detail(driver, url: str) -> str | None:
    """
    Visite la fiche detail et extrait la couleur via data-testid="color-item".
    Retourne la couleur en francais (ex : "noir") ou None si non trouvee.
    Pas de sleep ici — l'appelant gere le delai.
    """
    try:
        texte = _detail_execute_script(driver, url, _JS_LIRE_COULEUR)
        return _couleur_de_vers_fr(texte)
    except Exception as e:
        print(f"    [WARN] Couleur detail inaccessible ({url[:60]}...) : {e}")
        return None


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
    import tempfile

    print("[WEB] Ouverture de Chrome...")

    # Tuer les Chrome orphelins de Carveille (profil carveille_chrome_*)
    # avant de créer une nouvelle session, pour éviter les conflits de port.
    try:
        for proc in psutil.process_iter(['name', 'cmdline']):
            if 'chrome' in (proc.info['name'] or '').lower():
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'carveille_chrome_' in cmdline:
                    proc.kill()
                    print(f"  [WEB] Chrome orphelin tué (pid {proc.pid})")
    except Exception as e:
        print(f"  [WARN] Nettoyage Chrome orphelins : {e}")

    options = uc.ChromeOptions()
    # Profil isolé dans un dossier temp dédié → évite les conflits avec
    # Chrome normal de l'utilisateur et les sessions orphelines précédentes.
    _profile_dir = tempfile.mkdtemp(prefix="carveille_chrome_")
    options.add_argument(f"--user-data-dir={_profile_dir}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    print(f"  [WEB] Profil Chrome isolé : {_profile_dir}")

    # Compter les Chrome avant lancement pour diagnostiquer
    chromes_avant = [p for p in psutil.process_iter(['name']) if 'chrome' in (p.info['name'] or '').lower()]
    print(f"  [WEB] Processus Chrome avant lancement : {len(chromes_avant)}")

    driver = uc.Chrome(options=options, headless=False, use_subprocess=False, version_main=149)

    time.sleep(1)
    chromes_apres = [p for p in psutil.process_iter(['name']) if 'chrome' in (p.info['name'] or '').lower()]
    print(f"  [WEB] Processus Chrome après lancement : {len(chromes_apres)}")

    # Charger la homepage en français pour initialiser le domaine
    driver.get("https://www.mobile.de/?lang=fr")
    time.sleep(5.0)

    # Vérifier si bloqué par DataDome / anti-bot
    for _attempt in range(4):
        title = driver.title
        if "verweigert" not in title.lower() and "denied" not in title.lower() and "datadome" not in title.lower():
            break
        print(f"  [WARN] Anti-bot détecté (tentative {_attempt+1}/4), attente 5s...")
        time.sleep(5.0)

    title = driver.title
    if "verweigert" in title.lower() or "denied" in title.lower():
        print(f"  [ERR] Homepage bloquée : {title!r} — continuation quand même")
    else:
        print(f"  [OK] Homepage chargée : {title!r}")

    _accepter_cookies_gdpr(driver)
    _injecter_cookies_chrome(driver)
    time.sleep(1.0)

    _session = {"driver": driver}
    print("[OK] Chrome prêt.")


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
    """Scrape une page de résultats avec le driver Chrome déjÃ  ouvert."""
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

        current_url = driver.current_url
        page_title = driver.title

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
                print(f"  [WARN] API parse échouée : {e}")

        # Extraire directement depuis le DOM (Next.js App Router — plus de __NEXT_DATA__)
        dom_annonces, dom_total = _parse_dom_listings(driver)
        if dom_annonces:
            first = dom_annonces[0]
            m_sport_count = sum(1 for a in dom_annonces if any(
                t in (a.get('titre') or '').lower() for t in ['m sport', 'msport', 'm paket', 'm-paket']
            ))
            extra = f" dont {m_sport_count} M Sport" if m_sport_count else ""
            print(f"  [OK] {len(dom_annonces)} annonces extraites{extra} — ex: {first['titre']!r} {int(first['prix'] or 0):,}€ {int(first['km'] or 0):,}km".replace(',', ' '))
            return dom_annonces, dom_total

        # Fallback : parser le HTML complet
        html = driver.page_source
        result = _parse_html(html, url)

        # Page vide — diagnostic détaillé uniquement dans ce cas
        if not result[0]:
            print(f"  [ERR] Aucune annonce extraite — URL: {current_url[:100]!r} | Titre: {page_title!r}")
            try:
                api_logs = driver.execute_script("return window.__carveille_api_logs__ || []")
                if api_logs:
                    print(f"  [ERR] Appels réseau capturés ({len(api_logs)}) :")
                    for log in api_logs[:10]:
                        print(f"        {log.get('status','?')} {log.get('url','')[:100]}")
            except Exception:
                pass
            try:
                info = driver.execute_script("""
                    const articles = document.querySelectorAll('article').length;
                    const prix = document.querySelectorAll('[class*="price"],[class*="Price"]').length;
                    const liens = Array.from(document.querySelectorAll('a[href]'))
                        .map(a=>a.href).filter(h=>h.includes('/fahrzeuge/')&&h.includes('/details')).slice(0,3);
                    return {articles, prix, liens};
                """)
                print(f"  [ERR] DOM : {info['articles']} articles, {info['prix']} éléments prix, liens: {info['liens']}")
            except Exception:
                pass

        return result
    except Exception as e:
        print(f"  [ERR] Scraping page échoué : {e}")
        return [], 0


def charger(recherche: dict, max_pages: int = 10) -> list:
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

    # ── Résumé SRP ────────────────────────────────────────────────────────────
    # Compte les annonces qui ont déjà la finition dans leur titre SRP
    # (pas besoin d'aller sur la fiche pour celles-là).
    m_sport_srp = sum(1 for a in toutes if any(
        t in (a.get('titre') or '').lower() for t in ['m sport', 'msport', 'm paket', 'm-paket']
    ))
    print(f"  [OK] Total : {len(toutes)} annonces uniques — {m_sport_srp} avec M Sport/Paket dans le titre SRP")

    # ── Vérification fiche détail (finition impérative uniquement) ─────────────
    # Pour les annonces où la finition n'est PAS visible dans la carte SRP
    # (titre + options_texte), on visite la fiche complète.
    # On injecte ensuite le terme trouvé dans options_texte pour que scorer_annonce le détecte.
    finition_r = (recherche.get("finition") or "").strip().lower()
    if finition_r and recherche.get("finition_imperatif"):

        # Construire la liste de termes à chercher (même logique que scorer_annonce).
        # Ex : "pack m" → ["pack m", "m paket", "m-paket", "m sport", ...]
        termes_finition = []
        for mot in [m.strip() for m in finition_r.split(",") if m.strip()]:
            termes_finition.extend(FINITION_ALIASES.get(mot, [mot]))

        # Séparer les annonces qui ont déjà la finition de celles qui nécessitent une visite
        deja_ok = [
            a for a in toutes
            if any(t in (a.get("titre") or "").lower() for t in termes_finition)
            or any(t in (a.get("options_texte") or "").lower() for t in termes_finition)
        ]
        candidats_bruts = [a for a in toutes if a not in deja_ok and a.get("url")]
        # DataDome blackliste la session après ~33 visites séquentielles.
        # On se limite à 30 fiches max, triées par prix (les moins chères d'abord
        # = les plus intéressantes si elles ont le Pack M).
        MAX_DETAIL = 30
        candidats_bruts.sort(key=lambda a: (a.get("prix") or 999999))
        candidats = candidats_bruts[:MAX_DETAIL]
        if len(candidats_bruts) > MAX_DETAIL:
            print(f"  [WEB] {len(candidats_bruts)} candidats, limité à {MAX_DETAIL} pour éviter le blacklist DataDome")

        print(f"  [WEB] Finition '{finition_r}' : {len(deja_ok)} trouvées dans carte SRP, "
              f"{len(candidats)} à vérifier sur fiche détail")
        print(f"  [WEB] Termes recherchés : {', '.join(termes_finition)}")

        trouves_detail = 0
        bloques = 0
        delai_base = 4.0  # augmente après chaque blocage
        # URL de la recherche courante pour les pauses de "reset" anti-bot
        url_srp = recherche.get("mobile_de_url") or "https://www.mobile.de/?lang=fr"

        for i, a in enumerate(candidats, 1):
            titre_court = (a.get('titre') or '?')[:55]
            print(f"    [{i}/{len(candidats)}] Vérif fiche : {titre_court}")

            # Toutes les 25 fiches : retour sur la page de recherche pour casser
            # le pattern de visite séquentielle détecté par DataDome.
            if i > 1 and (i - 1) % 25 == 0:
                print(f"    [WEB] Pause anti-bot : retour SRP après {i-1} fiches...")
                driver.get(url_srp)
                time.sleep(random.uniform(8, 15))

            # Délai anti-bot entre chaque fiche (augmente si blocages détectés)
            time.sleep(random.uniform(delai_base, delai_base + 4.0))

            terme, citation, bloquee = _chercher_finition_sur_detail(driver, a["url"], termes_finition)

            if bloquee:
                # Retry unique après une longue pause
                print(f"      [BLOCK] Attente 20s puis retry...")
                time.sleep(random.uniform(20, 30))
                terme, citation, bloquee = _chercher_finition_sur_detail(driver, a["url"], termes_finition)
                if bloquee:
                    bloques += 1
                    delai_base = min(delai_base + 2.0, 12.0)  # durcit le délai après échec
                    a["finition_source"] = "BLOQUÉ"
                    print(f"      [BLOCK] Toujours bloqué, fiche ignorée (délai porté à {delai_base:.0f}s)")
                    continue

            if terme:
                a["options_texte"] = (a.get("options_texte") or "") + f" {terme}"
                a["finition_source"] = citation
                trouves_detail += 1
                print(f"      [OK] Trouvé : {citation[:100]}")
            else:
                a["finition_source"] = None
                print(f"      [--] Non trouvé")

        total_ok = len(deja_ok) + trouves_detail
        print(f"  [OK] Finition '{finition_r}' confirmée : {total_ok}/{len(toutes)} annonces "
              f"({len(deja_ok)} carte SRP + {trouves_detail} fiche détail, {bloques} bloquées)")

    return toutes


def _scraper_url(driver, base_url: str, max_pages: int) -> list:
    """Scrape une URL directe (mobile_de_url fourni manuellement), sans filtre UI."""
    print(f"  [WEB] URL directe : {base_url[:80]}...")
    annonces_p1, nb_total = _scrape_page(base_url)
    if not annonces_p1:
        print(f"  [ERR] Aucune annonce page 1 — abandon")
        return []
    print(f"  [OK] Page 1 : {len(annonces_p1)} annonces ({nb_total} au total)")
    toutes = list(annonces_p1)
    page_num = 2
    while len(toutes) < nb_total and page_num <= max_pages:
        url_page = _url_page(base_url, page_num)
        time.sleep(random.uniform(2.0, 3.5))
        annonces, _ = _scrape_page(url_page)
        if not annonces:
            print(f"  [WARN] Page {page_num} vide — arrêt")
            break
        toutes.extend(annonces)
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
        base_url = _url_via_detailsuche(driver, marque, modele, recherche)
        if base_url:
            # Ajouter les filtres supplémentaires (couleur, prix, km, etc.) Ã  l'URL retournée
            parsed = urlparse(base_url)
            qs = parse_qs(parsed.query, keep_blank_values=True)
            extra = _build_url(recherche, page=1)
            extra_parsed = urlparse(extra)
            extra_qs = parse_qs(extra_parsed.query, keep_blank_values=True)
            # Fusionner : garder les params detailsuche, ajouter ceux de _build_url qui manquent
            # Ignorer extCol si detailsuche a déjÃ  ajouté ecol (même filtre, nom natif prioritaire)
            skip = {"mk", "mo", "s", "vc", "isSearchRequest"}
            if "ecol" in qs:
                skip.add("extCol")
            for k, v in extra_qs.items():
                if k not in qs and k not in skip:
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
        print(f"  [ERR] Aucune annonce page 1 — abandon")
        return []
    print(f"  [OK] Page 1 : {len(annonces_p1)} annonces ({nb_total} au total sur mobile.de)")
    toutes = list(annonces_p1)
    page_num = 2
    while len(toutes) < nb_total and page_num <= max_pages:
        url_page = _url_page(base_url, page_num)
        time.sleep(random.uniform(2.0, 3.5))
        annonces, _ = _scrape_page(url_page)
        if not annonces:
            print(f"  [WARN] Page {page_num} vide — arrêt de la pagination")
            break
        toutes.extend(annonces)
        page_num += 1

    m_sport_total = sum(1 for a in toutes if any(
        t in (a.get('titre') or '').lower() for t in ['m sport', 'msport', 'm paket', 'm-paket']
    ))
    print(f"  [OK] {len(toutes)} annonces scrappées sur {nb_total} disponibles — {m_sport_total} avec M Sport dans le titre")

    if marque:
        marque_lower = marque.strip().lower()
        avant = len(toutes)
        toutes = [a for a in toutes if marque_lower in (a.get("titre") or "").lower()]
        if len(toutes) < avant:
            print(f"  [OK] Filtre marque '{marque}' : {len(toutes)}/{avant}")
        else:
            print(f"  [OK] Filtre marque '{marque}' : toutes les annonces correspondent ({avant})")

        if modele:
            avant2 = len(toutes)
            keywords = MODEL_TITLE_KEYWORDS.get(modele, [modele.strip().lower()])
            toutes = [a for a in toutes if any(kw in (a.get("titre") or "").lower() for kw in keywords)]
            if len(toutes) < avant2:
                print(f"  [OK] Filtre modèle '{modele}' : {len(toutes)}/{avant2}")
            elif avant2 == 0:
                print(f"  [WARN] Filtre modèle '{modele}' : 0 annonces en entrée")
            else:
                print(f"  [OK] Filtre modèle '{modele}' : toutes correspondent ({avant2})")

    # Filtre couleur côté client quand impératif
    couleur_imp = recherche.get("couleur_imperatif") and recherche.get("couleur")
    if couleur_imp:
        couleurs_voulues = [c.strip().lower() for c in recherche["couleur"].split(",") if c.strip()]

        sans_couleur = [a for a in toutes if not a.get("couleur") and a.get("url")]
        if sans_couleur:
            print(f"  [WEB] Récupération couleur sur {len(sans_couleur)} fiches détail...")
            progression["total"] = len(sans_couleur)
            progression["actuel"] = 0
            progression["etape"] = "couleur"
            for i, ann in enumerate(sans_couleur, 1):
                # Sleep AVANT : SPA render + rate-limit anti-bot (un seul sleep)
                time.sleep(random.uniform(2.5, 4.0))
                couleur = _charger_couleur_depuis_detail(driver, ann["url"])
                ann["couleur"] = couleur or ""
                statut = couleur or "inconnue"
                print(f"    [{i}/{len(sans_couleur)}] {ann.get('titre','?')[:50]} → couleur: {statut}")
                progression["actuel"] = i
            progression["etape"] = ""

        avant_c = len(toutes)
        toutes = [a for a in toutes if any(cv in (a.get("couleur") or "") for cv in couleurs_voulues)]
        print(f"  [OK] Filtre couleur '{recherche['couleur']}' : {len(toutes)} gardées, {avant_c - len(toutes)} exclues")

    return toutes


def _url_page(base_url: str, page_num: int) -> str:
    if "pgn=" in base_url:
        return re.sub(r"pgn=\d+", f"pgn={page_num}", base_url)
    if "pageNumber=" in base_url:
        return re.sub(r"pageNumber=\d+", f"pageNumber={page_num}", base_url)
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}pgn={page_num}"
