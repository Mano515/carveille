from datetime import datetime, timezone, timedelta
from config import BONUS_FRAICHEUR


def _age_annonce(date_publication: str | None) -> str | None:
    if not date_publication:
        return None
    try:
        pub = datetime.fromisoformat(date_publication.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - pub
        if age <= timedelta(hours=24):
            return "24h"
        if age <= timedelta(hours=48):
            return "48h"
        if age <= timedelta(days=7):
            return "7j"
    except (ValueError, TypeError):
        pass
    return None


def scorer_annonce(annonce: dict, recherche: dict) -> dict:
    """
    Score 0-100. Chaque critère a des paliers progressifs.
    Les champs inconnus donnent un score partiel (pas 0).
    """
    p_prix      = recherche.get("poids_prix", 30)
    p_km        = recherche.get("poids_km", 25)
    p_annee     = recherche.get("poids_annee", 20)
    p_boite     = recherche.get("poids_boite", 10)
    p_carburant = recherche.get("poids_carburant", 10)
    p_options   = recherche.get("poids_options", 5)

    budget_max   = recherche.get("budget_max")
    budget_strict = bool(recherche.get("budget_strict", False))
    km_max       = recherche.get("km_max")
    annee_min    = recherche.get("annee_min")
    boite_r      = (recherche.get("boite") or "indifferent").lower()
    carburant_r  = (recherche.get("carburant") or "indifferent").lower()
    vendeur_r    = (recherche.get("vendeur_filtre") or "indifferent").lower()
    options_r    = recherche.get("options_recherchees") or ""

    prix        = annonce.get("prix")
    km          = annonce.get("km")
    date_immat  = annonce.get("date_immat") or ""
    annee       = int(date_immat[:4]) if date_immat and len(date_immat) >= 4 else annonce.get("annee")
    boite_a     = (annonce.get("boite") or "").lower().strip()
    carburant_a = (annonce.get("carburant") or "").lower().strip()
    vendeur_a   = (annonce.get("vendeur_type") or "").lower()
    options_a   = (annonce.get("options_texte") or "").lower()
    date_pub    = annonce.get("date_publication")

    detail = {}
    raison_rejet = None

    # ── Prix ──────────────────────────────────────────────────────────────────
    # Plein score dans le budget ; bonus si vraiment pas cher ; 0 au-delà de +5%
    if prix is None:
        score_prix = round(p_prix * 0.5, 1)   # inconnu : score neutre
    elif budget_max is None:
        score_prix = p_prix
    elif budget_strict and prix > budget_max:
        score_prix = 0
        raison_rejet = f"Prix {prix:.0f}EUR dépasse budget strict {budget_max:.0f}EUR"
    elif prix > budget_max * 1.05:
        score_prix = 0
        raison_rejet = f"Prix {prix:.0f}EUR dépasse budget {budget_max:.0f}EUR"
    elif prix > budget_max:
        score_prix = round(p_prix * 0.25, 1)  # légèrement au-dessus
    elif prix <= budget_max * 0.70:
        score_prix = p_prix                    # vraie bonne affaire
    elif prix <= budget_max * 0.85:
        score_prix = round(p_prix * 0.90, 1)  # bien en dessous
    else:
        score_prix = round(p_prix * 0.75, 1)  # dans le budget
    detail["prix"] = {"score": score_prix, "max": p_prix}

    # ── Kilométrage ────────────────────────────────────────────────────────────
    # Plein score si bien en dessous ; score partiel jusqu'à +10% ; 0 au-delà
    if km is None:
        score_km = round(p_km * 0.5, 1)
    elif km_max is None:
        score_km = p_km
    elif km > km_max * 1.10:
        score_km = 0
        if not raison_rejet:
            raison_rejet = f"Kilométrage {km:.0f}km dépasse {km_max:.0f}km"
    elif km > km_max:
        score_km = round(p_km * 0.30, 1)   # légèrement au-dessus
    elif km <= km_max * 0.50:
        score_km = p_km                     # peu roulée
    elif km <= km_max * 0.75:
        score_km = round(p_km * 0.88, 1)   # raisonnable
    else:
        score_km = round(p_km * 0.72, 1)   # dans les clous
    detail["km"] = {"score": score_km, "max": p_km}

    # ── Année ─────────────────────────────────────────────────────────────────
    if annee is None:
        score_annee = round(p_annee * 0.4, 1)
    elif annee_min is None:
        score_annee = p_annee
    elif annee >= annee_min:
        score_annee = p_annee
    elif annee == annee_min - 1:
        score_annee = round(p_annee * 0.60, 1)
    elif annee == annee_min - 2:
        score_annee = round(p_annee * 0.25, 1)
    else:
        score_annee = 0
        if not raison_rejet:
            raison_rejet = f"Année {annee} trop ancienne (min {annee_min})"
    detail["annee"] = {"score": score_annee, "max": p_annee}

    # ── Boîte de vitesses ─────────────────────────────────────────────────────
    # Inconnu → score partiel (on ne peut pas pénaliser ce qu'on ne sait pas)
    if boite_r in ("indifferent", ""):
        score_boite = p_boite
    elif not boite_a:
        score_boite = round(p_boite * 0.40, 1)  # inconnu
    elif boite_a == boite_r:
        score_boite = p_boite
    else:
        score_boite = 0
    detail["boite"] = {"score": score_boite, "max": p_boite}

    # ── Carburant ─────────────────────────────────────────────────────────────
    if carburant_r in ("indifferent", ""):
        score_carburant = p_carburant
    elif not carburant_a:
        score_carburant = round(p_carburant * 0.40, 1)  # inconnu
    elif carburant_a == carburant_r:
        score_carburant = p_carburant
    else:
        score_carburant = 0
    detail["carburant"] = {"score": score_carburant, "max": p_carburant}

    # ── Vendeur ───────────────────────────────────────────────────────────────
    if vendeur_r in ("indifferent", ""):
        score_vendeur = 0
    elif vendeur_a == vendeur_r:
        score_vendeur = 0
    else:
        score_vendeur = -3   # léger malus si ne correspond pas
    detail["vendeur"] = {"score": score_vendeur, "max": 0}

    # ── Options / mots-clés ───────────────────────────────────────────────────
    mots_cles = [m.strip().lower() for m in options_r.split(",") if m.strip()]
    if not mots_cles:
        bonus_options = p_options
    else:
        trouves = sum(1 for m in mots_cles if m in options_a)
        ratio = trouves / len(mots_cles)
        bonus_options = round(p_options * ratio, 1)
    detail["options"] = {"score": bonus_options, "max": p_options}

    # ── Pénalité champs manquants ──────────────────────────────────────────────
    # Réduite : -3 par champ, cap à -10. On ne punit que les champs critiques.
    champs_critiques = [prix, km, annee]
    nb_manquants = sum(1 for c in champs_critiques if c is None)
    penalite = min(nb_manquants * 3, 10)
    detail["penalite"] = {"score": -penalite, "max": 0}

    # ── Bonus fraîcheur ────────────────────────────────────────────────────────
    age = _age_annonce(date_pub)
    bonus_fraicheur = BONUS_FRAICHEUR.get(age, 0) if age else 0
    detail["fraicheur"] = {"score": bonus_fraicheur, "max": 5, "age": age}

    # ── Score final ────────────────────────────────────────────────────────────
    score_brut = (
        score_prix + score_km + score_annee
        + score_boite + score_carburant + score_vendeur
        + bonus_options - penalite + bonus_fraicheur
    )
    score_final = max(0.0, min(100.0, score_brut))

    return {
        "score": round(score_final, 1),
        "detail": detail,
        "raison_rejet": raison_rejet,
    }


def selectionner_top_annonces(annonces_scorees: list, recherche: dict) -> list:
    seuil = recherche.get("score_min_notification", 60)
    max_n = recherche.get("max_annonces", 3)
    filtre = [a for a in annonces_scorees if a["score"] >= seuil]
    filtre.sort(key=lambda a: (a["score"], a.get("date_publication") or ""), reverse=True)
    return filtre[:max_n]
