import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")


def charger(recherche: dict, day: int = 1) -> list:
    path = os.path.join(DATA_DIR, f"mock_day{day}.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)
