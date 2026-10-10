# worldkit — outil de worldbuilding pour MJ-auteur de JDR

Outil privé et local : un wiki de l'univers adossé à un graphe versionné, alimenté par ingestion de textes et par édition structurée, avec une couche scénario (pistes, déroulés) qui fait évoluer l'univers en branches. Le wiki est lu par des humains ; un LLM consomme le graphe. Objectif prioritaire : des univers petits ou persistants, construits progressivement.

`worldkit` est un nom provisoire (outil et commande).

## Documents de référence (dans `docs/`)

Par ordre de priorité en cas de divergence :

1. **`docs/cadre-fondation.md`** — base de vérité du modèle conceptuel. Règles `R-XXX-nn`, invariants (§9), périmètre (§1.4), glossaire FR ↔ EN (§3).
2. **`docs/cadre-technique.md`** — décisions techniques `T-XXX-nn` (toutes validées), modules M1–M11, impact du noyau sur l'ingestion (§5), stratégie de test, jalons J0–J8.
3. **`docs/cadre-interface.md`** — interface conçue comme banc d'essai : objectifs, principes, étapes du pipeline, espaces, indicateurs ; décisions `I-XXX-nn`, questions `QI-nn`.
   - **`docs/aide/`** — documents d'aide, lus par le lexique (`/aide`, `worldkit explain`) : `glossaire.md` (statuts, codes de signalement, valeurs affichées, exécutions, parcours, mesures), `outils.md` (carte des outils : une ligne par écran), `guide.md` (guide pas à pas, **exécuté par `tests/test_guide.py`** : blocs ```powershell exécutés, ```text sortie vérifiés, ```yaml fichier=X écrits, `<!-- écran /adresse : "texte" -->` vérifiés ; ```powershell sans-test pour ce qui ne doit pas tourner). Ils complètent les cadres sans les répéter.
