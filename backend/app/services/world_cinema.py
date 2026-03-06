"""World Cinema Map — country-based discovery with taste matching.

Maps countries to their known cinema genre profiles, then scores
each country against a user's taste profile for personalized discovery.
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CountryProfile:
    """Cinema profile for a country."""
    code: str
    name: str
    flag: str
    region: str
    genres: dict[str, float]  # genre → weight (0-1)
    labels: list[str] = field(default_factory=list)  # e.g. "Bollywood", "K-Drama"
    notable: str = ""  # One-line descriptor


# ── Country Cinema Profiles ──────────────────────────────────────
# Genre weights represent the relative prominence of each genre
# in that country's film/TV output. Weights are normalized 0-1.

COUNTRY_PROFILES: list[CountryProfile] = [
    # ── North America ──
    CountryProfile("US", "United States", "🇺🇸", "North America",
        {"Action": 0.9, "Comedy": 0.8, "Drama": 0.8, "Thriller": 0.7, "Science Fiction": 0.7,
         "Horror": 0.6, "Romance": 0.5, "Animation": 0.6, "Adventure": 0.8, "Crime": 0.6},
        ["Hollywood", "Indie"], "Blockbuster capital, indie powerhouse"),
    CountryProfile("CA", "Canada", "🇨🇦", "North America",
        {"Drama": 0.8, "Thriller": 0.7, "Horror": 0.7, "Science Fiction": 0.5, "Comedy": 0.5,
         "Documentary": 0.6, "Animation": 0.4},
        ["Quebec Cinema"], "Strong horror/thriller scene, Québec arthouse"),
    CountryProfile("MX", "Mexico", "🇲🇽", "North America",
        {"Drama": 0.9, "Thriller": 0.6, "Horror": 0.5, "Comedy": 0.5, "Romance": 0.4,
         "Fantasy": 0.3},
        ["New Mexican Cinema"], "Cuarón, del Toro, Iñárritu — auteur-driven"),

    # ── Europe ──
    CountryProfile("GB", "United Kingdom", "🇬🇧", "Europe",
        {"Drama": 0.9, "Comedy": 0.7, "Crime": 0.7, "Thriller": 0.6, "History": 0.6,
         "Horror": 0.5, "Science Fiction": 0.4, "Romance": 0.5, "War": 0.4, "Mystery": 0.6},
        ["British TV", "Period Drama"], "BBC/Channel 4 golden age, period pieces"),
    CountryProfile("FR", "France", "🇫🇷", "Europe",
        {"Drama": 0.9, "Romance": 0.7, "Comedy": 0.6, "Thriller": 0.6, "Crime": 0.5,
         "Animation": 0.5, "Horror": 0.4, "Science Fiction": 0.3, "Mystery": 0.4},
        ["French New Wave", "Arthouse"], "Cannes heartland, animation excellence"),
    CountryProfile("DE", "Germany", "🇩🇪", "Europe",
        {"Drama": 0.8, "Thriller": 0.7, "Crime": 0.7, "History": 0.6, "War": 0.5,
         "Horror": 0.4, "Science Fiction": 0.5, "Comedy": 0.4, "Mystery": 0.5},
        ["German Expressionism", "Dark"], "Tatort nation, dark/brooding thrillers"),
    CountryProfile("IT", "Italy", "🇮🇹", "Europe",
        {"Drama": 0.9, "Crime": 0.7, "Comedy": 0.6, "Romance": 0.6, "History": 0.5,
         "Thriller": 0.5, "Horror": 0.5, "War": 0.3},
        ["Neorealism", "Giallo"], "Mafia epics, giallo horror, Fellini legacy"),
    CountryProfile("ES", "Spain", "🇪🇸", "Europe",
        {"Drama": 0.8, "Thriller": 0.7, "Horror": 0.6, "Comedy": 0.5, "Crime": 0.5,
         "Romance": 0.4, "Mystery": 0.5, "Fantasy": 0.3},
        ["Spanish Thriller"], "Almodóvar, elite thriller craft"),
    CountryProfile("SE", "Sweden", "🇸🇪", "Scandinavia",
        {"Drama": 0.8, "Crime": 0.8, "Thriller": 0.8, "Mystery": 0.7, "Horror": 0.5},
        ["Nordic Noir"], "Bergman legacy, Nordic noir pioneer"),
    CountryProfile("DK", "Denmark", "🇩🇰", "Scandinavia",
        {"Drama": 0.9, "Crime": 0.7, "Thriller": 0.6, "Comedy": 0.4, "Horror": 0.3,
         "War": 0.3},
        ["Dogme 95", "Nordic Noir"], "Von Trier, Dogme movement"),
    CountryProfile("NO", "Norway", "🇳🇴", "Scandinavia",
        {"Drama": 0.7, "Thriller": 0.7, "Crime": 0.6, "Horror": 0.5, "Adventure": 0.4},
        ["Nordic Noir", "Troll Cinema"], "Emerging genre cinema"),
    CountryProfile("FI", "Finland", "🇫🇮", "Scandinavia",
        {"Drama": 0.8, "Comedy": 0.5, "Crime": 0.4, "Horror": 0.3},
        ["Kaurismäki"], "Deadpan humor, minimalist drama"),
    CountryProfile("NL", "Netherlands", "🇳🇱", "Europe",
        {"Drama": 0.7, "Thriller": 0.5, "Comedy": 0.5, "Documentary": 0.6, "Crime": 0.4},
        [], "Verhoeven origins, strong documentary scene"),
    CountryProfile("PL", "Poland", "🇵🇱", "Europe",
        {"Drama": 0.9, "History": 0.6, "War": 0.6, "Thriller": 0.4, "Horror": 0.3},
        [], "Kieślowski, Polanski — philosophical cinema"),
    CountryProfile("RO", "Romania", "🇷🇴", "Europe",
        {"Drama": 0.9, "Comedy": 0.4},
        ["Romanian New Wave"], "Palme d'Or winners, minimalist realism"),
    CountryProfile("GR", "Greece", "🇬🇷", "Europe",
        {"Drama": 0.8, "Comedy": 0.4, "History": 0.4},
        ["Greek Weird Wave"], "Lanthimos, absurdist cinema"),

    # ── East Asia ──
    CountryProfile("KR", "South Korea", "🇰🇷", "East Asia",
        {"Thriller": 0.9, "Drama": 0.9, "Crime": 0.8, "Horror": 0.7, "Action": 0.7,
         "Romance": 0.6, "Comedy": 0.5, "Science Fiction": 0.4, "Mystery": 0.6},
        ["K-Drama", "Hallyu"], "Bong, Park — genre-blending masters"),
    CountryProfile("JP", "Japan", "🇯🇵", "East Asia",
        {"Animation": 0.9, "Drama": 0.8, "Horror": 0.8, "Action": 0.6, "Science Fiction": 0.6,
         "Fantasy": 0.6, "Thriller": 0.5, "Crime": 0.4, "Romance": 0.4, "Mystery": 0.5},
        ["Anime", "J-Horror", "Studio Ghibli"], "Anime titan, J-horror, Kurosawa legacy"),
    CountryProfile("CN", "China", "🇨🇳", "East Asia",
        {"Action": 0.8, "Drama": 0.8, "History": 0.7, "Fantasy": 0.6, "Romance": 0.5,
         "War": 0.5, "Animation": 0.4, "Comedy": 0.4, "Thriller": 0.3},
        ["Wuxia", "Fifth Generation"], "Wuxia epics, Zhang Yimou spectacles"),
    CountryProfile("HK", "Hong Kong", "🇭🇰", "East Asia",
        {"Action": 0.9, "Crime": 0.8, "Thriller": 0.7, "Drama": 0.6, "Comedy": 0.5,
         "Horror": 0.4, "Romance": 0.3},
        ["HK Action", "Heroic Bloodshed"], "John Woo, Wong Kar-wai, martial arts"),
    CountryProfile("TW", "Taiwan", "🇹🇼", "East Asia",
        {"Drama": 0.9, "Romance": 0.6, "Comedy": 0.4, "Horror": 0.3},
        ["Taiwan New Cinema"], "Ang Lee origins, contemplative drama"),

    # ── South & Southeast Asia ──
    CountryProfile("IN", "India", "🇮🇳", "South Asia",
        {"Drama": 0.8, "Action": 0.7, "Romance": 0.8, "Comedy": 0.7, "Music": 0.8,
         "Thriller": 0.5, "Crime": 0.4, "History": 0.4, "Fantasy": 0.3, "Horror": 0.3},
        ["Bollywood", "Tollywood", "Malayalam"], "World's largest film industry"),
    CountryProfile("TH", "Thailand", "🇹🇭", "Southeast Asia",
        {"Horror": 0.8, "Action": 0.6, "Drama": 0.6, "Comedy": 0.5, "Romance": 0.4,
         "Thriller": 0.5},
        ["Thai Horror"], "Horror powerhouse, Apichatpong arthouse"),
    CountryProfile("PH", "Philippines", "🇵🇭", "Southeast Asia",
        {"Drama": 0.8, "Action": 0.5, "Horror": 0.5, "Comedy": 0.5, "Romance": 0.4},
        [], "Emerging indie scene"),
    CountryProfile("ID", "Indonesia", "🇮🇩", "Southeast Asia",
        {"Action": 0.8, "Horror": 0.7, "Drama": 0.6, "Thriller": 0.5},
        ["Pencak Silat"], "The Raid phenomenon, horror boom"),

    # ── Middle East & Africa ──
    CountryProfile("IR", "Iran", "🇮🇷", "Middle East",
        {"Drama": 0.9, "Mystery": 0.4, "Comedy": 0.3},
        ["Iranian New Wave"], "Farhadi, Kiarostami — festival darlings"),
    CountryProfile("TR", "Turkey", "🇹🇷", "Middle East",
        {"Drama": 0.8, "Romance": 0.7, "Comedy": 0.5, "History": 0.5, "Crime": 0.4,
         "Thriller": 0.4},
        ["Dizi"], "Turkish drama series global explosion"),
    CountryProfile("IL", "Israel", "🇮🇱", "Middle East",
        {"Drama": 0.8, "Thriller": 0.6, "War": 0.5, "Comedy": 0.4},
        [], "Fauda phenomenon, conflict-driven narratives"),
    CountryProfile("NG", "Nigeria", "🇳🇬", "Africa",
        {"Drama": 0.8, "Comedy": 0.6, "Romance": 0.5, "Action": 0.4, "Thriller": 0.3},
        ["Nollywood"], "Nollywood — world's #2 by volume"),
    CountryProfile("ZA", "South Africa", "🇿🇦", "Africa",
        {"Drama": 0.7, "Crime": 0.6, "Thriller": 0.5, "Action": 0.4},
        [], "District 9, emerging genre cinema"),
    CountryProfile("EG", "Egypt", "🇪🇬", "Africa",
        {"Drama": 0.8, "Comedy": 0.6, "Romance": 0.5, "History": 0.4},
        ["Egyptian Golden Age"], "Arabic cinema's historic heart"),

    # ── Oceania ──
    CountryProfile("AU", "Australia", "🇦🇺", "Oceania",
        {"Drama": 0.7, "Horror": 0.6, "Thriller": 0.6, "Action": 0.6, "Comedy": 0.5,
         "Science Fiction": 0.4, "Crime": 0.5, "Adventure": 0.5},
        ["Ozploitation"], "Mad Max, horror/thriller excellence"),
    CountryProfile("NZ", "New Zealand", "🇳🇿", "Oceania",
        {"Fantasy": 0.7, "Drama": 0.6, "Horror": 0.6, "Comedy": 0.5, "Adventure": 0.6},
        ["Wellywood"], "Weta/Jackson, indie horror gems"),

    # ── South America ──
    CountryProfile("BR", "Brazil", "🇧🇷", "South America",
        {"Drama": 0.8, "Crime": 0.7, "Action": 0.5, "Comedy": 0.5, "Thriller": 0.5,
         "Horror": 0.4, "Romance": 0.3},
        ["Cinema Novo"], "City of God legacy, social realism"),
    CountryProfile("AR", "Argentina", "🇦🇷", "South America",
        {"Drama": 0.9, "Thriller": 0.6, "Comedy": 0.5, "Crime": 0.4, "Mystery": 0.4},
        ["New Argentine Cinema"], "Oscar winners, cerebral thrillers"),
    CountryProfile("CO", "Colombia", "🇨🇴", "South America",
        {"Drama": 0.7, "Crime": 0.6, "Thriller": 0.5, "Action": 0.4},
        [], "Narco narratives, emerging auteurs"),
    CountryProfile("CL", "Chile", "🇨🇱", "South America",
        {"Drama": 0.8, "Comedy": 0.4, "Thriller": 0.4},
        [], "Larraín, Lelio — Oscar-nominated new wave"),
]

# Index for fast lookup
COUNTRY_MAP: dict[str, CountryProfile] = {c.code: c for c in COUNTRY_PROFILES}

# Region ordering for UI layout
REGIONS = [
    ("East Asia", ["KR", "JP", "CN", "HK", "TW"]),
    ("Europe", ["GB", "FR", "DE", "IT", "ES", "NL", "PL", "RO", "GR"]),
    ("Scandinavia", ["SE", "DK", "NO", "FI"]),
    ("North America", ["US", "CA", "MX"]),
    ("South & Southeast Asia", ["IN", "TH", "ID", "PH"]),
    ("Middle East & Africa", ["TR", "IR", "IL", "EG", "NG", "ZA"]),
    ("South America", ["BR", "AR", "CO", "CL"]),
    ("Oceania", ["AU", "NZ"]),
]


def compute_taste_match(user_genres: dict[str, float], country: CountryProfile) -> float:
    """Compute taste match score between user genre preferences and country profile.

    Uses cosine-like similarity: sum of min(user_weight, country_weight)
    normalized by the geometric mean of both vector magnitudes.
    Returns 0.0-1.0.
    """
    if not user_genres or not country.genres:
        return 0.0

    overlap = 0.0
    for genre, c_weight in country.genres.items():
        u_weight = user_genres.get(genre, 0.0)
        overlap += min(u_weight, c_weight)

    user_mag = sum(v for v in user_genres.values())
    country_mag = sum(v for v in country.genres.values())

    if user_mag == 0 or country_mag == 0:
        return 0.0

    # Normalize by geometric mean of magnitudes
    import math
    denom = math.sqrt(user_mag * country_mag)
    return min(overlap / denom, 1.0) if denom > 0 else 0.0


def get_world_cinema_map(user_genres: dict[str, float] | None = None) -> dict:
    """Return full world cinema map data with optional taste matching.

    Args:
        user_genres: Dict of genre → normalized score (0-1) from user taste profile.
                     If None, returns countries without taste match scores.

    Returns:
        {
            "regions": [
                {
                    "name": "East Asia",
                    "countries": [
                        {
                            "code": "KR", "name": "South Korea", "flag": "🇰🇷",
                            "genres": {"Thriller": 0.9, ...},
                            "labels": ["K-Drama", "Hallyu"],
                            "notable": "...",
                            "taste_match": 0.82
                        }, ...
                    ]
                }, ...
            ]
        }
    """
    regions = []
    for region_name, codes in REGIONS:
        countries = []
        for code in codes:
            cp = COUNTRY_MAP.get(code)
            if not cp:
                continue
            entry = {
                "code": cp.code,
                "name": cp.name,
                "flag": cp.flag,
                "genres": cp.genres,
                "labels": cp.labels,
                "notable": cp.notable,
                "taste_match": compute_taste_match(user_genres, cp) if user_genres else None,
            }
            countries.append(entry)
        regions.append({"name": region_name, "countries": countries})
    return {"regions": regions}
