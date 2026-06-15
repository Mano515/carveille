# Carveille

Outil de veille automatisée sur les annonces automobiles mobile.de.

Carveille scrape mobile.de selon tes critères, score chaque annonce, détecte les baisses de prix, et t'envoie une notification (Telegram, email ou console) avec seulement les meilleures.

---

## Sommaire

1. [Ce que ça fait](#ce-que-ça-fait)
2. [Prérequis](#prérequis)
3. [Installation](#installation)
4. [Utilisation quotidienne](#utilisation-quotidienne)
5. [Créer une recherche](#créer-une-recherche)
6. [Configurer les notifications](#configurer-les-notifications)
7. [Vérification automatique](#vérification-automatique)
8. [Comprendre le score](#comprendre-le-score)
9. [Structure du projet](#structure-du-projet)
10. [Tests automatisés](#tests-automatisés)

---

## Ce que ça fait

- **Scraping mobile.de** — récupère les annonces selon tes critères (marque, modèle, budget, km, boîte, carburant…)
- **Scoring sur 100** — chaque annonce reçoit un score pondéré selon tes critères
- **Détection de baisses de prix** — si une annonce déjà vue baisse de prix, tu en es informé
- **Bonus fraîcheur** — les annonces très récentes (<24h, <48h, <7j) gagnent quelques points
- **Anti-doublon** — une annonce vue ne remonte pas comme nouvelle au run suivant
- **Vérification automatique** — choisir une heure dans l'interface, Carveille vérifie tous les jours sans action manuelle
- **Interface web** — tableau de bord local pour voir les résultats, marquer l'intérêt, configurer les alertes
- **Notifications** — console (défaut), Telegram, ou email SMTP, configurables depuis l'interface

---

## Prérequis

- Python 3.11 ou plus récent ([télécharger](https://www.python.org/downloads/) — cocher "Add Python to PATH" lors de l'installation)

Pas de base de données externe, pas de serveur cloud — tout tourne en local avec SQLite.

---

## Installation

### 1. Cloner le projet

```bash
git clone https://github.com/Mano515/carveille.git
cd carveille
```

### 2. Lancer

Double-clic sur **`Lancer Carveille.bat`**.

À la première utilisation, le script installe automatiquement tout ce dont Python a besoin (1-2 minutes). Ensuite, le navigateur s'ouvre tout seul sur l'interface.

> La fenêtre noire qui s'ouvre doit rester ouverte pendant toute l'utilisation de Carveille. La fermer arrête l'application.

---

## Utilisation quotidienne

1. Double-clic sur **`Lancer Carveille.bat`**
2. Le navigateur s'ouvre automatiquement sur l'interface
3. Cliquer sur **"Chercher maintenant sur mobile.de"** pour lancer une vérification
4. Consulter les résultats dans l'onglet **Résultats**
5. Marquer les annonces intéressantes avec 👍 ou les masquer avec 👎

> Le bouton **?** en bas à droite de l'interface affiche une aide contextuelle selon l'onglet ouvert.

---

## Créer une recherche

Dans l'onglet **"Nouvelle recherche"**, remplir le formulaire avec tes critères.

### Méthode recommandée : URL mobile.de

La méthode la plus précise et la plus simple :

1. Aller sur [mobile.de](https://www.mobile.de)
2. Faire sa recherche avec tous les filtres souhaités
3. Copier l'adresse de la page de résultats
4. La coller dans le champ **"URL de recherche mobile.de"** du formulaire

Carveille utilisera exactement cette URL et appliquera son scoring sur les résultats.

### Options du formulaire

| Champ | Description |
|---|---|
| Nom de la recherche | Nom libre pour s'y retrouver (ex : "BMW Papa") |
| Marque / Modèle | La voiture recherchée |
| Budget maximum | Prix au-dessus duquel les annonces sont pénalisées |
| Budget strict | Si coché : toute annonce au-dessus du budget est ignorée (sans tolérance) |
| Kilométrage maximum | Au-delà, l'annonce est pénalisée |
| Année minimum | En dessous de cette année, l'annonce est exclue (tolérance de 1 an à 50%) |
| Boîte de vitesses | Automatique, manuelle, ou peu importe |
| Carburant | Diesel, essence, hybride, électrique, ou peu importe |
| Type de vendeur | Pro, particulier, ou peu importe |
| Options souhaitées | Mots-clés séparés par des virgules (ex : camera, gps) |
| Réglages avancés | Modifier l'importance de chaque critère dans le score |

---

## Configurer les notifications

Dans l'onglet **"Paramètres"** de l'interface, choisir comment être alerté.

### Console (défaut)

Aucune configuration. Les résultats s'affichent dans la fenêtre noire.

### Telegram

1. Ouvrir Telegram, chercher **@BotFather**
2. Envoyer `/newbot` et suivre les instructions — noter le **Token**
3. Envoyer un message au bot, puis aller sur :
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Noter le **Chat ID** (le nombre dans le champ `"id"`)
5. Renseigner Token et Chat ID dans l'onglet Paramètres

### Email (Gmail)

1. Activer la validation en deux étapes sur le compte Google
2. Générer un [mot de passe d'application](https://myaccount.google.com/apppasswords)
3. Renseigner l'adresse email et ce mot de passe (pas le mot de passe habituel) dans l'onglet Paramètres

> La configuration est sauvegardée dans le fichier `.env` à la racine du projet. Ce fichier ne doit jamais être partagé (il contient les tokens/mots de passe).

---

## Vérification automatique

Dans l'onglet **"Paramètres"**, activer la vérification automatique et choisir une heure.

Carveille lancera une recherche chaque jour à cette heure — sans action manuelle.

> **Important** : la fenêtre noire (`Lancer Carveille.bat`) doit être ouverte à ce moment-là. Pour que ça fonctionne tous les jours, laisser la fenêtre ouverte en permanence ou s'assurer qu'elle est ouverte avant l'heure configurée.

---

## Comprendre le score

Chaque annonce reçoit un **score de 0 à 100** :

```
Score = prix(30) + km(25) + annee(20) + boite(10) + carburant(10) + options(5)
      + bonus fraîcheur (jusqu'à +5)
      − pénalités champs manquants (jusqu'à −30)
```

### Couleurs

| Couleur | Score | Signification |
|---|---|---|
| Vert | 80+ | Excellente annonce |
| Orange | 60–79 | Annonce correcte |
| Rouge | < 60 | Ne correspond pas bien |

### Paliers par critère

**Prix (30 pts)**
- ≤ 90% du budget → 30 pts
- ≤ 100% → 21 pts
- ≤ 105% (si budget non strict) → 12 pts
- Au-delà → 0 pts

**Kilométrage (25 pts)**
- ≤ 80% du km max → 25 pts
- ≤ 100% → 17,5 pts
- ≤ 110% → 10 pts
- Au-delà → 0 pts

**Année (20 pts)**
- ≥ année minimum → 20 pts
- = année minimum − 1 → 10 pts
- < année minimum − 1 → 0 pts (annonce exclue)

**Boîte / Carburant (10 pts chacun)**
- Correspond → plein score
- Ne correspond pas → 0 pts

**Options (5 pts)**
- Toutes présentes → 5 pts / 2 présentes → 3,5 pts / 1 présente → 2 pts / aucune → 0 pt

---

## Structure du projet

```
carveille/
├── Lancer Carveille.bat   # Double-clic pour tout démarrer
├── main.py                # Point d'entrée CLI + serveur HTTP
├── config.py              # Paramètres ajustables (poids, seuils, mappings mobile.de)
├── test.py                # Tests automatisés (python test.py)
├── requirements.txt       # Dépendances Python
├── .env                   # Configuration locale (créé automatiquement, ne pas partager)
├── .env.example           # Modèle de configuration
│
├── src/
│   ├── database.py        # Toutes les fonctions SQLite
│   ├── scoring.py         # Moteur de score
│   ├── runner.py          # Orchestrateur (charger → scorer → notifier)
│   ├── dedup.py           # Anti-doublon
│   ├── notifier.py        # Envoi des notifications
│   └── sources/
│       ├── mobile_de.py   # Scraper mobile.de
│       └── mock.py        # Source de test locale
│
├── data/
│   ├── mock_day1.json     # 15 annonces de démonstration
│   └── mock_day2.json     # 20 annonces (avec baisse de prix pour tester)
│
├── db/
│   ├── carveille.db       # Base SQLite (créée au premier lancement)
│   └── schedule.json      # Planning de vérification automatique
│
└── ui/
    └── index.html         # Interface web (servie sur http://localhost:8765)
```

### Tables SQLite

| Table | Rôle |
|---|---|
| `recherches` | Les critères de recherche sauvegardés |
| `annonces_vues` | Toutes les annonces trouvées avec score, `prix_initial`, `baisse_prix` |
| `historique_prix` | Historique des prix à chaque run |
| `runs` | Bilan de chaque run |

---

## Tests automatisés

```bash
python test.py
```

Lance 23 vérifications automatiques sans framework externe :

- Scoring correct sur une annonce idéale
- Budget strict / souple
- Filtres boîte, carburant, année + tolérance
- Pénalités champs manquants + plafond
- Sélection et tri du top annonces
- Anti-doublon
- Détection de baisse de prix + montant correct + pas de fausse alarme

Utilise une base de données temporaire isolée — aucun impact sur les données réelles.

```
========================================
  23/23 tests passés
========================================
```

Exit code 0 si tout passe, 1 si un test échoue (compatible CI).

---

## Remarques

- **Encodage Windows** : si des caractères s'affichent mal dans la fenêtre noire, lancer `$env:PYTHONIOENCODING="utf-8"` avant la commande Python.
- **mobile.de peut bloquer** : si le scraping retourne zéro résultat avec un message `__NEXT_DATA__ introuvable`, mobile.de a probablement bloqué la requête. Attendre quelques minutes et réessayer.
- **Le fichier `.env`** est dans `.gitignore` et ne sera jamais envoyé sur GitHub.
