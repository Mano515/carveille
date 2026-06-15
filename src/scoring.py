from datetime import datetime, timezone, timedelta
from config import TOLERANCE_PRIX_SOUPLE, TOLERANCE_KM_SOUPLE, BONUS_FRAICHEUR, PENALITE_PAR_CHAMP, PENALITE_MAX


def _age_annonce(date_publication: str | None) -> str | None:
    """Retourne '24h', '48h', '7j' ou None selon l'âge de l'annonce."""
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
    Retourne :
    - score (float, 0-100)
    - detail (dict des sous-scores pour affichage)
    - raison_rejet (str ou None)
    """
    p_prix = recherche.get("poids_prix", 30)
    p_km = recherche.get("poids_km", 25)
    p_annee = recherche.get("poids_annee", 20)
    p_boite = recherche.get("poids_boite", 10)
    p_carburant = recherche.get("poids_carburant", 10)
    p_options = recherche.get("poids_options", 5)
    penalite_par_champ = recherche.get("penalite_infos_manquantes", PENALITE_PAR_CHAMP)

    budget_max = recherche.get("budget_max")
    budget_strict = bool(recherche.get("budget_strict", False))
    km_max = recherche.get("km_max")
    annee_min = recherche.get("annee_min")
    boite_r = (recherche.get("boite") or "indifferent").lower()
    carburant_r = (recherche.get("carburant") or "indifferent").lower()
    vendeur_r = (recherche.get("vendeur_filtre") or "indifferent").lower()
    options_r = recherche.get("options_recherchees") or ""

    prix = annonce.get("prix")
    km = annonce.get("km")
    # Préfère date_immat (ex: "2019-06") pour extraire l'année si disponible
    date_immat = annonce.get("date_immat") or ""
    if date_immat and len(date_immat) >= 4:
        annee = int(date_immat[:4])
    else:
        annee = annonce.get("annee")

    boite_a = (annonce.get("boite") or "").lower()
    carburant_a = (annonce.get("carburant") or "").lower()
    vendeur_a = (annonce.get("vendeur_type") or "").lower()
    options_a = (annonce.get("options_texte") or "").lower()
    date_pub = annonce.get("date_publication")

    detail = {}
    raison_rejet = None

    # --- Score Prix ---
    # Paliers : ≤90% du budget → plein score, ≤100% → 70%, ≤105% (si non strict) → 40%, sinon 0.
    if prix is None:
        score_prix = 0
    elif budget_max is None:
        score_prix = p_prix
    elif budget_strict and prix > budget_max:
        score_prix = 0
        raison_rejet = f"Prix {prix:.0f}EUR depasse budget strict {budget_max:.0f}EUR"
    elif prix <= budget_max * 0.90:
        score_prix = p_prix
    elif prix <= budget_max:
        score_prix = p_prix * 0.70
    elif not budget_strict and prix <= budget_max * TOLERANCE_PRIX_SOUPLE:
        score_prix = p_prix * 0.40
    else:
        score_prix = 0
        if not raison_rejet:
            raison_rejet = f"Prix {prix:.0f}EUR depasse budget {budget_max:.0f}EUR"
    detail["prix"] = {"score": round(score_prix, 1), "max": p_prix}

    # --- Score Kilométrage ---
    # Paliers : ≤80% km_max → plein score, ≤100% → 70%, ≤110% → 40%, sinon 0.
    if km is None:
        score_km = 0
    elif km_max is None:
        score_km = p_km
    elif km <= km_max * 0.80:
        score_km = p_km
    elif km <= km_max:
        score_km = p_km * 0.70
    elif km <= km_max * TOLERANCE_KM_SOUPLE:
        score_km = p_km * 0.40
    else:
        score_km = 0
        if not raison_rejet:
            raison_rejet = f"Kilometrage {km:.0f}km depasse {km_max:.0f}km"
    detail["km"] = {"score": round(score_km, 1), "max": p_km}

    # --- Score Année ---
    if annee is None:
        score_annee = 0
    elif annee_min is None:
        score_annee = p_annee
    elif annee >= annee_min:
        score_annee = p_annee
    elif annee == annee_min - 1:
        score_annee = p_annee * 0.50
    else:
        score_annee = 0
        if not raison_rejet:
            raison_rejet = f"Annee {annee} trop ancienne (min {annee_min})"
    detail["annee"] = {"score": round(score_annee, 1), "max": p_annee}

    # --- Score Boîte ---
    if boite_r in ("indifferent", ""):
        score_boite = p_boite
    elif boite_a and boite_a == boite_r:
        score_boite = p_boite
    else:
        score_boite = 0
    detail["boite"] = {"score": round(score_boite, 1), "max": p_boite}

    # --- Score Carburant ---
    if carburant_r in ("indifferent", ""):
        score_carburant = p_carburant
    elif carburant_a and carburant_a == carburant_r:
        score_carburant = p_carburant
    else:
        score_carburant = 0
    detail["carburant"] = {"score": round(score_carburant, 1), "max": p_carburant}

    # --- Score Vendeur ---
    if vendeur_r in ("indifferent", ""):
        score_vendeur = 0  # pas de bonus, pas de malus
    elif vendeur_a == vendeur_r:
        score_vendeur = 0  # correspond, normal
    else:
        # Ne correspond pas : raison de rejet si strict
        score_vendeur = -5  # pénalité légère
    detail["vendeur"] = {"score": round(score_vendeur, 1), "max": 0}

    # --- Bonus Options ---
    mots_cles = [m.strip().lower() for m in options_r.split(",") if m.strip()]
    if not mots_cles:
        bonus_options = p_options
    else:
        trouves = sum(1 for m in mots_cles if m in options_a)
        if trouves == 0:
            bonus_options = 0
        elif trouves == 1:
            bonus_options = p_options * 0.40
        elif trouves == 2:
            bonus_options = p_options * 0.70
        else:
            bonus_options = p_options
    detail["options"] = {"score": round(bonus_options, 1), "max": p_options}

    # --- Pénalités champs manquants ---
    champs_importants = [prix, km, annee, boite_a or None, carburant_a or None]
    nb_manquants = sum(1 for c in champs_importants if c is None or c == "")
    penalite = min(nb_manquants * penalite_par_champ, PENALITE_MAX)
    detail["penalite"] = {"score": -penalite, "max": 0}

    # --- Bonus fraîcheur ---
    age = _age_annonce(date_pub)
    bonus_fraicheur = BONUS_FRAICHEUR.get(age, 0) if age else 0
    detail["fraicheur"] = {"score": bonus_fraicheur, "max": 5, "age": age}

    # --- Score final ---
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
    # Tri : score desc, puis fraîcheur (annonces récentes en tête si score égal)
    filtre.sort(key=lambda a: (a["score"], a.get("date_publication") or ""), reverse=True)
    return filtre[:max_n]
