import json
import uuid
from datetime import datetime, timezone

from src.database import (
    get_recherches_actives, upsert_annonce, save_run,
    marquer_notifiee, get_conn,
)
from src.scoring import scorer_annonce, selectionner_top_annonces
from src.dedup import filtrer_nouvelles_annonces
from src.notifier import notifier_global


def _charger_annonces(source: str, recherche: dict, day: int = 1) -> list:
    if source == "mobile.de":
        from src.sources.mobile_de import charger
        return charger(recherche)
    from src.sources.mock import charger
    return charger(recherche, day=day)


def _ouvrir_session_scraping(source: str):
    """Lance Chrome une fois avant la boucle de recherches (mobile.de uniquement)."""
    if source == "mobile.de":
        from src.sources.mobile_de import ouvrir_session
        ouvrir_session()


def _fermer_session_scraping(source: str):
    """Ferme Chrome après la boucle de recherches."""
    if source == "mobile.de":
        from src.sources.mobile_de import fermer_session
        fermer_session()


def _dedup_liste_interne(annonces: list) -> list:
    """Supprime les doublons au sein d'un même fichier/réponse (même listing_id)."""
    seen = set()
    result = []
    for a in annonces:
        lid = a.get("listing_id")
        if lid not in seen:
            seen.add(lid)
            result.append(a)
    return result


def _enrichir(ann: dict, search_id: str, res: dict, est_nouvelle: bool) -> dict:
    """Fusionne une annonce brute avec son score et les métadonnées nécessaires à la BDD."""
    return {
        **ann,
        "search_id": search_id,
        # seen_id vide pour les annonces déjà vues : upsert_annonce les retrouve
        # par (search_id, listing_id) et ignore cette valeur.
        "seen_id": str(uuid.uuid4()) if est_nouvelle else "",
        "score": res["score"],
        "score_detail": json.dumps(res["detail"], ensure_ascii=False),
        "raison_rejet": res["raison_rejet"],
        # est_nouvelle=1 → sera notifiée si score suffisant
        # est_nouvelle=0 → mise à jour silencieuse (sauf baisse de prix)
        "est_nouvelle": 1 if est_nouvelle else 0,
    }


def run(source: str = "mock", day: int = 1, notify_nouvelles: bool = True, notify_baisses: bool = True, search_id: str = None):
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).isoformat()
    cible = f"search_id={search_id[:8]}" if search_id else "toutes"
    print(f"\n[RUN] Run {run_id[:8]} demarre ({source} / {cible})")

    toutes = get_recherches_actives()
    if search_id:
        recherches = [r for r in toutes if r["search_id"] == search_id]
        if not recherches:
            print(f"[WARN] Recherche {search_id[:8]} introuvable ou inactive.")
            return
    else:
        recherches = toutes
    if not recherches:
        print("[WARN] Aucune recherche active trouvee.")
        return

    total_lues = total_nouvelles = total_notifiees = 0
    # Résultats à notifier : liste de (recherche, annonces) pour les recherches avec notifications activées
    a_notifier_global = []

    # Ouvrir le navigateur une seule fois pour toutes les recherches du run
    _ouvrir_session_scraping(source)
    try:
        for recherche in recherches:
            sid = recherche["search_id"]
            nom = recherche.get("nom_recherche", sid)
            print(f"\n[--] Recherche : {nom}")

            try:
                # 1. Charger et dédoublonner les annonces de la source
                annonces_brutes = _dedup_liste_interne(_charger_annonces(source, recherche, day))
                total_lues += len(annonces_brutes)
                print(f"  -> {len(annonces_brutes)} annonces chargees")

                # 2. Séparer nouvelles vs déjà vues (une seule requête SQL)
                conn = get_conn()
                nouvelles = filtrer_nouvelles_annonces(annonces_brutes, sid, conn)
                conn.close()
                ids_nouvelles = {a["listing_id"] for a in nouvelles}
                deja_vues = [a for a in annonces_brutes if a["listing_id"] not in ids_nouvelles]
                print(f"  -> {len(nouvelles)} nouvelles, {len(deja_vues)} deja vues")
                total_nouvelles += len(nouvelles)

                # 3. Scorer + enregistrer les nouvelles annonces
                annonces_scorees = []
                for ann in nouvelles:
                    enrichie = _enrichir(ann, sid, scorer_annonce(ann, recherche), est_nouvelle=True)
                    upsert_annonce(enrichie)
                    if not enrichie.get("raison_rejet") or "impérative" not in enrichie["raison_rejet"]:
                        annonces_scorees.append(enrichie)

                # 4. Mettre à jour les annonces déjà vues et détecter les baisses de prix
                baisses = []
                for ann in deja_vues:
                    enrichie = _enrichir(ann, sid, scorer_annonce(ann, recherche), est_nouvelle=False)
                    _, baisse_detectee = upsert_annonce(enrichie)
                    if baisse_detectee:
                        conn2 = get_conn()
                        row = conn2.execute(
                            "SELECT baisse_prix FROM annonces_vues WHERE search_id=? AND listing_id=?",
                            (sid, ann["listing_id"]),
                        ).fetchone()
                        conn2.close()
                        baisses.append({**enrichie, "baisse_prix": row["baisse_prix"] if row else 0})

                if baisses:
                    print(f"  -> {len(baisses)} baisse(s) de prix detectee(s) !")

                # 5. Préparer les annonces à notifier pour cette recherche
                top = selectionner_top_annonces(annonces_scorees, recherche)
                candidats = (top if notify_nouvelles else []) + (baisses if notify_baisses else [])
                print(f"  -> {len(candidats)} annonce(s) candidate(s) a la notification")

                if candidats:
                    for ann in top:
                        marquer_notifiee(ann["seen_id"])
                    total_notifiees += len(candidats)
                    # N'envoyer l'email que si la recherche a les notifications activées
                    if recherche.get("notifications_actives"):
                        a_notifier_global.append((recherche, candidats))

            except Exception as e:
                import traceback
                print(f"  [ERR] Recherche '{nom}' échouée : {type(e).__name__}: {e}")
                traceback.print_exc()
                print("  [INFO] Passage à la recherche suivante...")

    finally:
        _fermer_session_scraping(source)

    # 6. Envoyer UN seul email groupé si des notifications sont en attente
    if a_notifier_global:
        notifier_global(a_notifier_global)

    # 7. Sauvegarder le bilan du run
    save_run({
        "run_id": run_id,
        "started_at": started_at,
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "statut": "ok",
        "nb_annonces_lues": total_lues,
        "nb_annonces_nouvelles": total_nouvelles,
        "nb_annonces_notifiees": total_notifiees,
    })

    print(f"\n[OK] Run termine -- {total_lues} lues, {total_nouvelles} nouvelles, {total_notifiees} notifiees.")