4. **`docs/analyse-structuration-narrative-jdr.md`** — document historique : le *pourquoi* des décisions. À consulter pour le contexte, jamais pour les règles.
5. **`docs/chantier-ingestion.md`** — document de travail : faire évoluer l'ingestion pour de **petits modèles** (couches spécialisées, annotations comme monnaie d'échange, Atelier d'ingestion, magasin d'atelier, Haiku comme substitut, indicateurs par couche). Méthode, choix faits, pistes, questions ouvertes, prochaines étapes. **À lire avant de reprendre ce chantier.** Un choix acté passe dans les cadres et sort de ce document.
   - **`docs/recherche-ingestion/`** — journal de recherche : fiches d'écart `E-nnn` et d'expérience `X-nnn` (modèles dans son `README.md`). Tout écart qui coûte de la revue reçoit une fiche ; « prendre un meilleur modèle » n'est pas un remède.

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
   - **aide et guide** (`docs/aide/`) : toute fonctionnalité nouvelle ou modifiée met à jour, dans le même jalon, le glossaire complémentaire et la carte des outils (si un statut, un code, une valeur, un écran ou une opération apparaît) **et le guide pas à pas** (`docs/aide/guide.md`) : nouvel usage, commande, écran ou lecture de résultat. Le guide est exécuté par `tests/test_guide.py` : ses commandes et ses sorties annoncées doivent rester vraies ;
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
- `valmont/walkthroughs/walkthroughs.yaml` : parcours W00–W17, chacun rattaché à un jalon, avec résultats attendus — ce sont les **tests d'acceptation**, exécutables (`worldkit walkthrough run W15`, format au README du corpus §3) ; attendus structurés : W08, W15 ;
- `valmont/questions.yaml` : questions de compétence par vue ;
- second corpus, **ciblé** : `corpus/corbelle-v1/` (notes brouillon, voir son `README.md`), cohérence vérifiée par `tests/test_corpus_corbelle.py` ; axes de test et plan des corpus : `docs/recherche-ingestion/axes-corpus.md` (un corpus écrit par Claude sert à construire les couches, jamais à choisir le modèle, T-TST-01) ;
- `tools/check_corpus.py` : contrôle de cohérence du corpus lui-même (à lancer après toute modification du corpus).
- **mondes de l'auteur** : `mondes/` (voir son `README.md`), distincts des corpus : un corpus est un instrument de mesure (schéma, gold, tests inchangés), un monde d'auteur évolue. `mondes/corbelle/` = le corpus Corbelle plus cinq relations ajoutées par l'auteur (`on_river`, `runs`, `near`, `hates`, `conspires_with`) ; le corpus les garde hors schéma (E-007). Repartir de zéro : commandes du `README.md` (`corbelle.db`). Cohérence : `tests/test_mondes.py`.

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
- **I5 — fait** (branche `i5-revue`) : écran de revue `/review` (session du monde de travail), parcours exécutables (`worldkit/service/walkthroughs.py`, `walkthrough.run`, `/acceptance`, `worldkit walkthrough run W15`), format exécutable du corpus (identifiants réels, `requires`, vérifications typées), W15 et W08 structurés, 18 parcours exécutables (I-REV-01, I-REV-02, I-ACC-02, I-ACC-03). Fiche : `docs/i5-brief.md`.
- **I6 — fait** (branche `i6-graphe`) : graphe `/graph` (`graph.view`, `graph.compare`, Cytoscape.js), mesures T2 `/measures` (`eval.run`, `eval.history`, `eval.compare`) (I-GRA-02, I-MES-01). Fiche : `docs/i6-brief.md`. **Interface complète (I0 à I6).**
- **I7 — fait** (branche `i7-aide`) : aide (I-AID-01) — lexique lu dans les documents (`worldkit/service/lexicon.py`, `lexicon.lookup`, `lexicon.index`), `docs/aide/`, page `/aide`, codes liés avec définition au survol, fiche de chaque écran, `worldkit explain R-NOT-07` ; guide pas à pas `/aide/guide` exécuté par les tests (I-AID-02). Test de complétude (`tests/test_i7_aide.py`) : **tout nouveau statut, code de signalement, valeur affichée, étape, opération, écran ou identifiant cité doit recevoir sa définition** (dans un cadre ou `docs/aide/`), sinon la suite échoue.
- **I9 — fait** (branche `atelier-rattacher-nouvelle`) : atelier, deuxième incrément (les faits) : couche « faits » (`layers.run_facts`, chaîne partagée `facts_chain`), faits sous les passages avec pastilles, gestes sur un fait (`gestures.fact_gesture`), « Proposer » avec les faits ou second lot `…-faits` (I-ATL-06 à I-ATL-08). Fiche : `docs/i9-brief.md`. Aussi sur cette branche : rattacher une forme à une entité nouvelle de la source (E-014), expériences X-013 à X-016 (pivot « fantasy jdr » non adopté, cache confirmé), proposition `docs/proposition-schemas-de-genre.md` (non actée).
- **I8 — fait** (branche `i8-atelier`) : atelier d'ingestion, premier incrément (les entités) : magasin d'atelier en ajout seul lu par lignée (`atelier_sources`, `annotations`, `atelier_rules`), import d'un texte, couche « mentions » (C1a, C1b en option, C2), gestes de l'auteur et portées (occurrence, source, monde), règles d'atelier, « Proposer » vers la revue (`worldkit/atelier/`, opérations `atelier.*`, écran `/atelier`) (I-ATL-01 à I-ATL-05). Fiche : `docs/i8-brief.md`. Deuxième incrément : I9.
- **Ce que disent les documents — fait** (branche `wiki-passages`) : niveau 1 du chantier §10.6 : sur la page d'auteur, les passages des documents ingérés qui nomment l'entité, sans modèle (noms connus, corrigés par l'atelier), repère capté / non capté / affirmation, forme en casse différente à vérifier, rien en vue joueur (`worldkit/ingest/passages.py`, R-VUE-05, T-ING-21). Formes courtes des personnes (« Odon », « Ysolde ») : règle B de X-003, à vérifier, jamais un prénom partagé (choix 40), dans ces passages et dans la couche « mentions » de l'atelier (branche `formes-courtes`).
- **Écran Schéma — fait** (branche `schema-ecran`) : `/schema`, `schema.show`, `worldkit schema show` : schéma projeté à une branche et un point, relations de → vers, cardinalités, systèmes et fiches exigées, usage, provenance relue dans le journal, diagramme Mermaid (I-VUE-12). L'atelier montre aussi une étiquette sous chaque mention (pourquoi elle est liée, ou la décision de l'auteur et sa portée, I-ATL-05) et vérifie le schéma à la correction d'un fait (R-SCH-02).
- **Ajouter au schéma — fait** (branche `ajouter-au-schema`) : depuis un fait de l'atelier ou un changement hors schéma de la revue, formulaire `/schema/add` prérempli, aperçu puis confirmation, écriture au journal du monde, fait rattaché (`schema.add_relation`, I-ATL-09) ; `worldkit schema export --out` pour reporter le schéma projeté dans un monde d'auteur. Bilan de la première session réelle : X-017.
- **Chantier ingestion — en cours** : étape 1 fusionnée (adaptateur `claude-code` isolé, mesure T2 corrigée, clé d'API propre `WORLDKIT_ANTHROPIC_API_KEY`). Réorientation (v0.3 du chantier, branche `chantier-ingestion-atelier`) : cible petits modèles, méthode par écart, couches C0 à C6 sur un tableau d'annotations partagé, **fenêtre large et question étroite** (C1 sans liste connue, entités confirmées avant les faits, §6.5), Atelier, Haiku 4.5 par l'API comme substitut (conditions au §8). Mesure de référence X-001 faite ; prochaine expérience X-002 (C1 et C2 sur b1). Prochaines étapes au §16. Traces des appels : `WORLDKIT_LLM_LOG_DIR` (dossier `llm-log/`, ignoré par git).
- **Prochain, côté auteur** : tests humains à l'écran (curation chronométrée de b1, retcon d'Aldren, Loup sous deux systèmes, comparaison réelle de deux modèles — consomme le quota) ; second jet du corpus (choix du LLM, T-TST-01). Côté code : structurer les attendus des parcours restants au fil des besoins (I-ACC-03).
- R-SCH-09 appliqué aux termes du schéma (branche `libelles`) : wiki (Markdown et web), graphe, revue (ligne en français sous chaque changement) affichent « libellé (identifiant) » ; l'export JSON pour le LLM garde les identifiants. Reste : les termes de la plateforme (notoriété, statuts) dans le Markdown, traduits à l'écran seulement (lexique, `explain`).
- Lacunes L1, L2, L6 du corpus tranchées avant J8 (cadre R-MET-02, R-MET-04, T-FAI-01 ; analyse 00.50) : toutes les lacunes du corpus v1 sont closes.

