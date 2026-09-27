# worldkit — outil de worldbuilding pour MJ-auteur de JDR

Outil privé et local : un wiki de l'univers adossé à un graphe versionné, alimenté par ingestion de textes et par édition structurée, avec une couche scénario (pistes, déroulés) qui fait évoluer l'univers en branches. Le wiki est lu par des humains ; un LLM consomme le graphe. Objectif prioritaire : des univers petits ou persistants, construits progressivement.

`worldkit` est un nom provisoire (outil et commande).

## Documents de référence (dans `docs/`)

Par ordre de priorité en cas de divergence :

1. **`docs/cadre-fondation.md`** — base de vérité du modèle conceptuel. Règles `R-XXX-nn`, invariants (§9), périmètre (§1.4), glossaire FR ↔ EN (§3).
2. **`docs/cadre-technique.md`** — décisions techniques `T-XXX-nn` (toutes validées), modules M1–M11, impact du noyau sur l'ingestion (§5), stratégie de test, jalons J0–J8.
3. **`docs/cadre-interface.md`** — interface conçue comme banc d'essai : objectifs, principes, étapes du pipeline, espaces, indicateurs ; décisions `I-XXX-nn`, questions `QI-nn`.
4. **`docs/analyse-structuration-narrative-jdr.md`** — document historique : le *pourquoi* des décisions. À consulter pour le contexte, jamais pour les règles.

Lis le cadre concerné **avant** de coder une fonctionnalité. Ne devine pas une règle : cherche son identifiant.

## Principe d'architecture (T-ARC-01 à 03, validé)

- **Noyau déterministe** (`worldkit/core/…`) : schéma, journal, branches, projection, notoriété, clés de fait, collisions, dépendances, vues. **Aucun appel à un LLM.** Même entrée → même sortie.
- **Périphérie probabiliste** (extraction, résolution d'entités, détection d'indices) : derrière un adaptateur unique (`LLMAdapter`). Elle n'écrit **jamais** dans l'état : elle produit des propositions (`Proposal`).
- **Les contradictions sont détectées par le noyau**, par collision de clés de fait (R-FAI-05), jamais par un LLM.
- **L'historique ne fait que s'allonger** (R-HIS-01) : journal d'éditions en ajout seul ; un état est une projection ; aucune édition appliquée n'est modifiée ni retirée (R-CYC-01).

## Choix techniques validés

Python ; pydantic pour le méta-schéma et le validateur unique (T-SCH-01) ; SQLite, un fichier par monde (T-STO-02) ; tests avec pytest et *hypothesis* ; ligne de commande d'abord (T-LNG-01) ; noyau sur mesure, pas de framework de graphe de connaissances (T-FWK-01) ; `branch_id` présent partout dès J2 (T-BRA-01).

## Règles de travail

1. **Contredis quand c'est justifié.** Si une implémentation entre en tension avec une règle ou un invariant, dis-le en citant l'identifiant (ex. R-HIS-01, invariant 4) et présente deux voies — s'adapter au cadre, ou faire évoluer le cadre — avec une recommandation. Ne tords pas silencieusement le code ni le cadre.
2. **Cite les identifiants** (`R-XXX-nn`, `T-XXX-nn`) dans les docstrings, les noms ou docstrings de tests et les messages de commit quand un choix en dépend.
3. **Respecte le périmètre** (cadre §1.4) : ce qui est « préparé » doit rester possible (champs acceptés, conservés, ignorés) ; ce qui est « hors périmètre » ne se construit pas.
4. **Une question à la fois**, avec des options concrètes et un exemple tiré de Valmont (Brume, le baron Odon, Aldren, le Loup de cendre, la Chronique de la Chute).
5. **Sur un point technique non tranché, propose une solution argumentée** (choix, alternatives écartées, pourquoi) et attends la validation avant de l'acter dans les documents.
6. **La solution la plus simple** compatible avec la vision ; fondation minimale et extensible.
7. **Mise à jour des documents** :
   - documents de cadre : reflètent la vision la plus récente, sans historique interne ; conserver les identifiants des règles qui subsistent, ne jamais réutiliser l'identifiant d'une règle supprimée ; incrémenter la version ;
   - analyse : document historique ; incrémenter la version, ajouter une section 00.xx qui trace la décision (problème, voies comparées, décision) et une question numérotée ;
   - dans ta réponse (pas dans le document), liste les changements et les choix faits sans validation explicite.
8. **Nommage technique en anglais** (code, types, champs, opérations, énumérations, clés de configuration) ; prose, commentaires explicatifs et documents en **français**. Tenir le glossaire FR ↔ EN à jour.
9. **Diagrammes en Mermaid**, vérifiés syntaxiquement quand c'est possible.
10. **Réponds en français.**

## Tests

- **T1 — exacts** : propriétés et invariants du noyau (déterminisme, commutation des éditions indépendantes, aucun fait non public dans une vue publique…). Bloquants.
- **T2 — statistiques** : qualité de l'extraction contre le gold du corpus. Indicatifs.
- **T3 — humains** : questions de compétence, sessions de curation chronométrées.

