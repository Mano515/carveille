"""
Tests automatisés Carveille — python test.py

Vérifie les comportements clés sans framework externe :
  1. Scoring — les annonces reçoivent les bons scores
  2. Filtres — budget strict, boite, carburant bloquent correctement
  3. Pénalités — champs manquants font baisser le score
  4. Sélection top annonces
  5. Anti-doublon — une annonce déjà vue n'est pas recomptée comme nouvelle
  6. Baisse de prix — détectée et signalée correctement
  7. Clients — création, archivage, réactivation
  8. Recherches — désactivation, rattachement à un client
  9. Historique et résumé hebdomadaire
"""

import os
import sys
import shutil
import tempfile

# Force UTF-8 sur la console Windows (évite les UnicodeEncodeError avec les flèches/accents)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Isolation : base de données temporaire pour les tests ──────────────────────
_tmp_dir = tempfile.mkdtemp()
_db_test = os.path.join(_tmp_dir, "test.db")

import src.database as _db_module
_db_module.DB_PATH = _db_test  # redirige toutes les fonctions BDD vers le fichier temp
# ───────────────────────────────────────────────────────────────────────────────

from src.database import (
    init_db, insert_recherche, upsert_annonce, get_conn,
    insert_client, get_client_by_id, get_clients,
    archiver_client, reactiver_client,
    desactiver_recherche, rattacher_recherche_client,
    get_derniers_runs, save_run, get_historique_client,
    get_recherches_sans_client, get_resume_hebdo,
)
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
    "client_id": None,
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
ANN_PRIX_BAISSE        = {**ANN_PARFAITE, "listing_id": "ann_007", "prix": 17500}
ANN_PRIX_BAISSE_APRES  = {**ANN_PRIX_BAISSE, "prix": 16000}


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

res_souple = scorer_annonce({**ANN_PARFAITE, "prix": 20500}, RECHERCHE)
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

ann_limite = {**ANN_PARFAITE, "annee": 2017, "date_immat": "2017-06"}
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

ann_vide = {**ANN_PARFAITE, "listing_id": "ann_vide",
            "prix": None, "km": None, "annee": None, "boite": None, "carburant": None}
res_vide = scorer_annonce(ann_vide, RECHERCHE)
check("Pénalité plafonnée à 30 même si tout manque",
      res_vide["detail"]["penalite"]["score"] >= -30)


# ════════════════════════════════════════════════════════════════════════════════
print("\n[5] Sélection top annonces")
# ════════════════════════════════════════════════════════════════════════════════

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
    check("Top trié par score décroissant", top[0]["score"] >= top[-1]["score"])


# ════════════════════════════════════════════════════════════════════════════════
print("\n[6] Anti-doublon")
# ════════════════════════════════════════════════════════════════════════════════

init_db()
insert_recherche(RECHERCHE)

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
upsert_annonce({
    **ANN_PRIX_BAISSE, "search_id": "test_bmw", "seen_id": "seen-007",
    "score": r["score"], "score_detail": "{}", "raison_rejet": None, "est_nouvelle": 1,
})

r2 = scorer_annonce(ANN_PRIX_BAISSE_APRES, RECHERCHE)
_, baisse_detectee = upsert_annonce({
    **ANN_PRIX_BAISSE_APRES, "search_id": "test_bmw", "seen_id": "",
    "score": r2["score"], "score_detail": "{}", "raison_rejet": None, "est_nouvelle": 0,
})

check("Baisse de prix détectée", baisse_detectee)

conn = get_conn()
row = conn.execute(
    "SELECT prix_initial, prix, baisse_prix FROM annonces_vues WHERE listing_id='ann_007'"
).fetchone()
conn.close()
check("prix_initial conservé (premier prix jamais modifié)", row["prix_initial"] == 17500)
check("Montant baisse_prix correct (1500 EUR)", row["baisse_prix"] == 1500,
      f"obtenu : {row['baisse_prix']}")

_, pas_de_baisse = upsert_annonce({
    **ANN_PRIX_BAISSE_APRES, "search_id": "test_bmw", "seen_id": "",
    "score": r2["score"], "score_detail": "{}", "raison_rejet": None, "est_nouvelle": 0,
})
check("Prix stable → pas de fausse détection de baisse", not pas_de_baisse)


# ════════════════════════════════════════════════════════════════════════════════
print("\n[8] Clients — création, archivage, réactivation")
# ════════════════════════════════════════════════════════════════════════════════

CLIENT_A = {"client_id": "cli_001", "nom": "Dupont Jean", "contact": "06 12 34 56 78", "notes": "Budget serré"}
CLIENT_B = {"client_id": "cli_002", "nom": "Martin Paul", "contact": "", "notes": ""}