## Carte du code

| Module | Chemin | Rôle |
|---|---|---|
| M1 schéma | `worldkit/core/schema/` | méta-schéma, validateur, changements (catalogue), clés de fait, vérification, conformité |
| M2 journal | `worldkit/core/journal/` | éditions (`models.py`), stockage SQLite en ajout seul (`store.py`), lignée des branches |
| M3 projection | `worldkit/core/projection/` | état (`state.py`), application d'un changement, forme canonique (`serialize.py`) |
| M4 conflits | `worldkit/core/conflicts/` | collisions, lectures/écritures (`application.py`), transposition (`transposition.py`) |
| M5 workflows | `worldkit/core/workflows/` | scénarios, pistes d'auteur, déroulés (`scenarios.py`) ; redéfinition rétroactive et rejeu (`replay.py`) |
| M10–M11 vues | `worldkit/core/views/` | notoriété effective, pages (dont « ce que disent les documents », fournis par `ingest/passages.py`), rendu Markdown, export JSON, signalements |
| Façade | `worldkit/core/world.py` | `World` : créer, appliquer, soumettre, confirmer, rebaser, branches, transposer |
| M6–M9 ingestion | `worldkit/ingest/` | déclaration et passages, pipeline en étapes (`stages.py`, `ingest` dans `batch.py`), propositions, file de revue vivante, décisions ; méta : nature, questions de nature, `sheet_values` (`meta.py`) ; report des propositions en fin de rejeu (`carry.py`) |
| Périphérie | `worldkit/periphery/` | extracteur oracle, adaptateurs LLM et profils (`llm/`), extracteur LLM, mesure T2 |
| Atelier | `worldkit/atelier/` | magasin d'atelier (`store.py`), couches qui écrivent des annotations (`layers.py`), gestes et portées (`gestures.py`), « Proposer » (`propose.py`) ; mentions et recoupement dans `worldkit/periphery/{mentions,matching,facts}.py` |
| Service | `worldkit/service/` | registre d'opérations (`registry.py` ; opérations dans `ops.py`, `pipeline.py`, `walkthroughs.py`, `graph.py`, `measures.py`, `lexicon.py`, `atelier.py`, `schema.py`), `Session.call` (`session.py`), `Result` (`result.py`), exécutions et bacs (`runs.py`), tâches de fond (`jobs.py`), commandes `ops`/`call`/`sandbox`/`runs`/`run`/`runs-diff`/`walkthrough` (`cli.py`) ; `worldkit ops` liste tout |
| Web | `worldkit/web/` | application FastAPI (`app.py`) et écrans : saisie et banc (`actions.py`), pipeline (`pipeline.py`), revue et acceptation (`review.py`), graphe (`graph.py`), mesures (`measures.py`), aide et filtres `explain`/`linkify` (`help.py`), atelier (`atelier.py`) ; gabarits Jinja (`templates/`) ; htmx, Mermaid et Cytoscape.js copiés (`static/`) |
| CLI | `worldkit/cli.py` | `worldkit --db monde.db <commande>` ; `worldkit --help` ; `worldkit ops` ; `worldkit serve` |

