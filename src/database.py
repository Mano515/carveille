import sqlite3
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "db", "carveille.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id   TEXT PRIMARY KEY,
            nom         TEXT NOT NULL,
            contact     TEXT,
            notes       TEXT,
            statut      TEXT DEFAULT 'actif',
            created_at  TEXT,
            updated_at  TEXT
        );

        CREATE TABLE IF NOT EXISTS recherches (
            search_id TEXT PRIMARY KEY,
            client_id TEXT REFERENCES clients(client_id),
            nom_recherche TEXT,
            statut TEXT DEFAULT 'active',
            marque TEXT,
            modele TEXT,
            budget_max REAL,
            budget_strict INTEGER DEFAULT 0,
            km_max REAL,
            annee_min INTEGER,
            boite TEXT DEFAULT 'indifferent',
            carburant TEXT DEFAULT 'indifferent',
            vendeur_filtre TEXT DEFAULT 'indifferent',
            options_recherchees TEXT,
            mobile_de_url TEXT,
            poids_prix REAL DEFAULT 30,
            poids_km REAL DEFAULT 25,
            poids_annee REAL DEFAULT 20,
            poids_boite REAL DEFAULT 10,
            poids_carburant REAL DEFAULT 10,
            poids_options REAL DEFAULT 5,
            penalite_infos_manquantes REAL DEFAULT 10,
            score_min_notification REAL DEFAULT 60,
            max_annonces INTEGER DEFAULT 3,
            created_at TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS annonces_vues (
            seen_id TEXT PRIMARY KEY,
            search_id TEXT,
            listing_id TEXT,
            url TEXT,
            titre TEXT,
            prix REAL,
            prix_initial REAL,        -- premier prix constaté, jamais modifié
            baisse_prix REAL DEFAULT 0, -- écart entre prix_initial et prix actuel
            km REAL,
            annee INTEGER,
            date_immat TEXT,           -- format YYYY-MM (plus précis que annee)
            boite TEXT,
            carburant TEXT,
            couleur TEXT,
            vendeur_type TEXT,
            ville TEXT,
            image_url TEXT,
            options_texte TEXT,
            date_publication TEXT,
            score REAL,
            score_detail TEXT,         -- JSON du détail par critère
            raison_rejet TEXT,
            interet TEXT,              -- NULL | 'oui' | 'non' (marquage manuel)
            est_nouvelle INTEGER DEFAULT 1,  -- 1 = jamais notifiée
            deja_notifiee INTEGER DEFAULT 0,
            date_premiere_vue TEXT,
            date_derniere_vue TEXT,
            UNIQUE(search_id, listing_id)
        );

        CREATE TABLE IF NOT EXISTS historique_prix (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            search_id TEXT,
            listing_id TEXT,
            prix REAL,
            date_constatee TEXT
        );

        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            ended_at TEXT,
            statut TEXT,
            nb_annonces_lues INTEGER DEFAULT 0,
            nb_annonces_nouvelles INTEGER DEFAULT 0,
            nb_annonces_notifiees INTEGER DEFAULT 0
        );
        """)
    # Migration : ajouter client_id à recherches si la table existait déjà sans cette colonne
    with get_conn() as conn:
        try:
            conn.execute("ALTER TABLE recherches ADD COLUMN client_id TEXT REFERENCES clients(client_id)")
        except Exception:
            pass  # colonne déjà présente

    print("[OK] Base de donnees initialisee.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_recherches_actives() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM recherches WHERE statut = 'active'").fetchall()
    return [dict(r) for r in rows]


def get_recherche_by_id(search_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM recherches WHERE search_id = ?", (search_id,)).fetchone()
    return dict(row) if row else None


# ── Clients ─────────────────────────────────────────────────────────────────────

def insert_client(data: dict):
    now = _now()
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO clients (client_id, nom, contact, notes, statut, created_at, updated_at)
            VALUES (:client_id, :nom, :contact, :notes, 'actif', :now, :now)
        """, {**data, "now": now})


