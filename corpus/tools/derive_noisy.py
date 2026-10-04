"""Corpus **dérivé** : Valmont b1 bruité par perturbations contrôlées (axes AX-S1, S3, S4, S5, S6).

Reproductible : graine fixe, un tirage par (niveau, document, passage). Les perturbations sont appliquées mot par
mot, en gardant la correspondance entre le texte d'origine et le texte bruité : les mentions du gold sont recalées
sur leur forme bruitée, les débuts de passage aussi ; les changements attendus ne bougent pas (une valeur bien
écrite reste la valeur attendue). Usage, depuis la racine du dépôt :

    .venv\\Scripts\\python corpus/tools/derive_noisy.py

Écrit corpus/valmont-bruite-v1/ (documents, gold et batches.yaml par niveau). Voir son README.
"""

from __future__ import annotations

import random
import re
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "corpus" / "valmont-v1" / "valmont"
TARGET = ROOT / "corpus" / "valmont-bruite-v1"
DOCUMENTS = ["b1/notes-baron.v1.md", "b1/lieux-de-valmont.md"]
GOLD = {"notes-baron": "b1-notes-baron.v1.yaml", "lieux-de-valmont": "b1-lieux-de-valmont.yaml"}

# Taux par mot (ou par signe de ponctuation), par niveau.
LEVELS = {
    "l1": {"typo": 0.15, "lower": 0.25, "accent": 0.3, "abbrev": 0.5, "acronym": 0.5, "punct": 0.3},
    "l2": {"typo": 0.35, "lower": 0.6, "accent": 0.8, "abbrev": 1.0, "acronym": 1.0, "punct": 0.8},
}
SEED = 20261004
ABBREVIATIONS = {"pour": "pr", "beaucoup": "bcp", "avec": "av", "dans": "ds", "toujours": "tjs", "quelque": "qq",
                 "depuis": "dps", "est": "c"}
ACRONYMS = {"conseil des marchands": "CdM", "Cercle des Cendres": "CdC"}


def strip_accents(word: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", word) if not unicodedata.combining(c))


def typo(word: str, rng: random.Random) -> str:
    """Une faute de frappe : lettre doublée, lettre manquante ou deux lettres inversées (jamais la première)."""
    i = rng.randrange(1, len(word) - 1)
    kind = rng.choice(["double", "drop", "swap"])
    if kind == "double":
        return word[:i] + word[i] + word[i:]
    if kind == "drop":
        return word[:i] + word[i + 1:]
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]


def perturb(text: str, rates: dict[str, float], rng: random.Random) -> tuple[str, list[tuple[int, int, int, int]]]:
    """Texte bruité, et les segments (début et fin d'origine, début et fin bruités) pour recaler les portions."""
    out, segments = "", []
    pos = 0
    pattern = re.compile("|".join(re.escape(a) for a in ACRONYMS) + r"|\w+(?:['’-]\w+)*|[^\w\s]|\s+")
    for m in pattern.finditer(text):
        token, start = m.group(0), m.start()
        new = token
        if token in ACRONYMS and rng.random() < rates["acronym"]:
            new = ACRONYMS[token]
        elif token.strip() == "":
            new = token
        elif re.fullmatch(r"[.,;:]", token):
            new = "" if rng.random() < rates["punct"] else token
        elif re.fullmatch(r"\w.*", token):
            if token.lower() in ABBREVIATIONS and rng.random() < rates["abbrev"]:
                new = ABBREVIATIONS[token.lower()]
            else:
                if token[0].isupper() and len(token) >= 5 and rng.random() < rates["typo"]:
                    new = typo(new, rng)
                if new[0].isupper() and rng.random() < rates["lower"]:
                    new = new.lower()
                if rng.random() < rates["accent"]:
                    new = strip_accents(new)
        segments.append((start, start + len(token), len(out), len(out) + len(new)))
        out += new
        pos = m.end()
    return out, segments


def remap(surface: str, original: str, noisy: str, segments: list[tuple[int, int, int, int]]) -> str | None:
    """La forme bruitée d'une portion du texte d'origine (première occurrence, sans casse)."""
    i = original.lower().find(surface.lower())
    if i < 0:
        return None
    j = i + len(surface)
    covered = [s for s in segments if s[0] < j and i < s[1]]
    if not covered:
        return None
    return noisy[covered[0][2]:covered[-1][3]].strip(" .,;:") or None


def derive(target: Path = TARGET) -> None:
    for level, rates in LEVELS.items():
        docs_dir, gold_dir = target / level / "docs" / "b1", target / level / "gold"
        docs_dir.mkdir(parents=True, exist_ok=True)
        gold_dir.mkdir(parents=True, exist_ok=True)
        for rel in DOCUMENTS:
            raw = (SOURCE / "docs" / rel).read_text(encoding="utf-8")
            front, body = re.match(r"(---\n.*?\n---\n)(.*)", raw, re.DOTALL).groups()
            doc_id = re.search(r"^id: (\S+)", front, re.MULTILINE).group(1)
            gold = yaml.safe_load((SOURCE / "gold" / GOLD[doc_id]).read_text(encoding="utf-8"))
            blocks = body.split("\n\n")
            noisy_blocks, by_start = [], {}
            for k, block in enumerate(blocks):
                if block.startswith("#"):
                    noisy_blocks.append(block)
                    continue
                rng = random.Random(f"{SEED}:{level}:{doc_id}:{k}")
                noisy, segments = perturb(block, rates, rng)
                noisy_blocks.append(noisy)
                by_start[block.strip()] = (block, noisy, segments)
            passages = []
            for p in gold["passages"]:
                block, noisy, segments = next(v for b, v in by_start.items() if b.startswith(p["starts_with"]))
                q = dict(p)
                q["starts_with"] = noisy.strip()[:30].rstrip()
                q["mentions"] = {}
                for surface, eid in (p.get("mentions") or {}).items():
                    new = remap(surface, block, noisy, segments)
                    if new:
                        q["mentions"][new] = eid
                q["derived_from"] = p["starts_with"]
                passages.append(q)
            gold["passages"], gold["batch"] = passages, f"{level}-b1"
            gold["derived"] = {"from": f"valmont-v1/{GOLD[doc_id]}", "level": level, "rates": rates, "seed": SEED}
            (docs_dir / Path(rel).name).write_text(front + "\n\n".join(noisy_blocks), encoding="utf-8")
            (gold_dir / GOLD[doc_id]).write_text(
                "# Gold dérivé automatiquement (corpus/tools/derive_noisy.py) : ne pas modifier à la main.\n"
                + yaml.safe_dump(gold, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")
        batches = {"batches": [{"id": f"{level}-b1", "target_branch": "reference",
                                "documents": [f"b1/{Path(r).name}" for r in DOCUMENTS],
                                "purpose": f"Valmont b1 bruité, niveau {level} : {rates}"}]}
        (target / level / "docs" / "batches.yaml").write_text(yaml.safe_dump(batches, allow_unicode=True,
                                                                             sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    derive()
    print(f"écrit : {TARGET}")
