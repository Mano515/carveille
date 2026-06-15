# Carveille

Outil de veille automatisée sur les annonces automobiles mobile.de.

Carveille scrape mobile.de selon vos critères, score chaque annonce, détecte les baisses de prix, et envoie une notification par email avec seulement les meilleures. Toutes les recherches sont organisées par dossier client.

---

## Sommaire

1. [Ce que ça fait](#ce-que-ça-fait)
2. [Prérequis](#prérequis)
3. [Installation](#installation)
4. [Utilisation quotidienne](#utilisation-quotidienne)
5. [Gérer les dossiers clients](#gérer-les-dossiers-clients)
6. [Créer une recherche](#créer-une-recherche)
7. [Consulter les résultats](#consulter-les-résultats)
8. [Configurer les alertes email](#configurer-les-alertes-email)
9. [Convertir des images AVIF en JPG](#convertir-des-images-avif-en-jpg)
10. [Vérification automatique](#vérification-automatique)
11. [Mises à jour](#mises-à-jour)
12. [Comprendre le score](#comprendre-le-score)
13. [Structure du projet](#structure-du-projet)
14. [Tests automatisés](#tests-automatisés)

---

## Ce que ça fait

- **Dossiers clients** — chaque client a son dossier avec ses recherches, ses résultats, ses favoris et ses liens sauvegardés
- **Scraping mobile.de** — récupère les annonces selon les critères (marque, modèle, budget, km, boîte, carburant…)
- **Scoring sur 100** — chaque annonce reçoit un score pondéré selon les critères
- **Détection de baisses de prix** — si une annonce déjà vue baisse de prix, vous en êtes informé
- **Détection de doublons** — si la même annonce correspond à plusieurs clients, un badge d'avertissement s'affiche
- **Bonus fraîcheur** — les annonces très récentes (<24h, <48h, <7j) gagnent quelques points
- **Anti-doublon** — une annonce vue ne remonte pas comme nouvelle au run suivant
- **Alertes automatiques** — choisissez les horaires et les jours, Carveille vérifie sans action manuelle
- **Résumé hebdomadaire** — email de bilan chaque dimanche par client (optionnel)
- **Notes personnelles** — ajoutez des notes sur chaque annonce (rappel, avis, négociation…)
- **Liens sauvegardés** — enregistrez manuellement des liens d'annonces trouvées en naviguant
- **Filtre des résultats** — filtrez par texte, prix max et km max directement dans l'interface
- **Dossiers locaux** — un dossier Windows est créé automatiquement pour chaque client dans Documents/Carveille/Clients
- **Convertisseur AVIF → JPG** — convertit les images mobile.de en JPG partageables, directement dans le dossier du client
- **Interface web** — tableau de bord local pour voir les résultats, marquer l'intérêt, configurer les alertes

---

## Prérequis

- Python 3.11 ou plus récent ([télécharger](https://www.python.org/downloads/) — cocher "Add Python to PATH" lors de l'installation)
- Git ([télécharger](https://git-scm.com/download/win) — nécessaire pour les mises à jour automatiques)

Pas de base de données externe, pas de serveur cloud — tout tourne en local avec SQLite.

---

## Installation

### 1. Installer Python et Git

Suivre les instructions dans **`Installer Python.txt`** puis **`Installer Git.txt`**.

### 2. Télécharger Carveille

Ouvrir le menu Démarrer, taper `cmd`, et coller :

```
cd %USERPROFILE%\Documents && git clone https://github.com/Mano515/carveille.git
```

### 3. Lancer

Double-clic sur **`Lancer Carveille.bat`** dans le dossier `carveille`.

À la première utilisation, le script installe automatiquement tout ce dont Python a besoin (1-2 minutes). Ensuite, Chrome s'ouvre tout seul sur l'interface.

> La fenêtre noire qui s'ouvre doit rester ouverte pendant toute l'utilisation de Carveille. La fermer arrête l'application.

---

## Utilisation quotidienne

1. Double-clic sur **`Lancer Carveille.bat`** — la fenêtre se minimise automatiquement, Chrome s'ouvre
2. Cliquer sur **"Chercher pour tous les clients"** pour lancer une vérification manuelle
3. Consulter les résultats dans l'onglet **Résultats** (ou attendre l'email si les alertes sont configurées)
4. Marquer les annonces intéressantes avec 👍 ou les masquer avec 👎
5. Ajouter une note personnelle sur une annonce si besoin

> Le bouton **?** en bas à droite affiche une aide contextuelle selon l'onglet ouvert.

---

## Gérer les dossiers clients

L'onglet **"Mes recherches"** affiche tous les dossiers clients.

### Créer un client

Cliquer sur **"+ Nouveau client"** et renseigner :
- Nom du client (obligatoire — les doublons de nom sont bloqués)
- Téléphone ou email (optionnel)
- Notes libres : budget, préférences, remarques

Un dossier est automatiquement créé sur l'ordinateur :
```
Documents/
└── Carveille/
    └── Clients/
        └── Dupont Jean/
            ├── voitures/     ← images et photos
            └── documents/    ← PDFs, devis, contrats
```

### Modifier un client (✏️)

Cliquer sur le bouton ✏️ en haut à droite de la carte pour modifier le nom, les coordonnées ou les notes d'un client.

### Bouton 📂 Dossier

Ouvre directement le dossier du client dans l'explorateur Windows.

### Favoris (⭐)

Quand un client a des annonces marquées 👍, un badge "⭐ N favori(s)" apparaît sur sa carte. Cliquez dessus pour voir toutes ses annonces retenues, triées par score.

### Liens sauvegardés

En bas de chaque carte client, une zone permet de coller des liens d'annonces trouvées en naviguant soi-même sur mobile.de. Ajoutez un titre pour vous souvenir de quoi il s'agit. Les liens sont cliquables directement depuis la carte.

### Modifier ou supprimer une recherche

Sur chaque recherche d'un client :
- **✏️** — modifie les critères (le formulaire se pré-remplit automatiquement)
- **🗑️** — désactive la recherche (les annonces déjà trouvées sont conservées)

### Archiver / Réactiver / Supprimer un client

- **Archiver** — retire le client de la liste principale sans rien supprimer. Accessible dans "Dossiers archivés" en bas de page.
- **Réactiver** — remet le client dans la liste principale.
- **Supprimer** — supprime définitivement le client et toutes ses données (uniquement depuis les archives). Action irréversible.

### Recherches sans client

Les recherches non rattachées à un client apparaissent dans une section dédiée. Utilisez le menu **"Rattacher à…"** pour les associer au bon client.

---

## Créer une recherche

Dans l'onglet **"Nouvelle recherche"**, remplir le formulaire.

### Choisir un client

Sélectionnez le client concerné en haut du formulaire. Vous pouvez aussi cliquer sur **"+ Nouvelle recherche pour ce client"** directement depuis la carte du client.

### Méthode recommandée : URL mobile.de

1. Aller sur [mobile.de](https://www.mobile.de)
2. Faire sa recherche avec tous les filtres souhaités
3. Copier l'adresse de la page de résultats
4. La coller dans le champ **"URL de recherche mobile.de"**

### Options du formulaire

| Champ | Description |
|---|---|
| Nom de la recherche | Nom libre (ex : "BMW Papa") |
| Marque / Modèle | La voiture recherchée |
| Budget maximum | Prix au-dessus duquel les annonces sont pénalisées |
| Budget strict | Si coché : toute annonce au-dessus du budget est ignorée |
| Kilométrage maximum | Au-delà, l'annonce est pénalisée |
| Année minimum | En dessous, l'annonce est exclue (tolérance de 1 an à 50%) |
| Boîte de vitesses | Automatique, manuelle, ou peu importe |
| Carburant | Diesel, essence, hybride, électrique, ou peu importe |
| Type de vendeur | Pro, particulier, ou peu importe |
| Options souhaitées | Mots-clés séparés par des virgules (ex : camera, gps) |
| Réglages avancés | Modifier l'importance de chaque critère dans le score |

---

## Consulter les résultats

Cliquer sur **"Résultats"** à côté d'une recherche pour voir les annonces trouvées.

### Actions sur une annonce

- **👍 Intéressé** — met l'annonce en évidence et l'ajoute aux Favoris du client
- **👎 Pas intéressé** — masque l'annonce (rien n'est supprimé définitivement)
- **Voir l'annonce** — ouvre l'annonce sur mobile.de dans un nouvel onglet Chrome
- **Traduire** — ouvre l'annonce traduite en français via DeepL
- **Détail du score** — affiche la note obtenue pour chaque critère
- **Note personnelle** — champ texte pour écrire ses propres remarques sur l'annonce ("à rappeler lundi", "vu en vrai"…)

### Badges sur les annonces

- **Nouvelle annonce** (vert) — annonce absente lors de la vérification précédente
- **Baisse -X EUR** (orange) — le prix a baissé depuis la première apparition
- **⚠️ Vu aussi pour [client]** — la même annonce correspond à un autre client

### Filtrer les résultats

Une barre de filtres apparaît automatiquement au-dessus des résultats. Filtrez par :
- Mot-clé (titre, ville)
- Prix maximum
- Kilométrage maximum

Les filtres s'appliquent instantanément. Cliquer **✕ Effacer** pour tout réafficher.

---

## Configurer les alertes email

Dans l'onglet **"Paramètres"**.

### Configuration Gmail

1. Activer la validation en deux étapes sur le compte Google
2. Générer un [mot de passe d'application](https://myaccount.google.com/apppasswords)
3. Renseigner l'adresse email et ce mot de passe dans l'onglet Paramètres
4. Cliquer sur **"Envoyer un email de test"** pour vérifier

### Planning des alertes

- **Horaires** — jusqu'à 4 heures par jour (ex : 9h00 et 18h00)
- **Jours** — choisir les jours de la semaine actifs
- **Nouvelles annonces** — recevoir un email quand de nouvelles annonces sont trouvées
- **Baisses de prix** — recevoir un email quand un prix baisse
- **Résumé du dimanche** — email hebdomadaire avec les stats par client (nouvelles annonces de la semaine + total des favoris)

### Historique des vérifications

En bas de l'onglet Paramètres : liste des dernières vérifications effectuées avec date, heure, nombre d'annonces trouvées et durée.

---

## Convertir des images AVIF en JPG

Les images téléchargées depuis mobile.de sont au format AVIF, difficile à partager par email ou WhatsApp.

Dans l'onglet **"Outils"** :

1. Sélectionner le client destinataire dans la liste
2. Glisser les fichiers AVIF dans la zone, ou cliquer pour les sélectionner
3. Cliquer sur **"Convertir en JPG"**

Les JPG sont enregistrés automatiquement dans le dossier `voitures/` du client sélectionné (ou dans un dossier "Non classé" si aucun client n'est choisi).

---

## Vérification automatique

Dans l'onglet **"Paramètres"**, activer les alertes automatiques et choisir les horaires.

> **Important** : la fenêtre noire (`Lancer Carveille.bat`) doit être ouverte à ce moment-là. Pour que ça fonctionne tous les jours, laisser la fenêtre ouverte en permanence ou s'assurer qu'elle est ouverte avant l'heure configurée.

---

## Mises à jour

Quand une mise à jour est disponible, double-cliquer sur **`Mettre a jour Carveille.bat`**. Ce fichier :

1. Arrête Carveille s'il est en cours
2. Télécharge la dernière version depuis GitHub
3. Relance Carveille automatiquement

> Aucune donnée n'est perdue lors d'une mise à jour (la base de données et la configuration sont exclues du dépôt git).

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
├── Lancer Carveille.bat          # Double-clic pour tout démarrer (fenêtre minimisée)
├── Mettre a jour Carveille.bat   # Mise à jour depuis GitHub + relance automatique
├── main.py                       # Point d'entrée CLI + serveur HTTP
├── config.py                     # Paramètres ajustables (poids, seuils, mappings)
├── test.py                       # Tests automatisés (python test.py)
├── requirements.txt              # Dépendances Python
├── .env                          # Configuration locale (créé automatiquement, ne pas partager)
├── .env.example                  # Modèle de configuration
│
├── src/
│   ├── database.py        # Toutes les fonctions SQLite
│   ├── scoring.py         # Moteur de score
│   ├── runner.py          # Orchestrateur (charger → scorer → notifier)
│   ├── dedup.py           # Anti-doublon
│   ├── notifier.py        # Envoi des notifications email
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
| `clients` | Les dossiers clients (nom, contact, notes, statut) |
| `recherches` | Les critères de recherche, liés à un client |
| `annonces_vues` | Toutes les annonces trouvées avec score, `prix_initial`, `baisse_prix`, `note` |
| `historique_prix` | Historique des prix à chaque run |
| `runs` | Bilan de chaque vérification |
| `liens_client` | Liens d'annonces sauvegardés manuellement par client |

### Dossiers locaux

```
Documents/Carveille/Clients/
├── Dupont Jean/
│   ├── voitures/     ← images JPG des voitures
│   └── documents/    ← PDFs, devis, contrats
└── Martin Paul/
    ├── voitures/
    └── documents/
```

---

## Tests automatisés

```bash
python test.py
```

Lance 41 vérifications automatiques sans framework externe :

- Scoring correct sur une annonce idéale
- Budget strict / souple
- Filtres boîte, carburant, année + tolérance
- Pénalités champs manquants + plafond
- Sélection et tri du top annonces
- Anti-doublon
- Détection de baisse de prix + montant correct + pas de fausse alarme
- Création, archivage et réactivation de clients
- Désactivation et rattachement de recherches
- Historique des runs et résumé hebdomadaire

Utilise une base de données temporaire isolée — aucun impact sur les données réelles.

```
========================================
  41/41 tests passés
========================================
```

Exit code 0 si tout passe, 1 si un test échoue (compatible CI).

---

## Remarques

- **Encodage Windows** : si des caractères s'affichent mal dans la fenêtre noire, lancer `$env:PYTHONIOENCODING="utf-8"` avant la commande Python.
- **mobile.de peut bloquer** : si le scraping retourne zéro résultat avec un message `__NEXT_DATA__ introuvable`, mobile.de a probablement bloqué la requête. Attendre quelques minutes et réessayer.
- **Le fichier `.env`** est dans `.gitignore` et ne sera jamais envoyé sur GitHub.
- **Dossier clients** : par défaut dans `Documents/Carveille/Clients/`. Modifiable dans l'onglet Outils → "Dossier de stockage".
- **Plusieurs clics sur le bat** : si Carveille est déjà lancé, un clic supplémentaire ouvre juste un nouvel onglet — aucune instance dupliquée n'est créée.