def get_clients(statut: str = "actif") -> list[dict]:
    """Retourne les clients avec leurs recherches (+ stats annonces) et le nombre de favoris."""
    with get_conn() as conn:
        clients = [dict(r) for r in conn.execute(
            "SELECT * FROM clients WHERE statut=? ORDER BY nom COLLATE NOCASE",
            (statut,)
        ).fetchall()]
        for c in clients:
            c["recherches"] = [dict(r) for r in conn.execute("""
                SELECT r.*,
                       COUNT(av.seen_id) AS nb_annonces,
                       MAX(av.date_premiere_vue) AS derniere_annonce
                FROM recherches r
                LEFT JOIN annonces_vues av ON av.search_id = r.search_id
                    AND (av.interet IS NULL OR av.interet != 'non')
                WHERE r.client_id = ? AND r.statut = 'active'
                GROUP BY r.search_id
                ORDER BY r.nom_recherche
            """, (c["client_id"],)).fetchall()]
            c["nb_retenues"] = conn.execute("""
                SELECT COUNT(*) FROM annonces_vues av
                JOIN recherches r ON av.search_id = r.search_id
                WHERE r.client_id = ? AND av.interet = 'oui'
            """, (c["client_id"],)).fetchone()[0]
    return clients


def get_client_by_id(client_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM clients WHERE client_id=?", (client_id,)).fetchone()
    return dict(row) if row else None


def archiver_client(client_id: str):
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "UPDATE clients SET statut='archive', updated_at=? WHERE client_id=?",
            (now, client_id)
        )


def reactiver_client(client_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE clients SET statut='actif', updated_at=? WHERE client_id=?",
            (_now(), client_id)
        )


def desactiver_recherche(search_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE recherches SET statut='inactive', updated_at=? WHERE search_id=?",
            (_now(), search_id)
        )


def rattacher_recherche_client(search_id: str, client_id):
    """Rattache (ou détache si client_id=None) une recherche à un client."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE recherches SET client_id=?, updated_at=? WHERE search_id=?",
            (client_id or None, _now(), search_id)
        )


def get_derniers_runs(limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_resume_hebdo() -> list[dict]:
    """Stats de la semaine écoulée pour chaque client actif."""
    from datetime import timedelta
    semaine_debut = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    with get_conn() as conn:
        clients = [dict(r) for r in conn.execute(
            "SELECT * FROM clients WHERE statut='actif' ORDER BY nom"
        ).fetchall()]
        for c in clients:
            c["nb_annonces_semaine"] = conn.execute("""
                SELECT COUNT(*) FROM annonces_vues av
                JOIN recherches r ON av.search_id = r.search_id
                WHERE r.client_id = ? AND av.date_premiere_vue >= ?
            """, (c["client_id"], semaine_debut)).fetchone()[0]
            c["nb_retenues_total"] = conn.execute("""
                SELECT COUNT(*) FROM annonces_vues av
                JOIN recherches r ON av.search_id = r.search_id
                WHERE r.client_id = ? AND av.interet = 'oui'
            """, (c["client_id"],)).fetchone()[0]
    return clients


def get_historique_client(client_id: str) -> list[dict]:
    """Annonces marquées 'intéressé' sur toutes les recherches de ce client, triées par score."""
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT av.*, r.nom_recherche
            FROM annonces_vues av
            JOIN recherches r ON av.search_id = r.search_id
            WHERE r.client_id = ? AND av.interet = 'oui'
            ORDER BY av.score DESC, av.date_premiere_vue DESC
        """, (client_id,)).fetchall()
    return [dict(r) for r in rows]


def get_recherches_sans_client() -> list[dict]:
    """Recherches non rattachées à un client."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM recherches WHERE (client_id IS NULL OR client_id='') AND statut='active'"
        ).fetchall()
    return [dict(r) for r in rows]


def insert_recherche(data: dict):
    now = _now()
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO recherches (
                search_id, nom_recherche, statut, marque, modele,
                budget_max, budget_strict, km_max, annee_min,
                boite, carburant, vendeur_filtre, options_recherchees, mobile_de_url,
                poids_prix, poids_km, poids_annee, poids_boite, poids_carburant, poids_options,
                penalite_infos_manquantes, score_min_notification, max_annonces,
                created_at, updated_at
            ) VALUES (
                :search_id, :nom_recherche, :statut, :marque, :modele,
                :budget_max, :budget_strict, :km_max, :annee_min,
                :boite, :carburant, :vendeur_filtre, :options_recherchees, :mobile_de_url,
                :poids_prix, :poids_km, :poids_annee, :poids_boite, :poids_carburant, :poids_options,
                :penalite_infos_manquantes, :score_min_notification, :max_annonces,
                :created_at, :updated_at
            )
        """, {**data, "created_at": now, "updated_at": now})


