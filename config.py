# Poids par défaut (total = 100)
POIDS_DEFAUT = {
    "prix": 30,
    "km": 25,
    "annee": 20,
    "boite": 10,
    "carburant": 10,
    "options": 5,
}

# Pénalités pour champs manquants (prix, km, année, boite, carburant)
PENALITE_PAR_CHAMP = 10
PENALITE_MAX = 30  # plafond : on ne punit pas plus même si tout manque

# Seuil de notification et nb max d'annonces remontées
SCORE_MIN_NOTIFICATION = 60
MAX_ANNONCES = 3

# Tolérances
TOLERANCE_PRIX_SOUPLE = 1.05
TOLERANCE_KM_SOUPLE = 1.10

# Bonus fraîcheur (points ajoutés au score final, capé à 100)
BONUS_FRAICHEUR = {
    "24h": 5,
    "48h": 3,
    "7j": 1,
}

# Villes/zones à risque d'inondation en Allemagne
# Source : historique des crues majeures (Ahr 2021, Elbe 2002/2013, Rhin, Danube...)
ZONES_INONDATION = {
    # Vallée de l'Ahr (catastrophe 2021)
    "ahrweiler", "neuenahr", "altenahr", "dernau", "rech", "mayschoss", "mayschoß",
    "sinzig", "schuld", "insul", "antweiler",
    # Vallée du Rhin
    "koblenz", "köln", "cologne", "bonn", "düsseldorf", "dusseldorf",
    "duisburg", "mannheim", "worms", "mainz", "karlsruhe", "wiesbaden",
    "wesel", "dormagen", "leverkusen", "neuss", "andernach", "bingen",
    "bad honnef", "königswinter", "konigswinter", "remagen",
    # Vallée de l'Elbe
    "dresden", "magdeburg", "wittenberg", "schönebeck", "schonebeck",
    "tangermünde", "tangermunde", "havelberg", "wittenberge", "pirna",
    "meissen", "meißen", "riesa", "torgau",
    # Moselle
    "trier", "cochem", "bernkastel", "zell", "traben-trarbach", "bullay",
    # Oder
    "frankfurt (oder)", "eisenhüttenstadt", "eisenhuttenstadt", "küstrin", "kustrin",
    # Danube (Donau)
    "passau", "deggendorf", "straubing", "regensburg", "ingolstadt",
    "neuburg", "kelheim", "donauwörth", "donauworth",
    # Inn (crue 2013/2016)
    "simbach", "rosenheim", "mühldorf", "muhldorf", "braunau",
    # Néckar
    "heidelberg", "heilbronn", "ladenburg", "eberbach",
    # Main
    "würzburg", "wurzburg", "aschaffenburg", "miltenberg",
    # Weser
    "hameln", "minden", "nienburg", "rinteln",
    # Saale
    "merseburg", "naumburg", "weißenfels", "weissenfels",
    # Lippe / Ruhr
    "lünen", "lunen", "hamm", "herne",
    # Pays-Bas — vallée de la Maas (Meuse)
    "venlo", "roermond", "maastricht", "oss", "megen", "ravenstein",
    "boxmeer", "grave", "cuijk", "gennep",
    # Pays-Bas — vallée du Rhin / Waal
    "nijmegen", "arnhem", "tiel", "zaltbommel", "gorinchem", "woudrichem",
    "geldermalsen", "rhenen", "wageningen", "bemmel",
    # Pays-Bas — vallée de l'IJssel
    "zutphen", "deventer", "zwolle", "kampen", "hattem", "doesburg",
    # Pays-Bas — delta / zones basses
    "dordrecht", "middelburg", "vlissingen", "goes", "terneuzen",
    "sliedrecht", "alblasserdam", "kinderdijk",
    # Pays-Bas — 's-Hertogenbosch et environs (inondations 1995, 2011)
    "'s-hertogenbosch", "den bosch", "heusden", "vught",
}

