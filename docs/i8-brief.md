# I8 — L'atelier d'ingestion, premier incrément : les entités

**Statut :** fiche de jalon, version 0.1 — 4 octobre 2026. Décisions de l'auteur (Q1 à Q4) actées ; propositions techniques (§3) **à valider** avant de coder.
**Contexte :** le chantier ingestion ([`chantier-ingestion.md`](chantier-ingestion.md)) a construit et mesuré une chaîne en couches (C1 repérage, C2 recoupement, C5 faits, question ciblée, énonciation, critique ; X-001 à X-012). Ces mesures **simulent** l'auteur. X-012 a montré que les cas difficiles (homographes, noms communs, faux rattachements) ne se jugent pas sans lui : une correction faite une fois doit profiter à la suite. Ce jalon rend la chaîne **réelle**, avec l'auteur dans la boucle, en commençant par les entités.

## 1. Objectif

L'auteur importe une source, lance le repérage et le recoupement, voit les mentions surlignées sur le texte, les garde, retire, corrige, ajoute ou ignore, relance, confirme les entités, puis **propose** : un lot part dans le circuit existant (qualification, revue). Ses corrections peuvent valoir pour la source ou pour le monde. Ses gestes sont enregistrés : ce sont enfin de vraies mesures d'effort (T3).

Hors de ce jalon : les faits (C5, question ciblée, énonciation, critique : deuxième incrément), la forme en ligne des annotations (`[texte]{…}`), le recalage après modification du texte (choix 20, il viendra avec l'édition du texte dans l'atelier).

## 2. Décisions de l'auteur

| Q | Décision | Raison |
|---|---|---|
| Q1 | **Premier incrément : les entités** (magasin d'atelier, import, C1 et C2, point d'arrêt, écran Atelier) ; les faits au deuxième | c'est là que sont les cas que les mesures ne tranchent pas |
| Q2 | **Une source de l'atelier est une version de document** (tables `document_versions`, `passages` existantes, texte entier conservé) ; les annotations s'accrochent au passage (document, version, passage, début, fin) | un seul modèle de document : empreintes, cache, ré-ingestion restent valables |
| Q3 | **« Proposer » est un geste explicite** : un lot avec les entités nouvelles confirmées (création, nom) et les alias issus des rattachements, par le circuit existant jusqu'à `/review` | le monde ne reçoit que ce qui est validé, en une fois |
| Q4 | **Trois portées pour une correction** : cette occurrence ; toutes les occurrences de la forme dans la source (par défaut) ; le monde (« retenir ») : positive → alias proposé au journal ; négative (« les veilleurs de nuit ne sont pas les Veilleurs », « vallee n'est pas une entité ») → **règle d'atelier**, par branche, appliquée aux sources futures | apprentissage d'une source à l'autre ; le monde ne reçoit que des faits |

## 3. Propositions techniques (à valider)

**T1 — Tables du magasin d'atelier** (dans le fichier du monde, T-STO-02 ; créées à la demande comme celles de J3) :

| Table | Colonnes | Rôle |
|---|---|---|
| `atelier_sources` | `doc_id`, `version_fp`, `text` (corps entier), `created` | le texte d'une source ; ses passages sont dans `passages` |
| `annotations` | `ann_id`, `branch_id`, `at_seq` (tête de la branche à la création), `doc_id`, `version_fp`, `passage`, `start`, `end` (nuls pour une annotation de passage ou de source), `kind` (`mention`), `value` (JSON : type, entité ou `new`, candidats), `origin` (`author` ou couche et version), `confidence`, `status` (`proposed`, `kept`, `removed`, `corrected`, `ignored`), `replaces` (annotation remplacée), `created` | une annotation, **en ajout seul** : une correction est une nouvelle ligne qui en remplace une autre |
| `atelier_rules` | `rule_id`, `branch_id`, `at_seq`, `form` (forme pliée), `kind` (`not_entity`, `not_entity_of`), `target`, `origin`, `replaces`, `created` | règle d'atelier (Q4, portée « monde », négative) |

**T2 — Lecture par lignée** (choix 16) : une branche voit ses annotations et celles de ses ancêtres créées avant son point de départ (`at_seq` comparé au `fork_seq` de la lignée, comme le journal) ; l'annotation courante est la dernière de sa chaîne de remplacements. Une annotation de l'auteur n'est jamais remplacée par une couche.

**T3 — Couches comme opérations du service** (registre existant, résultat de forme commune) :

| Opération | Effet |
|---|---|
| `atelier.import` | texte collé ou fichier, en-tête (mode, nature, voix, valeurs par défaut) → version de document et source d'atelier |
| `atelier.run` (`layer`: `mentions`) | C1a, C1b (modèle, avec estimation et confirmation, I-LLM-01, en tâche de fond), C2, signaux en doute, règles d'atelier appliquées ; écrit des annotations `proposed` |
| `atelier.annotate` | un geste de l'auteur : garder, retirer, corriger (type, entité, nouvelle), ajouter (portion choisie), ignorer ; portée (occurrence, source, monde) |
| `atelier.view` | la source et ses annotations courantes, pour l'écran et la ligne de commande |
| `atelier.propose` | le lot (Q3) : entités nouvelles confirmées et alias retenus → propositions par le circuit existant |

**Règle de relance** : une couche relancée remplace ses propres annotations `proposed` encore intactes ; elle ne touche ni aux annotations de l'auteur, ni aux portions qu'il a ignorées ; les règles d'atelier s'appliquent à chaque passage.

**T4 — Écran `/atelier`** (FastAPI, Jinja, htmx existants) : liste des sources ; page d'une source : le texte avec les mentions surlignées (couleur par état : connue, nouvelle, doute ; bordure pointillée pour un doute), clic → panneau (candidats et fiche courte, gestes, portée) ; sélection de texte → ajout (un peu de JavaScript, sans bibliothèque) ; barre des couches (lancer, relancer, coût estimé) ; compteur de ce qui reste à revoir ; bouton « Proposer ».

**T5 — « Proposer »** : un extracteur d'atelier rend, par passage, les brouillons tirés des annotations confirmées (`create_entity` et `name` pour une entité nouvelle gardée ; `add_value aliases` pour un rattachement retenu au monde) ; le lot passe par l'ingestion existante (étapes E1 à E9+), sans modèle, avec la provenance par passage.

**T6 — Mesure réelle** : les gestes de l'auteur sont les annotations elles-mêmes (en ajout seul) : leur nombre et leur nature donnent l'effort réel (T3), comparable aux gestes simulés du chantier.

**T7 — Tests** (T1 exacts) : lignée ; ajout seul ; relance qui respecte l'auteur ; règle d'atelier appliquée à une source nouvelle ; « Proposer » qui produit les propositions attendues ; écran (rendu et gestes) ; aucun appel à un vrai modèle.

## 4. Étapes

1. Magasin d'atelier, import, lecture par lignée (service et ligne de commande).
2. `atelier.run` : C1 et C2 écrivent des annotations ; relance ; règles d'atelier.
3. `atelier.annotate` : les gestes et leurs portées ; alias retenus ; règles négatives.
4. `atelier.propose` : le lot, jusqu'à `/review`.
5. Écran `/atelier`.
6. Documents : cadre d'interface (décisions I-ATL), cadre technique (magasin d'atelier), glossaire, carte des outils, guide pas à pas (exécuté par les tests), chantier, CLAUDE.md.

Chaque étape est testée et commitée. Branche `i8-atelier`.
