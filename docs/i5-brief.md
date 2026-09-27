# Fiche de démarrage — Jalon I5 : revue complète, parcours d'acceptation exécutables

**Cadre :** *cadre-interface.md* v0.6 — I-OBJ-01, I-OBJ-05, I-OBJ-06 ; I-VUE-05 (revue : propositions, questions de nature, rejeu, aperçu d'impact) ; I-ACC-01 (parcours exécutables pas à pas dans un bac, attendus structurés ajoutés progressivement, exécuteur partagé avec pytest, W15 et W08 d'abord) ; I-ACT-01 (écriture dans un bac par défaut).
**Règles concernées :** T-ING-04 à T-ING-08 (décisions, mémoire), R-DEC-02 (nature), R-DOC-07 (qualification), R-RED-01 à R-RED-03 (rejeu), R-PRI-03 et R-PRI-07 (conflits de lot, concurrence).
**Test humain :** sessions de curation chronométrées (cadre technique §7) : revoir le lot b1 à l'écran, mesurer le temps et le nombre de propositions jugées inutiles.

---

## 1. Ce que dit le cadre

- **Revue** (I-VUE-05) : propositions avec étiquettes, détail, dépendances, concurrence, diff contre l'état ; questions de nature ; décisions ; rejeux ouverts et leurs conflits ; aperçu d'impact d'une redéfinition.
- **Parcours d'acceptation** (I-ACC-01) : les étapes `do:` de `walkthroughs.yaml` s'exécutent pas à pas dans un bac à sable ; à côté des attendus en prose, des **vérifications structurées** ; l'interface montre chaque étape et chaque attendu (réussi, échoué, non structuré) ; pytest et l'interface partagent l'exécuteur.

## 2. Ce qui existe et se réutilise

- Service : `review.list`, `review.accept`, `review.refuse`, `review.nature`, `replay.*`, `redefine.preview`, `pipeline.*`, `wiki.*`, `state.check`. Décisions métier : `decide.accept` (avec `keep`, `drop_optional`), `refuse` (changements), `choose`, `adapt`, `qualify`, `promote`, `abandon`, `move`, `dismiss`.
- Ligne de commande `review list|show|accept|refuse|choose|adapt|qualify|promote|nature|dismiss`.
- Parcours : 18 parcours, 13 verbes `do:` (`load_world`, `apply_edits`, `set_point`, `ingest_batch`, `decide`, `apply_edit`, `create_branch`, `transpose`, `play`, `load_scenarios`, `load_drafts`, `retroactive_redefinition`, `validate_schema`) ; attendus en prose ; **décisions désignées de façon informelle** (« b1/notes p3 », « title (régent / gouverneur) ») et actions qui n'existent pas toutes (`confirm_partial` avec libellés, `refuse_all`).

## 3. Points à trancher avec l'auteur (une question à la fois)

1. **Où vont les décisions de revue ?** La file vit dans le monde de travail ; une décision est une écriture (I-ACT-01 : bac par défaut).
2. **Format exécutable des parcours** : faire évoluer `walkthroughs.yaml` (identifiants réels de propositions, actions du service) et choisir la forme des vérifications structurées.
3. **Ampleur en I5** : W15 et W08 exécutables et vérifiés de bout en bout, les autres parcours exécutables sans attendus structurés ; ou tous.

## 4. Définition de « fini »

- Écran de revue : file filtrable, détail d'une proposition, toutes les décisions du service, questions de nature, rejeux ouverts ; opérations de service manquantes ajoutées (`review.choose`, `review.adapt`, `review.qualify`, `review.promote`, `review.dismiss`, `review.show`…).
- Exécuteur de parcours dans le service (`walkthrough.run`), dans un bac, étape par étape, attendus structurés vérifiés ; `pytest` l'utilise ; écran « Acceptation ».
- W15 et W08 au moins : toutes les étapes exécutables, tous les attendus structurés, verts.
- Guide PowerShell, test humain, documents (corpus : README, `check_corpus.py` si le format change).
