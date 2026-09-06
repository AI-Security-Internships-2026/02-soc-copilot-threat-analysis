"""
mitre_lookup.py
downloads the MITRE ATT&CK enterprise dataset once, caches it locally as json,
and gives a simple function to look up a technique id -> name + short description.

first run will take a few seconds to download (~30mb), after that it reads from cache.
"""

import json
import os
import re
import requests

MITRE_URL = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack.json"
CACHE_PATH = os.path.join("datasets", "mitre_technique_cache.json")


def _download_and_build_cache():
    """downloads the full MITRE stix bundle and extracts technique id -> info"""
    print("downloading MITRE ATT&CK dataset (first time only, this may take a bit)...")
    resp = requests.get(MITRE_URL, timeout=60)
    resp.raise_for_status()
    bundle = resp.json()

    technique_map = {}
    for obj in bundle.get("objects", []):
        if obj.get("type") != "attack-pattern":
            continue

        # find the technique id (like T1059 or T1059.001) from external_references
        technique_id = None
        for ref in obj.get("external_references", []):
            if ref.get("source_name") == "mitre-attack":
                technique_id = ref.get("external_id")
                break

        if not technique_id:
            continue

        description = obj.get("description", "")
        # strip citation markup like (Citation: ...) and footnote refs
        description = re.sub(r"\(Citation:.*?\)", "", description)
        description = re.sub(r"\[\d+\]", "", description)
        # keep only the first paragraph, then hard-cap length on a word boundary
        first_para = description.split("\n")[0].strip()
        if len(first_para) > 350:
            first_para = first_para[:350].rsplit(" ", 1)[0] + "..."
        short_description = first_para

        technique_map[technique_id] = {
            "name": obj.get("name", ""),
            "description": short_description,
        }

    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(technique_map, f, indent=2)

    print(f"cached {len(technique_map)} techniques to {CACHE_PATH}")
    return technique_map


def load_technique_map():
    """loads the technique map from cache, building the cache first if needed"""
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return _download_and_build_cache()


# GUIDE separates multiple technique ids with ";" -- verified against the
# committed evaluation sample, where 232 of 428 non-null MitreTechniques values
# contain ";" and none contain ",". The original parser split on "," only, so
# a value like "T1078;T1078.004" was looked up whole, missed the map, and
# returned nothing: every multi-technique alert -- over half of all alerts
# carrying MITRE data -- silently lost its ATT&CK enrichment. Both separators
# are accepted now so neither real data nor the docstring's example breaks.
_TECHNIQUE_SEPARATORS = re.compile(r"[;,]")

# Cap on how many techniques get expanded into the prompt. Alerts listing a
# technique and two sub-techniques are common; expanding all of them crowds out
# the alert's own fields without adding much.
MAX_TECHNIQUES_IN_CONTEXT = 3


def get_technique_info(technique_id: str, technique_map: dict = None) -> str:
    """
    looks up one or more technique ids (e.g. 'T1059.001' or
    'T1078;T1078.004') and returns a short formatted string for injecting into
    the LLM context. returns empty string if nothing is found or if
    technique_id is missing/blank.
    """
    if not technique_id or not isinstance(technique_id, str):
        return ""

    if technique_map is None:
        technique_map = load_technique_map()

    ids = [part.strip() for part in _TECHNIQUE_SEPARATORS.split(technique_id) if part.strip()]

    descriptions = []
    for tid in ids:
        info = technique_map.get(tid)
        if info:
            descriptions.append(f"{tid} ({info['name']}): {info['description']}")
        if len(descriptions) >= MAX_TECHNIQUES_IN_CONTEXT:
            break

    return "\n".join(descriptions)


if __name__ == "__main__":
    # quick manual test: python -m src.agent.mitre_lookup
    tm = load_technique_map()
    print(get_technique_info("T1059.001", tm))
    print(get_technique_info("T1078", tm))