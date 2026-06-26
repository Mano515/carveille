from datetime import datetime, timezone, timedelta
from config import BONUS_FRAICHEUR, ZONES_INONDATION, FINITION_ALIASES


def _age_annonce(date_publication: str | None) -> str | None:
    if not date_publication:
        return None
    try:
        pub = datetime.fromisoformat(date_publication.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - pub
        if age <= timedelta(hours=24):  return "24h"
        if age <= timedelta(hours=48):  return "48h"
        if age <= timedelta(days=7):    return "7j"
    except (ValueError, TypeError):
        pass
    return None


def _score_km_absolu(km: float, p_km: float) -> float:
    """Score basé sur la valeur brute du kilométrage, indépendant du km_max."""
    if km <=  30_000: return p_km
    if km <=  60_000: return round(p_km * 0.88, 1)
    if km <= 100_000: return round(p_km * 0.73, 1)
    if km <= 150_000: return round(p_km * 0.48, 1)
    if km <= 200_000: return round(p_km * 0.22, 1)
    return 0.0  # > 200 000 km → très usé


def _score_annee_absolue(annee: int, p_annee: float) -> float:
    """Score basé sur l'ancienneté réelle du véhicule."""
    age = datetime.now().year - annee
    if age <= 2:  return p_annee
    if age <= 5:  return round(p_annee * 0.85, 1)
    if age <= 8:  return round(p_annee * 0.65, 1)
    if age <= 12: return round(p_annee * 0.40, 1)
    return round(p_annee * 0.15, 1)  # > 12 ans, encore utilisable mais vieux


def scorer_annonce(annonce: dict, recherche: dict) -> dict:
    """
    Score 0-100.
    Chaque critère a un score absolu (toujours actif) ET un score relatif
    aux critères de la recherche. Le plus strict des deux s'applique.
    Un champ inconnu est traité comme suspect, pas comme neutre.
    """
    p_prix      = recherche.get("poids_prix", 30)
    p_km        = recherche.get("poids_km", 25)
    p_annee     = recherche.get("poids_annee", 20)
    p_boite     = recherche.get("poids_boite", 10)
    p_carburant = recherche.get("poids_carburant", 10)
    p_options   = recherche.get("poids_options", 5)

    budget_max    = recherche.get("budget_max")
    prix_min      = recherche.get("prix_min")
    budget_strict = bool(recherche.get("budget_strict", False))
    km_max        = recherche.get("km_max")
    annee_min     = recherche.get("annee_min")
    boite_r       = (recherche.get("boite") or "indifferent").lower()
    carburant_r        = (recherche.get("carburant") or "indifferent").lower()
    vendeur_r          = (recherche.get("vendeur_filtre") or "indifferent").lower()
    couleur_r          = (recherche.get("couleur") or "").lower()
    couleur_imperatif  = bool(recherche.get("couleur_imperatif", False))
    options_r          = recherche.get("options_recherchees") or ""
    options_imp_r      = recherche.get("options_imperatives") or ""
    finition_r         = (recherche.get("finition") or "").lower().strip()
    finition_imperatif = bool(recherche.get("finition_imperatif", False))
    carrosserie_r      = (recherche.get("carrosserie") or "").lower()
    materiaux_r        = (recherche.get("materiaux_interieur") or "").lower()
    couleur_int_r      = (recherche.get("couleur_interieure") or "").lower()

    prix        = annonce.get("prix")
    km          = annonce.get("km")
    date_immat  = annonce.get("date_immat") or ""
    annee       = int(date_immat[:4]) if date_immat and len(date_immat) >= 4 else annonce.get("annee")
    boite_a       = (annonce.get("boite") or "").lower().strip()
    carburant_a   = (annonce.get("carburant") or "").lower().strip()
    vendeur_a     = (annonce.get("vendeur_type") or "").lower()
    options_a     = (annonce.get("options_texte") or "").lower()
    carrosserie_a = (annonce.get("carrosserie") or "").lower().strip()
    date_pub      = annonce.get("date_publication")

    annee_actuelle = datetime.now().year
    detail = {}
    raison_rejet = None

    # ── Prix ──────────────────────────────────────────────────────────────────
    if prix is None:
        score_prix = round(p_prix * 0.30, 1)
    elif prix_min is not None and prix < prix_min * 0.85:
        # Prix anormalement bas : voiture suspecte (accident, inondation, vice caché)
        score_prix = round(p_prix * 0.10, 1)
        if not raison_rejet:
            raison_rejet = f"Prix {prix:.0f}€ anormalement bas (min attendu {prix_min:.0f}€)"
    elif prix_min is not None and prix < prix_min:
        score_prix = round(p_prix * 0.45, 1)
    elif budget_max is None:
        score_prix = p_prix
    elif budget_strict and prix > budget_max:
        score_prix = 0
        raison_rejet = f"Prix {prix:.0f}€ dépasse budget strict {budget_max:.0f}€"
    elif prix > budget_max * 1.05:
        score_prix = 0
        raison_rejet = f"Prix {prix:.0f}€ dépasse budget {budget_max:.0f}€"
    elif prix > budget_max:
        score_prix = round(p_prix * 0.20, 1)   # légèrement au-dessus
    elif prix <= budget_max * 0.65:
        score_prix = p_prix                      # très bonne affaire
    elif prix <= budget_max * 0.80:
        score_prix = round(p_prix * 0.90, 1)    # bien en dessous
    elif prix <= budget_max * 0.92:
        score_prix = round(p_prix * 0.78, 1)    # raisonnable
    else:
        score_prix = round(p_prix * 0.65, 1)    # proche du budget max
    if prix is None:
        detail["prix"] = {"score": score_prix, "max": p_prix, "trouve": "inconnu", "note": "Prix non renseigné"}
    else:
        budget_str = f"≤ {int(budget_max):,}€".replace(",", " ") if budget_max else "libre"
        detail["prix"] = {"score": score_prix, "max": p_prix, "trouve": f"{int(prix):,}€".replace(",", " "), "cherche": budget_str}

    # ── Kilométrage ────────────────────────────────────────────────────────────
    if km is None:
        score_km = round(p_km * 0.20, 1)
        detail["km"] = {"score": score_km, "max": p_km, "trouve": "inconnu", "note": "Kilométrage non renseigné"}
    else:
        score_km_abs = _score_km_absolu(km, p_km)
        if km > 200_000 and not raison_rejet:
            raison_rejet = f"Kilométrage très élevé : {km:.0f} km"
        if km_max is not None:
            if km > km_max * 1.10:
                score_km_rel = 0
                if not raison_rejet:
                    raison_rejet = f"Kilométrage {km:.0f} km dépasse {km_max:.0f} km"
            elif km > km_max:
                score_km_rel = round(p_km * 0.20, 1)
            elif km <= km_max * 0.50:
                score_km_rel = p_km
            elif km <= km_max * 0.75:
                score_km_rel = round(p_km * 0.88, 1)
            else:
                score_km_rel = round(p_km * 0.72, 1)
            score_km = min(score_km_abs, score_km_rel)
        else:
            score_km = score_km_abs
        km_str = f"{int(km):,} km".replace(",", " ")
        cherche_km = f"≤ {int(km_max):,} km".replace(",", " ") if km_max else "libre"
        detail["km"] = {"score": score_km, "max": p_km, "trouve": km_str, "cherche": cherche_km}

    # ── Année ─────────────────────────────────────────────────────────────────
    if annee is None:
        score_annee = round(p_annee * 0.25, 1)
        detail["annee"] = {"score": score_annee, "max": p_annee, "trouve": "inconnu", "note": "Année non renseignée"}
    else:
        if annee > annee_actuelle or annee < 1980:
            score_annee = 0
            detail["annee"] = {"score": 0, "max": p_annee, "trouve": str(annee), "note": "Année invalide"}
        else:
            score_annee_abs = _score_annee_absolue(annee, p_annee)
            if annee_min is not None:
                if annee >= annee_min:
                    score_annee_rel = p_annee
                elif annee == annee_min - 1:
                    score_annee_rel = round(p_annee * 0.60, 1)
                elif annee == annee_min - 2:
                    score_annee_rel = round(p_annee * 0.25, 1)
                else:
                    score_annee_rel = 0
                    if not raison_rejet:
                        raison_rejet = f"Année {annee} trop ancienne (min {annee_min})"
                score_annee = min(score_annee_abs, score_annee_rel)
            else:
                score_annee = score_annee_abs
            cherche_annee = f"≥ {annee_min}" if annee_min else "libre"
            detail["annee"] = {"score": score_annee, "max": p_annee, "trouve": str(annee), "cherche": cherche_annee}

    # ── Kilométrage annuel (km/an) ─────────────────────────────────────────────
    bonus_km_an = 0
    note_km_an = ""
    if km is not None and annee is not None and annee < annee_actuelle and annee >= 1980:
        age_ans = max(1, annee_actuelle - annee)
        km_an = km / age_ans
        if km_an <= 8_000:
            bonus_km_an = 4
            note_km_an = f"{int(km_an):,} km/an — très peu roulée".replace(",", " ")
        elif km_an <= 15_000:
            bonus_km_an = 1
            note_km_an = f"{int(km_an):,} km/an — usage normal".replace(",", " ")
        elif km_an <= 25_000:
            bonus_km_an = -3
            note_km_an = f"{int(km_an):,} km/an — usage élevé".replace(",", " ")
        else:
            bonus_km_an = -7
            note_km_an = f"{int(km_an):,} km/an — usage intensif".replace(",", " ")
    detail["km_an"] = {"score": bonus_km_an, "max": 4, "note": note_km_an}

    # ── Boîte de vitesses ─────────────────────────────────────────────────────
    boite_list = [b.strip() for b in boite_r.split(",") if b.strip() and b.strip() != "indifferent"]
    if not boite_list or boite_r in ("indifferent", ""):
        score_boite = p_boite
        detail["boite"] = {"score": score_boite, "max": p_boite, "cherche": "indifférent", "trouve": boite_a or "inconnu"}
    elif not boite_a:
        score_boite = round(p_boite * 0.40, 1)
        detail["boite"] = {"score": score_boite, "max": p_boite, "cherche": "/".join(boite_list), "trouve": "inconnu", "note": "Non renseignée dans l'annonce"}
    elif boite_a in boite_list:
        score_boite = p_boite
        detail["boite"] = {"score": score_boite, "max": p_boite, "cherche": "/".join(boite_list), "trouve": boite_a}
    else:
        score_boite = 0
        detail["boite"] = {"score": score_boite, "max": p_boite, "cherche": "/".join(boite_list), "trouve": boite_a, "note": "Ne correspond pas"}

    # ── Carburant ─────────────────────────────────────────────────────────────
    carburant_list = [c.strip() for c in carburant_r.split(",") if c.strip() and c.strip() != "indifferent"]
    if not carburant_list or carburant_r in ("indifferent", ""):
        score_carburant = p_carburant
        detail["carburant"] = {"score": score_carburant, "max": p_carburant, "cherche": "indifférent", "trouve": carburant_a or "inconnu"}
    elif not carburant_a:
        score_carburant = round(p_carburant * 0.40, 1)
        detail["carburant"] = {"score": score_carburant, "max": p_carburant, "cherche": "/".join(carburant_list), "trouve": "inconnu", "note": "Non renseigné dans l'annonce"}
    elif any(carburant_a == c or (c == "hybride" and carburant_a.startswith("hybride")) for c in carburant_list):
        score_carburant = p_carburant
        detail["carburant"] = {"score": score_carburant, "max": p_carburant, "cherche": "/".join(carburant_list), "trouve": carburant_a}
    else:
        score_carburant = 0
        detail["carburant"] = {"score": score_carburant, "max": p_carburant, "cherche": "/".join(carburant_list), "trouve": carburant_a, "note": "Ne correspond pas"}

    # ── Vendeur ───────────────────────────────────────────────────────────────
    if vendeur_r in ("indifferent", ""):
        score_vendeur = 0
        detail["vendeur"] = {"score": 0, "max": 0}
    elif vendeur_a == vendeur_r:
        score_vendeur = 0
        detail["vendeur"] = {"score": 0, "max": 0, "cherche": vendeur_r, "trouve": vendeur_a}
    else:
        score_vendeur = -3
        detail["vendeur"] = {"score": -3, "max": 0, "cherche": vendeur_r, "trouve": vendeur_a or "inconnu", "note": "Type de vendeur différent"}

    # ── Couleur (impératif uniquement) ────────────────────────────────────────
    couleur_list = [c.strip() for c in couleur_r.split(",") if c.strip()]
    couleur_a = (annonce.get("couleur") or "").lower()
    if couleur_imperatif and couleur_list:
        if any(c in couleur_a for c in couleur_list):
            malus_couleur = 0
            detail["couleur"] = {"score": 0, "max": 0, "cherche": "/".join(couleur_list), "trouve": couleur_a}
        elif not couleur_a:
            malus_couleur = -5
            detail["couleur"] = {"score": -5, "max": 0, "cherche": "/".join(couleur_list), "trouve": "inconnu", "note": "Couleur non détectée"}
        else:
            malus_couleur = -40
            detail["couleur"] = {"score": -40, "max": 0, "cherche": "/".join(couleur_list), "trouve": couleur_a, "note": "Mauvaise couleur"}
    else:
        malus_couleur = 0
        detail["couleur"] = {"score": 0, "max": 0}

    # ── Carrosserie ───────────────────────────────────────────────────────────
    carrosserie_list = [c.strip() for c in carrosserie_r.split(",") if c.strip()]
    if not carrosserie_list:
        score_carrosserie = 0
        detail["carrosserie"] = {"score": 0, "max": 3}
    elif not carrosserie_a:
        score_carrosserie = 0
        detail["carrosserie"] = {"score": 0, "max": 3, "cherche": "/".join(carrosserie_list), "trouve": "inconnu"}
    elif carrosserie_a in carrosserie_list:
        score_carrosserie = 3
        detail["carrosserie"] = {"score": 3, "max": 3, "cherche": "/".join(carrosserie_list), "trouve": carrosserie_a}
    else:
        score_carrosserie = -5
        detail["carrosserie"] = {"score": -5, "max": 3, "cherche": "/".join(carrosserie_list), "trouve": carrosserie_a, "note": "Ne correspond pas"}

    # ── Options / mots-clés ───────────────────────────────────────────────────
    # Exclure la finition des options et impératives : déjà évaluée via fiche détail,
    # donc pas de double pénalité si renseignée aussi dans options_imperatives/recherchees.
    finition_aliases: set[str] = set()
    if finition_r:
        from config import FINITION_ALIASES
        finition_aliases = {t.lower() for t in FINITION_ALIASES.get(finition_r, [finition_r])}
        finition_aliases.add(finition_r)
    mots_cles = [m.strip().lower() for m in options_r.split(",")
                 if m.strip() and m.strip().lower() not in finition_aliases]
    imperatives = [m.strip().lower() for m in options_imp_r.split(",")
                   if m.strip() and m.strip().lower() not in finition_aliases]
    mat_list = [m.strip().lower() for m in materiaux_r.split(",") if m.strip()]
    col_int_list = [c.strip().lower() for c in couleur_int_r.split(",") if c.strip()]
    mots_cles_bonus = mat_list + col_int_list
    malus_imperatives = 0
    bonus_extra = 0
    if not mots_cles:
        bonus_options = p_options
        detail["options"] = {"score": p_options, "max": p_options, "note": "Aucune option demandée"}
    else:
        presentes = [m for m in mots_cles if m in options_a]
        absentes = [m for m in mots_cles if m not in options_a]
        ratio = len(presentes) / len(mots_cles)
        bonus_options = round(p_options * ratio, 1)
        manquantes = [m for m in imperatives if m not in options_a]
        malus_imperatives = len(manquantes) * -12
        if manquantes and not raison_rejet:
            raison_rejet = f"Option(s) impérative(s) manquante(s) : {', '.join(manquantes)}"
        bonus_extra = sum(2 for m in mots_cles_bonus if m in options_a)
        detail["options"] = {
            "score": bonus_options + malus_imperatives + bonus_extra,
            "max": p_options,
            "presentes": presentes,
            "absentes": absentes,
            "imperatives_manquantes": manquantes,
        }

    # ── Pénalité champs critiques manquants ────────────────────────────────────
    nb_manquants = sum([
        1 if annonce.get("prix") is None else 0,
        1 if annonce.get("km") is None else 0,
        1 if annee is None else 0,
    ])
    penalite = min(nb_manquants * 4, 10)
    detail["penalite"] = {"score": -penalite, "max": 0}

    # ── Bonus fraîcheur ────────────────────────────────────────────────────────
    age_pub = _age_annonce(date_pub)
    bonus_fraicheur = BONUS_FRAICHEUR.get(age_pub, 0) if age_pub else 0
    detail["fraicheur"] = {"score": bonus_fraicheur, "max": 5, "age": age_pub}

    # ── Finition ──────────────────────────────────────────────────────────────
    titre_a = (annonce.get("titre") or "").lower()
    if finition_r:
        mots_finition = [m.strip() for m in finition_r.split(",") if m.strip()]
        termes = []
        for m in mots_finition:
            termes.extend(FINITION_ALIASES.get(m, [m]))
        terme_trouve = next((t for t in termes if t in titre_a or t in options_a), None)
        finition_trouvee = terme_trouve is not None
        if finition_trouvee:
            bonus_finition = 5
        elif finition_imperatif:
            # Impératif non trouvé : malus fort mais pas d'exclusion — reste visible avec score bas
            bonus_finition = -20
            if not raison_rejet:
                raison_rejet = f"Finition '{finition_r}' non trouvée"
        else:
            bonus_finition = 0
        finition_entry = {
            "score": bonus_finition, "max": 5,
            "cherche": finition_r,
            "trouve": terme_trouve or "non trouvé",
        }
        if annonce.get("finition_source"):
            finition_entry["source"] = annonce["finition_source"]
        detail["finition"] = finition_entry
    else:
        bonus_finition = 0
        detail["finition"] = {"score": 0, "max": 5}

    # ── Risque inondation ──────────────────────────────────────────────────────
    ville_a = (annonce.get("ville") or "").lower().strip()
    zone_inondable = bool(ville_a and any(z in ville_a for z in ZONES_INONDATION))
    malus_inondation = -8 if zone_inondable else 0
    detail["inondation"] = {"score": malus_inondation, "max": 0, "risque": zone_inondable, "ville": annonce.get("ville", "")}

    # ── Score final ────────────────────────────────────────────────────────────
    score_brut = (
        score_prix + score_km + score_annee + bonus_km_an
        + score_boite + score_carburant + score_vendeur
        + bonus_options + malus_imperatives + bonus_extra - penalite + bonus_fraicheur + malus_inondation + malus_couleur
        + score_carrosserie + bonus_finition
    )
    score_final = max(0.0, min(100.0, score_brut))

    return {
        "score": round(score_final, 1),
        "detail": detail,
        "raison_rejet": raison_rejet,
    }


def selectionner_top_annonces(annonces_scorees: list, recherche: dict) -> list:
    seuil = recherche.get("score_min_notification", 50)
    max_n = recherche.get("max_annonces", 10)
    filtre = [a for a in annonces_scorees if a["score"] >= seuil]
    filtre.sort(key=lambda a: (a["score"], a.get("date_publication") or ""), reverse=True)
    return filtre[:max_n]
