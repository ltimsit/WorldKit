# worldkit — outil de worldbuilding pour MJ-auteur de JDR

Outil privé et local : un wiki de l'univers adossé à un graphe versionné, alimenté par ingestion de textes et par édition structurée, avec une couche scénario (pistes, déroulés) qui fait évoluer l'univers en branches. Le wiki est lu par des humains ; un LLM consomme le graphe. Objectif prioritaire : des univers petits ou persistants, construits progressivement.

`worldkit` est un nom provisoire (outil et commande).

## Documents de référence (dans `docs/`)

Par ordre de priorité en cas de divergence :

1. **`docs/cadre-fondation.md`** — base de vérité du modèle conceptuel. Règles `R-XXX-nn`, invariants (§9), périmètre (§1.4), glossaire FR ↔ EN (§3).
2. **`docs/cadre-technique.md`** — décisions techniques `T-XXX-nn` (toutes validées), modules M1–M11, impact du noyau sur l'ingestion (§5), stratégie de test, jalons J0–J8.
3. **`docs/analyse-structuration-narrative-jdr.md`** — document historique : le *pourquoi* des décisions. À consulter pour le contexte, jamais pour les règles.

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
- Ensuite : J6 (pistes, scénarios, déroulés), J7 (rejeu rétroactif), J8 (méta), second jet du corpus… (cadre technique §7).
- Points ouverts à trancher avant J8 : lacunes L1, L2, L6 du corpus (`corpus/valmont-v1/README.md` §5).

## Git

Branche par jalon (`j1-schema`, …). Commits petits, message en français avec les identifiants de règles concernés. Ne pousse que si on te le demande.
