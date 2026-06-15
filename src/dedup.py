def filtrer_nouvelles_annonces(annonces: list, search_id: str, db_conn) -> list:
    """Retourne uniquement les annonces jamais vues pour cette recherche.

    Utilise une seule requête IN plutôt qu'une requête par annonce.
    """
    if not annonces:
        return []

    ids = [a["listing_id"] for a in annonces]
    placeholders = ",".join("?" * len(ids))
    deja_vus = {
        row[0]
        for row in db_conn.execute(
            f"SELECT listing_id FROM annonces_vues WHERE search_id=? AND listing_id IN ({placeholders})",
            [search_id, *ids],
        )
    }
    return [a for a in annonces if a["listing_id"] not in deja_vus]
