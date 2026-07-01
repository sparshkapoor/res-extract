"""Words a general English dictionary doesn't reliably know but that are
completely normal in a recipe — loaned ingredient names, technique verbs,
and unit abbreviations. Loaded into spellcheck.py's checker as known words
so it never "corrects" a real ingredient into nonsense."""

CULINARY_TERMS: set[str] = {
    # units / abbreviations
    "tbsp", "tbsps", "tsp", "tsps", "oz", "lb", "lbs", "qt", "qts", "pt", "pts",
    "ml", "mls", "kg", "kgs", "g", "gs", "gal", "gals",
    # techniques
    "julienne", "chiffonade", "brunoise", "blanch", "blanching", "sauté", "saute",
    "sauteed", "sautéed", "deglaze", "deglazing", "emulsify", "emulsified",
    "marinate", "marinated", "marinating", "braise", "braised", "braising",
    "poach", "poached", "poaching", "sear", "seared", "searing", "temper",
    "tempered", "proof", "proofed", "proofing", "knead", "kneaded", "kneading",
    "whisk", "whisked", "fold", "folded", "dice", "diced", "mince", "minced",
    "zest", "zested", "baste", "basted", "render", "rendered", "caramelize",
    "caramelized", "parboil", "parboiled", "brine", "brined", "brining",
    "reduce", "reduced", "reduction", "simmer", "simmered", "simmering",
    "sweat", "sweated", "blanched", "chiffonaded",
    # loanword ingredients / dishes
    "tahini", "harissa", "gochujang", "sriracha", "miso", "mirin", "sambal",
    "gochugaru", "furikake", "panko", "ghee", "paneer", "halloumi", "feta",
    "chorizo", "prosciutto", "pancetta", "guanciale", "burrata", "mascarpone",
    "ricotta", "crema", "tzatziki", "hummus", "falafel", "shawarma", "kimchi",
    "kombucha", "kefir", "quinoa", "farro", "couscous", "polenta", "risotto",
    "gnocchi", "ravioli", "tortellini", "tempeh", "edamame", "wasabi", "nori",
    "dashi", "katsu", "teriyaki", "tamari", "sumac", "zaatar", "allspice",
    "cardamom", "fenugreek", "asafoetida", "turmeric", "paprika", "cumin",
    "coriander", "cilantro", "jalapeno", "jalapeño", "habanero", "poblano",
    "serrano", "chipotle", "adobo", "achiote", "epazote", "masa", "tortilla",
    "salsa", "guacamole", "pico", "queso", "chimichurri", "mole", "pesto",
    "aioli", "remoulade", "bechamel", "béchamel", "roux", "mirepoix", "confit",
    "consomme", "consommé", "fricassee", "ratatouille", "cassoulet",
    "bourguignon", "vinaigrette", "crudites", "crudités", "charcuterie",
    "gratin", "souffle", "soufflé", "quiche", "brioche", "baguette", "focaccia",
    "ciabatta", "sourdough", "croissant", "macaron", "ganache", "meringue",
    "mousse", "panna", "tiramisu", "cannoli", "gelato", "sorbet", "biscotti",
}
