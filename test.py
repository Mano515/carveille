"""
Tests automatisés Carveille — python test.py

Vérifie les 5 comportements clés sans framework externe :
  1. Scoring — les annonces reçoivent les bons scores
  2. Filtres — budget strict, boite, carburant bloquent correctement
  3. Pénalités — champs manquants font baisser le score
  4. Anti-doublon — une annonce déjà vue n'est pas recomptée comme nouvelle
  5. Baisse de prix — détectée et signalée correctement
"""

import os
import sys
import shutil
import tempfile

# ── Isolation : base de données temporaire pour les tests ──────────────────────
_tmp_dir = tempfile.mkdtemp()
_db_test = os.path.join(_tmp_dir, "test.db")

import src.database as _db_module
_db_module.DB_PATH = _db_test  # redirige toutes les fonctions BDD vers le fichier temp
# ───────────────────────────────────────────────────────────────────────────────

from src.database import init_db, insert_recherche, upsert_annonce, get_conn
from src.scoring import scorer_annonce, selectionner_top_annonces
from src.dedup import filtrer_nouvelles_annonces

PASS = 0
FAIL = 0


def check(nom: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        print(f"  [PASS] {nom}")
        PASS += 1
    else:
        print(f"  [FAIL] {nom}" + (f" — {detail}" if detail else ""))
        FAIL += 1


# ── Données de base ─────────────────────────────────────────────────────────────

RECHERCHE = {
    "search_id": "test_bmw",
    "nom_recherche": "BMW Test",
    "statut": "active",
    "marque": "BMW", "modele": "Serie 1",
    "budget_max": 20000, "budget_strict": 0,
    "km_max": 100000, "annee_min": 2018,
    "boite": "auto", "carburant": "diesel",
    "vendeur_filtre": "indifferent",
    "options_recherchees": "camera,gps",
    "mobile_de_url": None,
    "poids_prix": 30, "poids_km": 25, "poids_annee": 20,
    "poids_boite": 10, "poids_carburant": 10, "poids_options": 5,
    "penalite_infos_manquantes": 10,
    "score_min_notification": 60, "max_annonces": 3,
}

ANN_PARFAITE = {
    "listing_id": "ann_001",
    "url": "https://example.com/001",
    "titre": "BMW 116d 2019 Auto",
    "prix": 17000, "km": 70000, "annee": 2019, "date_immat": "2019-06",
    "boite": "auto", "carburant": "diesel", "couleur": "noir",
    "vendeur_type": "pro", "ville": "Lyon",
    "image_url": None, "options_texte": "camera, gps",
    "date_publication": None,
}

ANN_HORS_BUDGET_STRICT = {**ANN_PARFAITE, "listing_id": "ann_002", "prix": 22000}
ANN_MAUVAISE_BOITE     = {**ANN_PARFAITE, "listing_id": "ann_003", "boite": "manuelle"}
ANN_MAUVAIS_CARBURANT  = {**ANN_PARFAITE, "listing_id": "ann_004", "carburant": "essence"}
ANN_CHAMPS_MANQUANTS   = {**ANN_PARFAITE, "listing_id": "ann_005", "prix": None, "km": None, "boite": None}
ANN_TROP_ANCIENNE      = {**ANN_PARFAITE, "listing_id": "ann_006", "annee": 2015, "date_immat": "2015-01"}
ANN_PRIX_BAISSE        = {**ANN_PARFAITE, "listing_id": "ann_007", "prix": 17500}  # premier prix
ANN_PRIX_BAISSE_APRES  = {**ANN_PRIX_BAISSE, "prix": 16000}                         # prix réduit


# ════════════════════════════════════════════════════════════════════════════════
print("\n[1] Scoring — annonce idéale")
# ════════════════════════════════════════════════════════════════════════════════

res = scorer_annonce(ANN_PARFAITE, RECHERCHE)
check("Score > 90 pour une annonce qui coche toutes les cases", res["score"] > 90,
      f"score obtenu : {res['score']}")
check("Pas de raison de rejet", res["raison_rejet"] is None)
check("Détail contient toutes les clés attendues",
      all(k in res["detail"] for k in ("prix", "km", "annee", "boite", "carburant", "options")))


# ════════════════════════════════════════════════════════════════════════════════
print("\n[2] Filtres — budget strict")
# ════════════════════════════════════════════════════════════════════════════════

recherche_stricte = {**RECHERCHE, "budget_strict": 1}
res_strict = scorer_annonce(ANN_HORS_BUDGET_STRICT, recherche_stricte)
check("Budget strict : score = 0 si prix dépasse le budget",
      res_strict["detail"]["prix"]["score"] == 0)
check("Budget strict : raison de rejet renseignée",
      res_strict["raison_rejet"] is not None)

# Budget non strict : tolérance +5%
res_souple = scorer_annonce({**ANN_PARFAITE, "prix": 20500}, RECHERCHE)  # 20500 / 20000 = +2.5%
check("Budget non strict : légère tolérance autorisée (score partiel)",
      res_souple["detail"]["prix"]["score"] > 0)


# ════════════════════════════════════════════════════════════════════════════════
print("\n[3] Filtres — boite, carburant, année")
# ════════════════════════════════════════════════════════════════════════════════

res_boite = scorer_annonce(ANN_MAUVAISE_BOITE, RECHERCHE)
check("Mauvaise boite → score boite = 0", res_boite["detail"]["boite"]["score"] == 0)

res_carb = scorer_annonce(ANN_MAUVAIS_CARBURANT, RECHERCHE)
check("Mauvais carburant → score carburant = 0", res_carb["detail"]["carburant"]["score"] == 0)

res_old = scorer_annonce(ANN_TROP_ANCIENNE, RECHERCHE)
check("Annee trop ancienne → score annee = 0", res_old["detail"]["annee"]["score"] == 0)
check("Annee trop ancienne → raison de rejet renseignée", res_old["raison_rejet"] is not None)

# Tolérance 1 an : annee_min - 1 donne 50%
ann_limite = {**ANN_PARFAITE, "annee": 2017, "date_immat": "2017-06"}  # annee_min = 2018
res_limite = scorer_annonce(ann_limite, RECHERCHE)
expected = RECHERCHE["poids_annee"] * 0.5
check("Année = min-1 → 50% du poids année",
      res_limite["detail"]["annee"]["score"] == round(expected, 1),
      f"attendu {expected}, obtenu {res_limite['detail']['annee']['score']}")


# ════════════════════════════════════════════════════════════════════════════════
print("\n[4] Pénalités — champs manquants")
# ════════════════════════════════════════════════════════════════════════════════

res_incomplet = scorer_annonce(ANN_CHAMPS_MANQUANTS, RECHERCHE)
check("Pénalité appliquée si champs manquants",
      res_incomplet["detail"]["penalite"]["score"] < 0)
check("Score global réduit par les pénalités",
      res_incomplet["score"] < res["score"])

# Annonce avec tout manquant : pénalité plafonnée à PENALITE_MAX
ann_vide = {**ANN_PARFAITE, "listing_id": "ann_vide",
            "prix": None, "km": None, "annee": None, "boite": None, "carburant": None}
res_vide = scorer_annonce(ann_vide, RECHERCHE)
check("Pénalité plafonnée à 30 même si tout manque",
      res_vide["detail"]["penalite"]["score"] >= -30)


# ════════════════════════════════════════════════════════════════════════════════
print("\n[5] Sélection top annonces")
# ════════════════════════════════════════════════════════════════════════════════

annonces = [
    {**scorer_annonce(ANN_PARFAITE, RECHERCHE), **ANN_PARFAITE, "search_id": "test"},
    {**scorer_annonce(ANN_MAUVAISE_BOITE, RECHERCHE), **ANN_MAUVAISE_BOITE, "search_id": "test"},
    {**scorer_annonce(ANN_TROP_ANCIENNE, RECHERCHE), **ANN_TROP_ANCIENNE, "search_id": "test"},
]
# Aplatir : scorer retourne {score, detail, raison_rejet}, on fusionne avec l'annonce
annonces_scorees = []
for ann in [ANN_PARFAITE, ANN_MAUVAISE_BOITE, ANN_TROP_ANCIENNE]:
    r = scorer_annonce(ann, RECHERCHE)
    annonces_scorees.append({**ann, "score": r["score"], "search_id": "test",
                              "date_publication": ann.get("date_publication")})

top = selectionner_top_annonces(annonces_scorees, RECHERCHE)
check("Top retourne au plus max_annonces résultats", len(top) <= RECHERCHE["max_annonces"])
check("Top ne contient que des annonces au-dessus du seuil",
      all(a["score"] >= RECHERCHE["score_min_notification"] for a in top))
if top:
    check("Top trié par score décroissant",
          top[0]["score"] >= top[-1]["score"])


# ════════════════════════════════════════════════════════════════════════════════
print("\n[6] Anti-doublon")
# ════════════════════════════════════════════════════════════════════════════════

init_db()
insert_recherche(RECHERCHE)

# Simuler un premier run : ann_001 est vue
r = scorer_annonce(ANN_PARFAITE, RECHERCHE)
upsert_annonce({
    **ANN_PARFAITE, "search_id": "test_bmw", "seen_id": "seen-001",
    "score": r["score"], "score_detail": "{}", "raison_rejet": None, "est_nouvelle": 1,
})

conn = get_conn()
nouvelles = filtrer_nouvelles_annonces([ANN_PARFAITE, ANN_MAUVAISE_BOITE], "test_bmw", conn)
conn.close()

check("Annonce déjà vue exclue des nouvelles", len(nouvelles) == 1)
check("Annonce jamais vue incluse dans les nouvelles",
      nouvelles[0]["listing_id"] == "ann_003")


# ════════════════════════════════════════════════════════════════════════════════
print("\n[7] Détection baisse de prix")
# ════════════════════════════════════════════════════════════════════════════════

r = scorer_annonce(ANN_PRIX_BAISSE, RECHERCHE)
# Première insertion (prix 17500)
upsert_annonce({
    **ANN_PRIX_BAISSE, "search_id": "test_bmw", "seen_id": "seen-007",
    "score": r["score"], "score_detail": "{}", "raison_rejet": None, "est_nouvelle": 1,
})

# Deuxième passage : même annonce, prix baissé à 16000
r2 = scorer_annonce(ANN_PRIX_BAISSE_APRES, RECHERCHE)
_, baisse_detectee = upsert_annonce({
    **ANN_PRIX_BAISSE_APRES, "search_id": "test_bmw", "seen_id": "",
    "score": r2["score"], "score_detail": "{}", "raison_rejet": None, "est_nouvelle": 0,
})

check("Baisse de prix détectée", baisse_detectee)

# Vérifier que le montant de baisse est correct en BDD
conn = get_conn()
row = conn.execute(
    "SELECT prix_initial, prix, baisse_prix FROM annonces_vues WHERE listing_id='ann_007'"
).fetchone()
conn.close()
check("prix_initial conservé (premier prix jamais modifié)", row["prix_initial"] == 17500)
check("Montant baisse_prix correct (1500 EUR)", row["baisse_prix"] == 1500,
      f"obtenu : {row['baisse_prix']}")

# Prix stable → pas de fausse détection
_, pas_de_baisse = upsert_annonce({
    **ANN_PRIX_BAISSE_APRES, "search_id": "test_bmw", "seen_id": "",
    "score": r2["score"], "score_detail": "{}", "raison_rejet": None, "est_nouvelle": 0,
})
check("Prix stable → pas de fausse détection de baisse", not pas_de_baisse)


# ════════════════════════════════════════════════════════════════════════════════
print("\n[8] Nettoyage + bilan")
# ════════════════════════════════════════════════════════════════════════════════

shutil.rmtree(_tmp_dir, ignore_errors=True)

total = PASS + FAIL
print(f"\n{'='*40}")
print(f"  {PASS}/{total} tests passés")
if FAIL:
    print(f"  {FAIL} ECHEC(S)")
print(f"{'='*40}\n")
sys.exit(0 if FAIL == 0 else 1)