Le corpus de test est `corpus/valmont-v1/` (voir son `README.md`) :
- `schemas/` et `valmont/` : schémas, vérité structurée, documents par lots, annotations `gold/`, scénarios ;
- `valmont/walkthroughs/walkthroughs.yaml` : parcours W00–W17, chacun rattaché à un jalon, avec résultats attendus — ce sont les **tests d'acceptation** ;
- `valmont/questions.yaml` : questions de compétence par vue ;
- `tools/check_corpus.py` : contrôle de cohérence du corpus lui-même (à lancer après toute modification du corpus).

Les formats du corpus (éditions, gold, parcours) sont **provisoires** : si l'implémentation impose un autre format, propose l'adaptation plutôt que de contourner.

## État d'avancement

- **J0 — fait** : corpus synthétique v1.
- **J1 — fait** (branche `j1-schema`) : validateur de schéma, clés de fait, vérification des changements et de la conformité (`worldkit/core/schema/`). Fiche : `docs/j1-brief.md`.
- **J2 — fait** (branche `j2-journal`) : journal SQLite, projection, collisions et péremption, wiki d'auteur et joueur, export (`worldkit/core/{journal,projection,conflicts,views}`, `worldkit/core/world.py`).
- **J3 — fait** (branche `j3-ingestion`) : lots, passages, extracteur oracle, propositions qualifiées, revue et décisions, affirmations, ré-ingestion, documents obsolètes (`worldkit/ingest/`, `worldkit/periphery/`).
- **J4 — outillage fait** (branche `j4-extraction`) : adaptateurs LLM (`claude-code` avec l'abonnement, `anthropic-api`, `ollama`), profils routés par tâche (`worldkit-llm.yaml`), extracteur LLM, mesure T2 (`worldkit eval extraction`). Le choix du modèle attend le second jet du corpus, écrit par l'auteur (T-TST-01).
- **J5 — fait** (branche `j5-branches`) : branches, redéfinition ponctuelle et R-VUE-03, transposition d'éditions (indépendante, dépendante, contradictoire), déplacement de propositions. La transposition de scénario (fin de W13) arrive avec J6.
- **J6 — fait** (branche `j6-scenarios`) : scénarios versionnés, pistes d'auteur, déroulés, transposition de scénario, pistes ouvertes sur les pages (`worldkit/core/workflows/`).
- **J7 — fait** (branche `j7-replay`) : redéfinition rétroactive (T-RED-01) — aperçu d'impact, session de rejeu suspendable, reprenable et abandonnable, bascule de la référence (historique en ajout seul), ancienne branche archivée, report des points, pistes, propositions et déroulés, variantes signalées (`worldkit/core/workflows/replay.py`, `worldkit/ingest/carry.py`).
- **J8 — fait** (branche `j8-meta`) : méta à l'ingestion (T-ING-20) — nature des passages, garde de classement, questions de nature (`worldkit review nature`), formes réduites LLM `sheet_values` / `schema_constraint`, T2 étendu au méta (`worldkit/ingest/meta.py`). Fiche : `docs/j8-brief.md`. La mesure T2 réelle du méta attend l'accord de l'auteur (quota).
- **I0 — fait** : cadre d'interface validé (`docs/cadre-interface.md` v0.2, décisions I-TEC-01 à I-LLM-01).
- **I1 — fait** (branche `i1-service`) : couche de service (`worldkit/service/`), registre d'opérations, résultat de forme commune, exécutions `monde.runs.db`, bacs à sable ; commandes `ops`, `call`, `sandbox`, `runs` (I-SVC-01 à I-SVC-04). Fiche : `docs/i1-brief.md`.
- **I2 — fait** (branche `i2-lecture`) : application web locale en lecture (`worldkit/web/`, `worldkit serve`) : tableau de bord, wiki, comparaison de deux lectures (`wiki.compare`), branches, journal, exécutions (I-WEB-01 à I-WEB-03). Fiche : `docs/i2-brief.md`.
- **I3 — fait** (branche `i3-saisie`) : éditeur YAML vérifié en direct (`/editor`), banc de mécanismes (`/bench`), rendre réel un bac (`sandbox.promote`, `worldkit sandbox promote N [--yes]`), rejeu exposé par le service ; écriture dans un bac par défaut (I-ACT-01 à I-ACT-04). Fiche : `docs/i3-brief.md`.
- **I4 — fait** (branche `i4-pipeline`) : ingestion découpée en étapes (`worldkit/ingest/stages.py`, E1 à E9 purs, E9+ Enregistrer), `pipeline.run` / `pipeline.save` / `pipeline.estimate` / `runs.diff`, tâches de fond (`worldkit/service/jobs.py`), banc de pipeline `/pipeline`, commandes `run stages`, `run save`, `runs-diff` (I-PPL-01 à I-PPL-04). Fiche : `docs/i4-brief.md`.
- **Prochain : I5** (revue complète : propositions, questions de nature, rejeu ; parcours exécutables, W15 et W08 d'abord). En parallèle, côté auteur : second jet du corpus (choix du LLM, T-TST-01).
- Lacunes L1, L2, L6 du corpus tranchées avant J8 (cadre R-MET-02, R-MET-04, T-FAI-01 ; analyse 00.50) : toutes les lacunes du corpus v1 sont closes.

## Carte du code

| Module | Chemin | Rôle |
|---|---|---|
| M1 schéma | `worldkit/core/schema/` | méta-schéma, validateur, changements (catalogue), clés de fait, vérification, conformité |
| M2 journal | `worldkit/core/journal/` | éditions (`models.py`), stockage SQLite en ajout seul (`store.py`), lignée des branches |
| M3 projection | `worldkit/core/projection/` | état (`state.py`), application d'un changement, forme canonique (`serialize.py`) |
| M4 conflits | `worldkit/core/conflicts/` | collisions, lectures/écritures (`application.py`), transposition (`transposition.py`) |
| M5 workflows | `worldkit/core/workflows/` | scénarios, pistes d'auteur, déroulés (`scenarios.py`) ; redéfinition rétroactive et rejeu (`replay.py`) |
| M10–M11 vues | `worldkit/core/views/` | notoriété effective, pages, rendu Markdown, export JSON, signalements |
| Façade | `worldkit/core/world.py` | `World` : créer, appliquer, soumettre, confirmer, rebaser, branches, transposer |
| M6–M9 ingestion | `worldkit/ingest/` | déclaration et passages, pipeline en étapes (`stages.py`, `ingest` dans `batch.py`), propositions, file de revue vivante, décisions ; méta : nature, questions de nature, `sheet_values` (`meta.py`) ; report des propositions en fin de rejeu (`carry.py`) |
| Périphérie | `worldkit/periphery/` | extracteur oracle, adaptateurs LLM et profils (`llm/`), extracteur LLM, mesure T2 |
| Service | `worldkit/service/` | registre d'opérations (`registry.py`, `ops.py`), `Session.call` (`session.py`), `Result` (`result.py`), exécutions et bacs (`runs.py`), commandes `ops`/`call`/`sandbox`/`runs` (`cli.py`) |
| Web | `worldkit/web/` | application FastAPI (`app.py`), gabarits Jinja (`templates/`), style, htmx et Mermaid copiés (`static/`) ; lecture seule jusqu'à I3 |
| CLI | `worldkit/cli.py` | `worldkit --db monde.db <commande>` ; `worldkit --help` ; `worldkit ops` ; `worldkit serve` |

Tests : `tests/` ; aides dans `tests/support.py` (`base_world`, `edit`, `rel`…), `tests/test_w10_w11.py` (`after_w05` : état après la revue de W05) et `tests/test_w15_replay.py` (`setup_w15`, `file_world` : état de départ de W15, en mémoire ou sur fichier).

La branche de référence n'est plus forcément `reference` : après un rejeu, c'est la dernière de l'historique des références (`world.reference_branch`). Une branche archivée refuse toute édition.

## Commandes et environnement

- Environnement : `.venv` (Python 3.12) ; interface : `pip install -e .[ui]` (FastAPI, Uvicorn, Jinja2), puis `worldkit --db monde.db serve`. Tests : `.venv\Scripts\python -m pytest -q` (tous doivent passer ; aucun n'appelle un vrai modèle). Corpus : `cd corpus/valmont-v1; ..\..\.venv\Scripts\python tools/check_corpus.py`.
- Windows, PowerShell 5.1 : `@base` doit s'écrire `'@base'` ou `base` (le `@` est facultatif) ; `0,1` devient deux arguments (les options d'indices l'acceptent) ; les guillemets d'un argument JSON passé à un exécutable natif sont mangés (passer par Python).
- LLM : l'adaptateur `claude-code` appelle `claude -p` avec l'abonnement de l'auteur (usage personnel), binaire trouvé dans l'extension VS Code. Une mesure `worldkit eval extraction` consomme le quota : demander avant d'en lancer une complète.
- Pour modifier un fichier par script, écrire le script dans le dossier temporaire de session puis l'exécuter : les apostrophes françaises cassent les here-docs de bash.
- Un script `.ps1` contenant des accents doit être enregistré en UTF-8 **avec BOM** : PowerShell 5.1 lit sinon le fichier en ANSI (« fièvre » devient « fiÃ¨vre »).

## Façon de travailler (établie)

- Chaque jalon : lire la fiche et le cadre, proposer un plan, poser les questions **une par une** avec options A/B et recommandation, coder par étapes testées et commitées, puis mettre à jour les documents (cadre, analyse 00.xx et question numérotée, CLAUDE.md) et lister dans la réponse les choix faits sans validation.
- Adapter le corpus plutôt que contourner une règle (ex. retrait explicite exigé par R-FAI-05 : e201, x-d3), et le dire.
- Les guides pas à pas donnés à l'auteur sont d'abord exécutés sous PowerShell pour vérifier chaque résultat annoncé.

## Git

Branche par jalon (`j1-schema`, …). Commits petits, message en français avec les identifiants de règles concernés. Ne pousse que si on te le demande.
