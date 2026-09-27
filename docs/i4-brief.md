# Fiche de démarrage — Jalon I4 : pipeline en étapes, banc de pipeline, coût des modèles

**Cadre :** *cadre-interface.md* v0.5 — I-OBJ-01, I-OBJ-03, I-OBJ-04 ; I-PRI-05, I-PRI-06 ; I-PIP-01 (12 étapes, artefacts JSON typés et réinjectables, `ingest` recomposé) ; I-LLM-01 (estimation exacte, confirmation, plafond `max_calls_per_run`, relevé) ; I-VUE-03 (banc de pipeline) ; §4 (étapes E1 à E12).
**Règles et décisions touchées :** T-ING-01 à T-ING-20 (comportement de l'ingestion inchangé), T-ING-09 (cache d'extraction), T-ING-17 (erreurs d'extraction), T-LLM-01.
**Test humain :** le Loup de cendre sous deux systèmes (J8), de E1 à E12 puis par morceaux : injecter des brouillons écrits à la main en E5, comparer deux extracteurs sur E1 à E4.

---

## 1. Ce que dit le cadre

- **Étapes** (I-PIP-01) : E1 Déclaration, E2 Passages, E3 Nature, E4 Extraction, E5 Traduction, E6 Classement, E7 Résolution, E8 Qualification, E9 Propositions, E10 Revue, E11 Application, E12 Vues. Chaque étape est une fonction du service : artefact d'entrée + état de base → résultat portant l'artefact de sortie ; un modèle pydantic par artefact ; JSON canonique ; YAML accepté en saisie ; E10 prend un artefact « décisions » dans un pipeline scripté.
- **`ingest` devient l'enchaînement des étapes**, vérifié par les tests existants, inchangés.
- **Banc de pipeline** (I-VUE-03) : choisir les étapes (de x à y), les entrées (document, lot, artefact enregistré, saisie), l'extracteur ; pour chaque étape : artefact, indicateurs, durée, signalements.
- **Coût** (I-LLM-01) : avant E4 avec un modèle, estimation exacte (passages absents du cache), confirmation, plafond par exécution, relevé des appels.

## 2. Ce qui existe et se réutilise

- `ingest` (`worldkit/ingest/batch.py`) fait E1 à E9 d'un bloc : déclaration, passages, extraction et cache, garde de classement et questions de nature (`meta.py`), regroupement des entités nouvelles, qualification et assemblage (`proposals.py`), concurrence entre lots, mémoire des décisions, puis enregistrement.
- Extracteurs : oracle, LLM (`llm_extractor.py`), `CachedExtractor` ; profils et adaptateurs (`periphery/llm`).
- Service : registre, exécutions enregistrées, bacs, `review.*`, `wiki.*`, `state.check`.

## 3. Points à trancher avec l'auteur (une question à la fois)

1. **Quand le pipeline écrit-il ?** Les étapes E1 à E9 sont aujourd'hui mêlées d'écritures (cache, passages, lot, propositions). Faut-il des étapes pures jusqu'à E9, l'enregistrement du lot devenant un acte explicite ?
2. **Exécutions longues** : une extraction par un modèle prend des minutes ; exécution dans la requête (page qui attend) ou en tâche de fond avec suivi de progression ?
3. **Comparer deux exécutions** (diff étape par étape) : dès I4, ou avec les mesures en I6 ?

## 4. Définition de « fini »

- Étapes E1 à E12 exposées par le service (`stage.run`, `pipeline.run` de x à y), artefacts typés, enregistrés, réinjectables ; `ingest` recomposé, les 385 tests existants passent sans modification.
- T1 : pipeline E1→E9 identique à l'ancien `ingest` sur tous les lots du corpus ; une étape déterministe rejouée donne le même artefact.
- Extracteur LLM dans le pipeline avec contrôle du coût (estimation, confirmation, plafond, relevé) ; aucun test n'appelle un vrai modèle.
- Banc de pipeline dans l'interface et en ligne de commande (`worldkit run stages --from E5 --to E9 …`).
- Guide PowerShell et test humain ; documents mis à jour.