insert_client(CLIENT_A)
insert_client(CLIENT_B)

c = get_client_by_id("cli_001")
check("get_client_by_id retourne le bon client", c is not None and c["nom"] == "Dupont Jean")
check("Client créé avec statut actif", c["statut"] == "actif")

clients_actifs = get_clients("actif")
noms = [c["nom"] for c in clients_actifs]
check("get_clients retourne les deux clients actifs", "Dupont Jean" in noms and "Martin Paul" in noms)

archiver_client("cli_001")
c_archive = get_client_by_id("cli_001")
check("archiver_client passe le client en archive", c_archive["statut"] == "archive")

actifs_apres = get_clients("actif")
check("Client archivé absent des actifs", not any(c["client_id"] == "cli_001" for c in actifs_apres))

archives = get_clients("archive")
check("Client archivé présent dans get_clients('archive')", any(c["client_id"] == "cli_001" for c in archives))

reactiver_client("cli_001")
c_reactif = get_client_by_id("cli_001")
check("reactiver_client repasse le client en actif", c_reactif["statut"] == "actif")


# ════════════════════════════════════════════════════════════════════════════════
print("\n[9] Recherches — désactivation et rattachement client")
# ════════════════════════════════════════════════════════════════════════════════

RECHERCHE_2 = {**RECHERCHE, "search_id": "test_peugeot", "nom_recherche": "Peugeot Test",
               "client_id": None}
insert_recherche(RECHERCHE_2)

sans_client = get_recherches_sans_client()
check("Recherche sans client_id apparaît dans get_recherches_sans_client",
      any(r["search_id"] == "test_peugeot" for r in sans_client))

rattacher_recherche_client("test_peugeot", "cli_002")
sans_apres = get_recherches_sans_client()
check("Après rattachement, recherche absente de sans_client",
      not any(r["search_id"] == "test_peugeot" for r in sans_apres))

clients_avec_recherches = get_clients("actif")
martin = next((c for c in clients_avec_recherches if c["client_id"] == "cli_002"), None)
check("Recherche rattachée visible dans get_clients pour Martin Paul",
      martin is not None and any(r["search_id"] == "test_peugeot" for r in martin["recherches"]))

desactiver_recherche("test_peugeot")
conn = get_conn()
row = conn.execute("SELECT statut FROM recherches WHERE search_id='test_peugeot'").fetchone()
conn.close()
check("desactiver_recherche passe la recherche en inactive", row["statut"] == "inactive")

martin_apres = next((c for c in get_clients("actif") if c["client_id"] == "cli_002"), None)
check("Recherche inactive absente des recherches actives du client",
      martin_apres is not None and not any(r["search_id"] == "test_peugeot" for r in martin_apres["recherches"]))


# ════════════════════════════════════════════════════════════════════════════════
print("\n[10] Historique runs et résumé hebdomadaire")
# ════════════════════════════════════════════════════════════════════════════════

import uuid
from datetime import datetime, timezone

save_run({
    "run_id": str(uuid.uuid4()),
    "started_at": datetime.now(timezone.utc).isoformat(),
    "ended_at": datetime.now(timezone.utc).isoformat(),
    "statut": "ok",
    "nb_annonces_lues": 10,
    "nb_annonces_nouvelles": 3,
    "nb_annonces_notifiees": 2,
})

runs = get_derniers_runs(5)
check("get_derniers_runs retourne au moins un run", len(runs) >= 1)
check("Run enregistré avec le bon statut", runs[0]["statut"] == "ok")
check("Run enregistré avec le bon nombre d'annonces lues", runs[0]["nb_annonces_lues"] == 10)

resume = get_resume_hebdo()
check("get_resume_hebdo retourne une liste", isinstance(resume, list))
check("Résumé contient les clients actifs",
      any(c["client_id"] == "cli_001" for c in resume))
check("Résumé contient nb_annonces_semaine pour chaque client",
      all("nb_annonces_semaine" in c for c in resume))


# ════════════════════════════════════════════════════════════════════════════════
print("\n[11] Nettoyage + bilan")
# ════════════════════════════════════════════════════════════════════════════════

shutil.rmtree(_tmp_dir, ignore_errors=True)

total = PASS + FAIL
print(f"\n{'='*40}")
print(f"  {PASS}/{total} tests passés")
if FAIL:
    print(f"  {FAIL} ECHEC(S)")
print(f"{'='*40}\n")
sys.exit(0 if FAIL == 0 else 1)