Tests : `tests/` ; aides dans `tests/support.py` (`base_world`, `edit`, `rel`…), `tests/test_w10_w11.py` (`after_w05` : état après la revue de W05) et `tests/test_w15_replay.py` (`setup_w15`, `file_world` : état de départ de W15, en mémoire ou sur fichier).

La branche de référence n'est plus forcément `reference` : après un rejeu, c'est la dernière de l'historique des références (`world.reference_branch`). Une branche archivée refuse toute édition.

## Commandes et environnement

- Environnement : `.venv` (Python 3.12) ; interface : `pip install -e .[ui]` (FastAPI, Uvicorn, Jinja2), puis `worldkit --db monde.db serve`. Tests : `.venv\Scripts\python -m pytest -q` (tous doivent passer ; aucun n'appelle un vrai modèle). Corpus : `cd corpus/valmont-v1; ..\..\.venv\Scripts\python tools/check_corpus.py`.
- Windows, PowerShell 5.1 : `@base` doit s'écrire `'@base'` ou `base` (le `@` est facultatif) ; `0,1` devient deux arguments (les options d'indices l'acceptent) ; les guillemets d'un argument JSON passé à un exécutable natif sont mangés (passer par Python).
- LLM : l'adaptateur `claude-code` appelle `claude -p` avec l'abonnement de l'auteur (usage personnel), binaire natif trouvé derrière le lanceur npm (`%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe`) ou dans l'extension VS Code, ou désigné par `WORLDKIT_CLAUDE_BIN` ; appel isolé (prompt par fichier, ni MCP, ni compétences, ni réglages, dossier vide : environ 4 900 tokens par appel au lieu de 39 000, T-LLM-01). `worldkit-llm.yaml` est personnel (ignoré par git). L'auteur passe à l'API pour mesurer dans des conditions proches de l'usage attendu : `anthropic-api` (SDK `anthropic` dans les dépendances), clé dans la variable d'environnement utilisateur `WORLDKIT_ANTHROPIC_API_KEY` (pas `ANTHROPIC_API_KEY`, que Claude Code utiliserait aussi ; l'adaptateur `claude-code` la retire de l'environnement de `claude -p`), **jamais** dans un fichier du dépôt ni dans la conversation ; facturé au token. Sa machine ne fait pas tourner de modèle local (`ollama` préparé, inutilisé) ; utiliser le jeton de l'abonnement directement contre l'API est exclu. Profils : copier `worldkit-llm.example.yaml` en `worldkit-llm.yaml`. Une mesure `worldkit eval extraction` consomme le quota ou coûte : demander avant d'en lancer une, avec l'estimation du nombre d'appels (et du coût en mode API).
- Pour modifier un fichier par script, écrire le script dans le dossier temporaire de session puis l'exécuter : les apostrophes françaises cassent les here-docs de bash.
- Un script `.ps1` contenant des accents doit être enregistré en UTF-8 **avec BOM** : PowerShell 5.1 lit sinon le fichier en ANSI (« fièvre » devient « fiÃ¨vre »).

## Façon de travailler (établie)

- Chaque jalon : lire la fiche et le cadre, proposer un plan, poser les questions **une par une** avec options A/B et recommandation, coder par étapes testées et commitées, puis mettre à jour les documents (cadre, analyse 00.xx et question numérotée, CLAUDE.md) et lister dans la réponse les choix faits sans validation.
- Adapter le corpus plutôt que contourner une règle (ex. retrait explicite exigé par R-FAI-05 : e201, x-d3), et le dire.
- Les guides pas à pas donnés à l'auteur sont d'abord exécutés sous PowerShell pour vérifier chaque résultat annoncé.

## Git

Branche par jalon (`j1-schema`, …). Commits petits, message en français avec les identifiants de règles concernés. Ne pousse que si on te le demande.
