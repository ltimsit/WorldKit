"""M6 : déclaration d'un document et découpage en passages (R-DOC-02, R-ING-01, R-DEC-01, T-ING-10).

- En-tête YAML (niveau 1 de déclaration) : `id`, `mode`, `nature`, `voice` (et `speaker` si
  `in_world`), `visibility` facultative. Les trois axes sont obligatoires (R-ING-01).
- Passages : paragraphes du corps, titres exclus, numérotés à partir de 1 (format du corpus).
  Un passage est identifié par l'empreinte de son contenu normalisé : le découpage est
  déterministe, et un passage inchangé garde son empreinte d'une version à l'autre.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import yaml

from worldkit.core.schema import Visibility


class Mode(StrEnum):
    SOURCE = "source"
    EDIT = "edit"


class Nature(StrEnum):
    DIEGETIC = "diegetic"
    META_SYSTEM = "meta_system"
    META_SHEET = "meta_sheet"
    MIXED = "mixed"


class Voice(StrEnum):
    AUTHOR = "author"
    IN_WORLD = "in_world"


class DeclarationError(ValueError):
    pass


@dataclass(frozen=True)
class Axes:
    mode: Mode
    nature: Nature
    voice: Voice
    speaker: str | None = None
    visibility: Visibility | None = None


@dataclass(frozen=True)
class Passage:
    index: int
    text: str
    fingerprint: str


@dataclass(frozen=True)
class DocumentVersion:
    doc_id: str
    path: str
    fingerprint: str
    axes: Axes
    passages: tuple[Passage, ...]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize(text).encode("utf-8")).hexdigest()[:16]


_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_document(text: str, path: str = "") -> DocumentVersion:
    m = _FRONTMATTER.match(text)
    if not m:
        raise DeclarationError(f"{path} : en-tête YAML absent (--- … ---) ; mode, nature et voice sont requis (R-ING-01)")
    header = yaml.safe_load(m.group(1)) or {}
    missing = [k for k in ("id", "mode", "nature", "voice") if k not in header]
    if missing:
        raise DeclarationError(f"{path} : en-tête incomplet, manquent {', '.join(missing)} (R-DOC-02, R-ING-01)")
    try:
        axes = Axes(Mode(header["mode"]), Nature(header["nature"]), Voice(header["voice"]), header.get("speaker"),
                    Visibility(header["visibility"]) if "visibility" in header else None)
    except ValueError as e:
        raise DeclarationError(f"{path} : axe invalide ({e})") from e
    if axes.voice is Voice.IN_WORLD and not axes.speaker:
        raise DeclarationError(f"{path} : un document in_world nomme son énonciateur (speaker) (R-DOC-02)")
    body = text[m.end():]
    blocks = [b for b in re.split(r"\n\s*\n", body) if b.strip() and not b.lstrip().startswith("#")]
    passages = tuple(Passage(i, normalize(b), fingerprint(b)) for i, b in enumerate(blocks, start=1))
    return DocumentVersion(str(header["id"]), path, fingerprint(body), axes, passages)


def read_document(path: str | Path) -> DocumentVersion:
    return parse_document(Path(path).read_text(encoding="utf-8"), str(path))