# Mapping marques → codes mobile.de
MAKES_MOBILE_DE = {
    "BMW": "BMW",
    "Peugeot": "PEUGEOT",
    "Mercedes": "MERCEDES_BENZ",
    "Mercedes-Benz": "MERCEDES_BENZ",
    "Volkswagen": "VW",
    "VW": "VW",
    "Audi": "AUDI",
    "Renault": "RENAULT",
    "Toyota": "TOYOTA",
    "Ford": "FORD",
    "Opel": "OPEL",
    "Citroen": "CITROEN",
    "Citroën": "CITROEN",
    "Skoda": "SKODA",
    "Škoda": "SKODA",
    "SEAT": "SEAT",
    "Seat": "SEAT",
    "Volvo": "VOLVO",
    "Hyundai": "HYUNDAI",
    "Kia": "KIA",
    "Nissan": "NISSAN",
    "Honda": "HONDA",
    "Mazda": "MAZDA",
    "Porsche": "PORSCHE",
    "Fiat": "FIAT",
    "Alfa Romeo": "ALFA_ROMEO",
    "Mini": "MINI",
    "Dacia": "DACIA",
    "Suzuki": "SUZUKI",
    "Mitsubishi": "MITSUBISHI",
    "Land Rover": "LAND_ROVER",
    "Jaguar": "JAGUAR",
    "Lexus": "LEXUS",
    "Tesla": "TESLA",
    "Jeep": "JEEP",
    "Dodge": "DODGE",
    "Chrysler": "CHRYSLER",
    "Infiniti": "INFINITI",
    "Subaru": "SUBARU",
    "Isuzu": "ISUZU",
    "DS": "DS",
    "Cupra": "CUPRA",
    "MG": "MG",
    "BYD": "BYD",
    "Polestar": "POLESTAR",
    "Rivian": "RIVIAN",
    "Lucid": "LUCID",
    "Genesis": "GENESIS",
}

# Mapping modèles courants → codes mobile.de
MODELS_MOBILE_DE = {
    "Série 1": "1ER", "Serie 1": "1ER", "1er": "1ER",
    "Série 2": "2ER", "Serie 2": "2ER",
    "Série 3": "3ER", "Serie 3": "3ER",
    "Série 4": "4ER", "Série 5": "5ER", "Série 6": "6ER", "Série 7": "7ER",
    "X1": "X1", "X2": "X2", "X3": "X3", "X4": "X4",
    "X5": "X5", "X6": "X6", "X7": "X7",
    "Z4": "Z4", "M3": "M3", "M5": "M5",
    "208": "208", "308": "308", "508": "508",
    "3008": "3008", "5008": "5008", "2008": "2008",
    "Clio": "CLIO", "Megane": "MEGANE", "Mégane": "MEGANE",
    "Kadjar": "KADJAR", "Captur": "CAPTUR",
    "Golf": "GOLF", "Polo": "POLO", "Passat": "PASSAT", "Tiguan": "TIGUAN",
    "A3": "A3", "A4": "A4", "A5": "A5", "A6": "A6",
    "Q3": "Q3", "Q5": "Q5", "Q7": "Q7",
    "Classe A": "A_KLASSE", "Classe C": "C_KLASSE", "Classe E": "E_KLASSE",
    "GLA": "GLA", "GLC": "GLC", "GLE": "GLE",
}

# Mapping transmission → code mobile.de
TRANSMISSION_MOBILE_DE = {
    "auto": "AUTOMATIC_GEAR",
    "automatique": "AUTOMATIC_GEAR",
    "manuelle": "MANUAL_GEAR",
    "manual": "MANUAL_GEAR",
    "indifferent": None,
}

# Mapping carburant → code mobile.de
FUEL_MOBILE_DE = {
    "diesel": "DIESEL",
    "essence": "PETROL",
    "electrique": "ELECTRIC",
    "électrique": "ELECTRIC",
    "hybride": "HYBRID_PETROL",
    "indifferent": None,
}
