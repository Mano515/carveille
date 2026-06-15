# Carveille

Outil de veille automatisée sur les annonces automobiles mobile.de.

Carveille scrape mobile.de selon tes critères, score chaque annonce, détecte les baisses de prix, et t'envoie une notification (Telegram, email ou console) avec seulement les meilleures.

---

## Sommaire

1. [Ce que ça fait](#ce-que-ça-fait)
2. [Prérequis](#prérequis)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Utilisation](#utilisation)
6. [Comprendre le score](#comprendre-le-score)
7. [Notifications](#notifications)
8. [Structure du projet](#structure-du-projet)
9. [Tests automatisés](#tests-automatisés)

---

## Ce que ça fait

- **Scraping mobile.de** — récupère les annonces en fonction de ta recherche (marque, modèle, budget, km, boîte, carburant…)
- **Scoring sur 100** — chaque annonce reçoit un score pondéré selon tes critères
- **Détection de baisses de prix** — si une annonce que tu as déjà vue baisse de prix, tu en es informé
- **Filtre vendeur** — pro, particulier, ou indifférent
- **Bonus fraîcheur** — les annonces très récentes (<24h, <48h, <7j) gagnent quelques points
- **Anti-doublon** — une annonce vue ne remonte pas comme nouvelle lors du run suivant
- **Interface web** — tableau de bord local pour voir les résultats, marquer l'intérêt, lancer des runs
- **Notifications** — console (défaut), Telegram, ou email SMTP

---

## Prérequis

- Python 3.11 ou plus récent
- pip

Pas de base de données externe, pas de serveur cloud — tout tourne en local avec SQLite.

---

## Installation

### 1. Cloner le projet

```bash
git clone https://github.com/VOTRE_PSEUDO/carveille.git
cd carveille
```

### 2. Créer un environnement virtuel (recommandé)

```bash
python -m venv .venv
```

Activer l'environnement :

- **Windows** : `.venv\Scripts\activate`
- **Mac / Linux** : `source .venv/bin/activate`

### 3. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 4. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Ouvre le fichier `.env` et remplis les valeurs dont tu as besoin (voir section [Notifications](#notifications)).

### 5. Initialiser la base de données

```bash
python main.py init
```

Cela crée le fichier `db/carveille.db` avec toutes les tables nécessaires.

---

## Configuration

### .env

```env
# Canal de notification : console (défaut), telegram ou email
CANAL_NOTIFICATION=console

# Telegram (si CANAL_NOTIFICATION=telegram)
TELEGRAM_BOT_TOKEN=ton_token_ici
TELEGRAM_CHAT_ID=ton_chat_id_ici

# Email SMTP (si CANAL_NOTIFICATION=email)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=ton.email@gmail.com
SMTP_PASSWORD=ton_mot_de_passe_app
SMTP_DEST=destinataire@email.com
```

### config.py

Tu peux ajuster les valeurs dans `config.py` sans toucher au reste du code :

| Paramètre | Défaut | Description |
|---|---|---|
| `POIDS_DEFAUT["prix"]` | 30 | Poids du prix dans le score |
| `POIDS_DEFAUT["km"]` | 25 | Poids du kilométrage |
| `POIDS_DEFAUT["annee"]` | 20 | Poids de l'année |
| `POIDS_DEFAUT["boite"]` | 10 | Poids de la boîte de vitesses |
| `POIDS_DEFAUT["carburant"]` | 10 | Poids du carburant |
| `POIDS_DEFAUT["options"]` | 5 | Poids des options |
| `SCORE_MIN_NOTIFICATION` | 60 | Score minimum pour être notifié |
| `MAX_ANNONCES` | 3 | Nombre max d'annonces remontées par run |
| `TOLERANCE_PRIX_SOUPLE` | 1.05 | Tolérance budget si non strict (+5%) |
| `TOLERANCE_KM_SOUPLE` | 1.10 | Tolérance km (+10%) |
| `PENALITE_PAR_CHAMP` | 10 | Pénalité par champ manquant |
| `PENALITE_MAX` | 30 | Plafond des pénalités |
| `BONUS_FRAICHEUR` | 5/3/1 pts | Bonus pour annonces <24h / <48h / <7j |

---

## Utilisation

### Commandes disponibles

```bash
# Initialiser la base de données (une seule fois)
python main.py init

# Charger des données de démonstration
python main.py seed

# Lancer un run avec les données de démo (jour 1)
python main.py run --source mock --day 1

# Lancer un run avec les données de démo (jour 2, avec baisse de prix)
python main.py run --source mock --day 2

# Lancer un vrai scraping sur mobile.de
python main.py run --source mobile.de

# Ouvrir l'interface web
python main.py ui
# Puis ouvre http://localhost:8765 dans ton navigateur
```

### Workflow typique

1. `python main.py init` — initialiser (première fois)
2. Créer une recherche via l'interface web (`python main.py ui`)
3. `python main.py run --source mobile.de` — lancer le scraping
4. Recevoir la notification avec les meilleures annonces
5. Répéter le step 3 régulièrement (cron, alarme, manuellement)

### Créer une recherche via l'URL mobile.de

La méthode la plus simple et la plus précise :

1. Va sur [mobile.de](https://www.mobile.de), fais ta recherche avec tous tes filtres
2. Copie l'URL de la page de résultats
3. Dans l'interface web, colle cette URL dans le champ **URL mobile.de**

Carveille utilisera cette URL directement et appliquera quand même son propre scoring sur les résultats.

---

## Comprendre le score

Chaque annonce reçoit un **score de 0 à 100** calculé ainsi :

```
Score = prix(30) + km(25) + annee(20) + boite(10) + carburant(10) + options(5)
      + bonus_fraicheur (jusqu'à +5)
      - penalites_champs_manquants (jusqu'à -30)
```

### Paliers de score par critère

**Prix (30 pts)**
- ≤ 90% du budget → 30 pts (plein)
- ≤ 100% → 21 pts
- ≤ 105% (budget non strict uniquement) → 12 pts
- > 105% ou budget strict dépassé → 0 pts + rejet

**Kilométrage (25 pts)**
- ≤ 80% du km max → 25 pts
- ≤ 100% → 17.5 pts
- ≤ 110% → 10 pts
- > 110% → 0 pts + rejet

**Année (20 pts)**
- ≥ année minimum → 20 pts
- = année minimum - 1 → 10 pts
- < année minimum - 1 → 0 pts + rejet

**Boîte de vitesses (10 pts)**
- Correspond → 10 pts
- Ne correspond pas → 0 pts

**Carburant (10 pts)**
- Correspond → 10 pts
- Ne correspond pas → 0 pts

**Options (5 pts)**
- Toutes les options trouvées → 5 pts
- 2 options trouvées → 3.5 pts
- 1 option trouvée → 2 pts
- Aucune → 0 pts

Les annonces avec un score inférieur à `SCORE_MIN_NOTIFICATION` (60 par défaut) ne sont pas notifiées.

---

## Notifications

### Console (défaut)

Aucune configuration requise. Les résultats s'affichent dans le terminal à chaque run.

### Telegram

1. Crée un bot via [@BotFather](https://t.me/BotFather) et récupère le token
2. Envoie un message au bot, puis va sur `https://api.telegram.org/bot<TOKEN>/getUpdates` pour trouver ton `chat_id`
3. Renseigne dans `.env` :
   ```env
   CANAL_NOTIFICATION=telegram
   TELEGRAM_BOT_TOKEN=123456:ABCdef...
   TELEGRAM_CHAT_ID=987654321
   ```

### Email (Gmail)

1. Active l'authentification à deux facteurs sur ton compte Google
2. Génère un [mot de passe d'application](https://myaccount.google.com/apppasswords)
3. Renseigne dans `.env` :
   ```env
   CANAL_NOTIFICATION=email
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=ton.email@gmail.com
   SMTP_PASSWORD=xxxx xxxx xxxx xxxx
   SMTP_DEST=destinataire@email.com
   ```

---

## Structure du projet

```
carveille/
├── main.py              # Point d'entrée CLI + serveur HTTP pour l'UI
├── config.py            # Tous les paramètres ajustables
├── test.py              # Tests automatisés (python test.py)
├── requirements.txt     # Dépendances Python
├── .env.example         # Modèle de configuration
│
├── src/
│   ├── database.py      # Toutes les fonctions SQLite
│   ├── scoring.py       # Moteur de score (scorer_annonce)
│   ├── runner.py        # Orchestrateur principal (un run = charger + scorer + notifier)
│   ├── dedup.py         # Anti-doublon contre la base de données
│   ├── notifier.py      # Envoi des notifications (console / Telegram / email)
│   └── sources/
│       ├── mobile_de.py # Scraper mobile.de (extrait __NEXT_DATA__ Next.js)
│       └── mock.py      # Source de test locale (data/mock_dayN.json)
│
├── data/
│   ├── mock_day1.json   # 15 annonces de démo (jour 1)
│   └── mock_day2.json   # 20 annonces (dont baisse de prix sur ann_001)
│
├── db/
│   └── carveille.db     # Base SQLite (créée par `python main.py init`)
│
└── ui/
    └── index.html       # Interface web (servie par main.py sur :8765)
```

### Tables SQLite

| Table | Rôle |
|---|---|
| `recherches` | Tes critères de recherche |
| `annonces_vues` | Toutes les annonces scrappées avec leur score, `prix_initial`, `baisse_prix` |
| `historique_prix` | Historique des prix constatés à chaque run |
| `runs` | Bilan de chaque run (nb lues, nouvelles, notifiées) |

---

## Tests automatisés

```bash
python test.py
```

Lance 23 vérifications couvrant tous les comportements critiques :

- Scoring correct sur une annonce idéale
- Budget strict / souple
- Filtres boîte, carburant, année + tolérance
- Pénalités champs manquants + plafond
- Sélection et tri du top annonces
- Anti-doublon (annonce déjà vue exclue)
- Détection baisse de prix + montant correct + pas de fausse alarme

Utilise une base de données temporaire isolée — aucun impact sur tes données.

Sortie attendue :
```
========================================
  23/23 tests passés
========================================
```

Exit code 0 si tout passe, 1 si un test échoue (compatible CI).

---

## Remarques

- **Encodage Windows** : si tu vois des erreurs d'encodage dans le terminal, lance `$env:PYTHONIOENCODING="utf-8"` avant la commande Python (PowerShell) ou `set PYTHONIOENCODING=utf-8` (cmd).
- **mobile.de peut bloquer** : si le scraping retourne zéro résultat avec un message `__NEXT_DATA__ introuvable`, mobile.de a probablement bloqué la requête. Attends quelques minutes et réessaie.
- **Le fichier `.env` ne doit jamais être committé** — il est dans `.gitignore`.