def upsert_annonce(annonce_data: dict) -> tuple[bool, bool]:
    """
    Insère ou met à jour une annonce.
    Retourne (est_nouvelle, baisse_prix_detectee).

    La détection de baisse compare le nouveau prix au dernier prix connu.
    prix_initial est figé à la première insertion et ne change jamais.
    """
    now = _now()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT seen_id, prix, prix_initial FROM annonces_vues WHERE search_id=? AND listing_id=?",
            (annonce_data["search_id"], annonce_data["listing_id"]),
        ).fetchone()

        if existing:
            nouveau_prix = annonce_data.get("prix")
            ancien_prix = existing["prix"]
            prix_initial = existing["prix_initial"] or ancien_prix

            baisse = 0.0
            if nouveau_prix and ancien_prix and nouveau_prix < ancien_prix:
                baisse = round(ancien_prix - nouveau_prix, 2)

            conn.execute("""
                UPDATE annonces_vues SET
                    prix=:prix, km=:km, score=:score, score_detail=:score_detail,
                    raison_rejet=:raison_rejet, est_nouvelle=:est_nouvelle,
                    date_derniere_vue=:now,
                    baisse_prix=CASE WHEN :baisse > 0 THEN :baisse ELSE baisse_prix END,
                    prix_initial=CASE WHEN prix_initial IS NULL THEN :prix_initial ELSE prix_initial END
                WHERE seen_id=:seen_id
            """, {
                **annonce_data, "now": now,
                "seen_id": existing["seen_id"],
                "baisse": baisse,
                "prix_initial": prix_initial,
            })

            if baisse > 0:
                conn.execute(
                    "INSERT INTO historique_prix (search_id, listing_id, prix, date_constatee) VALUES (?,?,?,?)",
                    (annonce_data["search_id"], annonce_data["listing_id"], nouveau_prix, now),
                )

            return False, baisse > 0

        # Première insertion : prix_initial = prix courant
        prix = annonce_data.get("prix")
        conn.execute("""
            INSERT INTO annonces_vues (
                seen_id, search_id, listing_id, url, titre,
                prix, prix_initial, baisse_prix,
                km, annee, date_immat, boite, carburant, couleur,
                vendeur_type, ville, image_url, options_texte, date_publication,
                score, score_detail, raison_rejet, interet,
                est_nouvelle, deja_notifiee,
                date_premiere_vue, date_derniere_vue
            ) VALUES (
                :seen_id, :search_id, :listing_id, :url, :titre,
                :prix, :prix, 0,
                :km, :annee, :date_immat, :boite, :carburant, :couleur,
                :vendeur_type, :ville, :image_url, :options_texte, :date_publication,
                :score, :score_detail, :raison_rejet, NULL,
                :est_nouvelle, 0,
                :now, :now
            )
        """, {**annonce_data, "now": now})

        if prix:
            conn.execute(
                "INSERT INTO historique_prix (search_id, listing_id, prix, date_constatee) VALUES (?,?,?,?)",
                (annonce_data["search_id"], annonce_data["listing_id"], prix, now),
            )

        return True, False


def marquer_notifiee(seen_id: str):
    with get_conn() as conn:
        conn.execute("UPDATE annonces_vues SET deja_notifiee=1 WHERE seen_id=?", (seen_id,))


def marquer_interet(seen_id: str, interet: str | None):
    with get_conn() as conn:
        conn.execute("UPDATE annonces_vues SET interet=? WHERE seen_id=?", (interet, seen_id))


def save_run(run_data: dict):
    with get_conn() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO runs (
                run_id, started_at, ended_at, statut,
                nb_annonces_lues, nb_annonces_nouvelles, nb_annonces_notifiees
            ) VALUES (
                :run_id, :started_at, :ended_at, :statut,
                :nb_annonces_lues, :nb_annonces_nouvelles, :nb_annonces_notifiees
            )
        """, run_data)


def get_derniers_resultats(search_id: str, limit: int = 20) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT * FROM annonces_vues
            WHERE search_id=? AND (interet IS NULL OR interet != 'non')
            ORDER BY date_premiere_vue DESC
            LIMIT ?
        """, (search_id, limit)).fetchall()
    return [dict(r) for r in rows]


def get_historique_prix(search_id: str, listing_id: str) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT prix, date_constatee FROM historique_prix
            WHERE search_id=? AND listing_id=?
            ORDER BY date_constatee ASC
        """, (search_id, listing_id)).fetchall()
    return [dict(r) for r in rows]
