# categories.py
# Keyword-based automatic tagging for IHL articles.
# Each category has a list of keywords (lowercase).
# An article is tagged if ANY keyword appears in its title or full_text.

CATEGORIES = {
    "Targeting": [
        "targeting", "military objective", "distinction", "proportionality",
        "precautionary", "precautions", "dual use", "dual-use",
        "collateral damage", "collateral", "lawful target", "unlawful attack",
        "airstrike", "air strike", "bombardment", "indiscriminate",
        "direct participation", "dph", "human shields"
    ],
    "Cyber": [
        "cyber", "cyberattack", "cyber attack", "cyberwarfare", "cyber warfare",
        "cyber operation", "tallinn manual", "information warfare",
        "electronic warfare", "hacking", "malware", "ransomware",
        "critical infrastructure", "disinformation", "autonomous weapon",
        "artificial intelligence", "ai weapon", "algorithm"
    ],
    "IHL": [
        "international humanitarian law", "ihl", "geneva convention",
        "additional protocol", "laws of war", "law of armed conflict", "loac",
        "combatant", "civilian", "protected persons", "humanitarian",
        "martens clause", "customary ihl", "non-international armed conflict",
        "niac", "international armed conflict", "iac", "armed conflict"
    ],
    "ICJ / Courts": [
        "icj", "international court of justice", "international criminal court",
        "icc", "war crimes", "genocide", "crimes against humanity",
        "tribunal", "prosecution", "accountability", "jurisdiction",
        "universal jurisdiction", "advisory opinion", "state responsibility",
        "rome statute", "individual criminal responsibility"
    ],
    "Occupation": [
        "occupation", "occupied territory", "occupying power",
        "belligerent occupation", "annexation", "settlement", "settler",
        "occupied population", "hague regulations", "fourth geneva",
        "administration of occupied", "transfer of civilians"
    ],
    "Detention": [
        "detention", "prisoner of war", "pow", "internment",
        "interrogation", "torture", "cruel treatment", "captive",
        "guantanamo", "detainee", "habeas corpus", "security detention",
        "administrative detention", "fair trial", "due process"
    ],
    "Weapon Systems": [
        "weapon", "weapons", "explosive", "munition", "ammunition",
        "cluster munition", "landmine", "anti-personnel mine",
        "chemical weapon", "biological weapon", "nuclear weapon",
        "incendiary", "white phosphorus", "lethal autonomous",
        "laws", "armed drone", "uav", "unmanned"
    ]
}

ALL_CATEGORY_NAMES = list(CATEGORIES.keys())


def assign_categories(article: dict) -> list:
    """
    Returns a list of matching category names for an article,
    based on keywords found in title + full_text (case-insensitive).
    Falls back to ['General'] if nothing matches.
    """
    text = (
        article.get("title", "") + " " + article.get("full_text", "")
    ).lower()

    matched = [
        category
        for category, keywords in CATEGORIES.items()
        if any(kw in text for kw in keywords)
    ]

    return matched if matched else ["General"]