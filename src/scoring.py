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
    detail["prix"] = {"score": score_prix, "max": p_prix}

    # ── Kilométrage ────────────────────────────────────────────────────────────
    # Score absolu TOUJOURS actif : une voiture à 250 000 km reste risquée
    # même si le critère km_max n'est pas renseigné.
    if km is None:
        # Km non renseigné : suspicion (info potentiellement cachée)
        score_km = round(p_km * 0.20, 1)
        detail["km"] = {"score": score_km, "max": p_km, "note": "non renseigné"}
    else:
        score_km_abs = _score_km_absolu(km, p_km)

        if km > 200_000 and not raison_rejet:
            raison_rejet = f"Kilométrage très élevé : {km:.0f} km"

        if km_max is not None:
            # Score relatif au critère
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
            # Le plus strict des deux s'applique
            score_km = min(score_km_abs, score_km_rel)
        else:
            score_km = score_km_abs
        detail["km"] = {"score": score_km, "max": p_km}

    # ── Année ─────────────────────────────────────────────────────────────────
    # Score absolu TOUJOURS actif : une voiture de 2008 est objectivement vieille.
    if annee is None:
        score_annee = round(p_annee * 0.25, 1)
        detail["annee"] = {"score": score_annee, "max": p_annee, "note": "non renseignée"}
    else:
        # Bloquer les années manifestement fausses (scraping artifact)
        if annee > annee_actuelle or annee < 1980:
            score_annee = 0
            detail["annee"] = {"score": 0, "max": p_annee, "note": "année invalide"}
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
            detail["annee"] = {"score": score_annee, "max": p_annee}

    # ── Kilométrage annuel (km/an) ─────────────────────────────────────────────
    # Si km et année connus, on peut estimer l'usage annuel.
    # Un taxi fait 80 000 km/an, une voiture "normale" 12-15 000 km/an.
    bonus_km_an = 0
    if km is not None and annee is not None and annee < annee_actuelle and annee >= 1980:
        age_ans = max(1, annee_actuelle - annee)
        km_an = km / age_ans
        if km_an <= 8_000:
            bonus_km_an = 4    # très peu roulée (retraité, collection)
        elif km_an <= 15_000:
            bonus_km_an = 1    # usage normal
        elif km_an <= 25_000:
            bonus_km_an = -3   # usage élevé (commercial ?)
        else:
            bonus_km_an = -7   # usage intensif (taxi, livreur)
    detail["km_an"] = {"score": bonus_km_an, "max": 4}

    # ── Boîte de vitesses ─────────────────────────────────────────────────────
    boite_list = [b.strip() for b in boite_r.split(",") if b.strip() and b.strip() != "indifferent"]
    if not boite_list or boite_r in ("indifferent", ""):
        score_boite = p_boite
    elif not boite_a:
        score_boite = round(p_boite * 0.40, 1)
    elif boite_a in boite_list:
        score_boite = p_boite
    else:
        score_boite = 0
    detail["boite"] = {"score": score_boite, "max": p_boite}

    # ── Carburant ─────────────────────────────────────────────────────────────
    carburant_list = [c.strip() for c in carburant_r.split(",") if c.strip() and c.strip() != "indifferent"]
    if not carburant_list or carburant_r in ("indifferent", ""):
        score_carburant = p_carburant
    elif not carburant_a:
        score_carburant = round(p_carburant * 0.40, 1)  # inconnu : score partiel
    elif any(
        carburant_a == c or (c == "hybride" and carburant_a.startswith("hybride"))
        for c in carburant_list
    ):
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
        score_vendeur = -3
    detail["vendeur"] = {"score": score_vendeur, "max": 0}

    # ── Couleur (impératif uniquement) ────────────────────────────────────────
    couleur_list = [c.strip() for c in couleur_r.split(",") if c.strip()]
    couleur_a = (annonce.get("couleur") or "").lower()
    if couleur_imperatif and couleur_list:
        if any(c in couleur_a for c in couleur_list):
            malus_couleur = 0    # bonne couleur confirmée
        elif not couleur_a:
            malus_couleur = -5   # couleur non récupérable (page détail inaccessible)
        else:
            malus_couleur = -40  # mauvaise couleur (ne devrait pas passer le filtre)
    else:
        malus_couleur = 0
    detail["couleur"] = {"score": malus_couleur, "max": 0}

    # ── Carrosserie ───────────────────────────────────────────────────────────
    carrosserie_list = [c.strip() for c in carrosserie_r.split(",") if c.strip()]
    if not carrosserie_list:
        score_carrosserie = 0
    elif not carrosserie_a:
        score_carrosserie = 0
    elif carrosserie_a in carrosserie_list:
        score_carrosserie = 3
    else:
        score_carrosserie = -5
    detail["carrosserie"] = {"score": score_carrosserie, "max": 3}

    # ── Options / mots-clés ───────────────────────────────────────────────────
    mots_cles = [m.strip().lower() for m in options_r.split(",") if m.strip()]
    imperatives = [m.strip().lower() for m in options_imp_r.split(",") if m.strip()]
    # Matériaux et couleur intérieure : ajoutés comme mots-clés bonus dans options_texte
    mat_list = [m.strip().lower() for m in materiaux_r.split(",") if m.strip()]
    col_int_list = [c.strip().lower() for c in couleur_int_r.split(",") if c.strip()]
    mots_cles_bonus = mat_list + col_int_list
    if not mots_cles:
        bonus_options = p_options
        malus_imperatives = 0
    else:
        trouves = sum(1 for m in mots_cles if m in options_a)
        ratio = trouves / len(mots_cles)
        bonus_options = round(p_options * ratio, 1)
        manquantes = [m for m in imperatives if m not in options_a]
        malus_imperatives = len(manquantes) * -12
        if manquantes and not raison_rejet:
            raison_rejet = f"Option(s) impérative(s) manquante(s) : {', '.join(manquantes)}"
    # Petit bonus si matériaux/couleur intérieure trouvés dans l'annonce
    bonus_extra = sum(2 for m in mots_cles_bonus if m in options_a)
    detail["options"] = {"score": bonus_options + malus_imperatives + bonus_extra, "max": p_options}

    # ── Pénalité champs critiques manquants ────────────────────────────────────
    # Prix, km et année manquants sont déjà pénalisés ci-dessus via leur score.
    # On ajoute une pénalité supplémentaire légère pour souligner le manque d'info.
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
        # Pour chaque mot de finition, chercher aussi ses aliases (termes allemands équivalents)
        termes = []
        for m in mots_finition:
            termes.extend(FINITION_ALIASES.get(m, [m]))
        finition_trouvee = any(t in titre_a or t in options_a for t in termes)
        bonus_finition = 5 if finition_trouvee else 0
        if not finition_trouvee and finition_imperatif and not raison_rejet:
            raison_rejet = f"Finition '{finition_r}' non trouvée dans l'annonce"
    else:
        bonus_finition = 0
    detail["finition"] = {"score": bonus_finition, "max": 5}

    # ── Risque inondation ──────────────────────────────────────────────────────
    ville_a = (annonce.get("ville") or "").lower().strip()
    zone_inondable = bool(ville_a and any(z in ville_a for z in ZONES_INONDATION))
    malus_inondation = -8 if zone_inondable else 0
    detail["inondation"] = {"score": malus_inondation, "max": 0, "risque": zone_inondable}

    # ── Score final ────────────────────────────────────────────────────────────
    score_brut = (
        score_prix + score_km + score_annee + bonus_km_an
        + score_boite + score_carburant + score_vendeur
        + bonus_options - penalite + bonus_fraicheur + malus_inondation + malus_couleur
        + score_carrosserie + bonus_finition
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
