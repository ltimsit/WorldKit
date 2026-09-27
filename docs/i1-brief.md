# Fiche de démarrage — Jalon I1 : couche de service, exécutions, bacs à sable

**Cadre :** *cadre-interface.md* v0.2 — I-PRI-02, I-PRI-03, I-PRI-05, I-PRI-07 ; I-SBX-01, I-RUN-01, I-CLI-01 ; forme commune d'un retour (§7).
**Règles du noyau concernées :** T-ARC-01 (déterminisme), R-HIS-01 (l'histoire ne fait que s'allonger), T-STO-02 (un fichier par monde).
**Test :** automatique, sur le service seul (sans interface ni navigateur). Pas de test humain : I1 n'a pas d'écran.

---

## 1. Ce que dit le cadre d'interface

- **Couche de service** : une API Python mince entre l'interface, la ligne de commande et le code métier ; elle ne contient **aucune logique métier** (I-PRI-02) ; chaque opération rend un **résultat** de forme commune : statut, entrée, sortie, signalements avec la règle citée, indicateurs, trace (§7).
- **Exécutions** (I-RUN-01) : enregistrées dans `monde.runs.db`, à côté du monde : entrées, artefacts, indicateurs, trace, prompts et réponses brutes ; purge manuelle.
- **Bacs à sable** (I-SBX-01) : copie du fichier du monde (`monde.sandbox-<n>.db`) ; créer, lister, jeter en I1 ; **rendre réel** (rejouer les actions enregistrées sur le monde de travail) arrive en I3, mais I1 doit enregistrer ces actions sous une forme rejouable.
- **Parité** (I-CLI-01) : toute opération du service est accessible en ligne de commande.

## 2. Ce qui existe et se réutilise

- `World` (`worldkit/core/world.py`) : apply, submit, confirm, rebase, abandon, branches, points, transposition, états.
- Ingestion (`worldkit/ingest/`) : `ingest`, décisions (`decide.py`), questions de nature (`meta.py`), revue (`review.py`).
- Workflows (`worldkit/core/workflows/`) : scénarios, déroulés, rejeu.
- Vues (`worldkit/core/views/`) : pages, rendu, export, signalements.
- `Issue` (code, message, règle, gravité, chemin) : déjà la forme des signalements.
- La ligne de commande (`worldkit/cli.py`) appelle aujourd'hui tout cela directement, avec un affichage propre à chaque commande.

## 3. Points à trancher avec l'auteur (une question à la fois)

1. **Forme d'une opération du service** : fonctions Python ordinaires, ou **registre d'opérations nommées** avec paramètres typés (pydantic), qui donne d'un coup l'API HTTP (I2), la ligne de commande, l'enregistrement des exécutions et le rejeu d'un bac à sable (I3) ?
2. **Qu'est-ce qui est une exécution enregistrée** : toute opération, ou seulement celles qu'on « exécute » (écritures, mécanismes, étapes, mesures), les simples consultations (une page, une liste) n'étant pas enregistrées ?
3. **Forme de la ligne de commande** : une commande générique (`worldkit call <opération> <paramètres.yaml>`), des commandes dédiées, ou les deux ?
4. **Bacs à sable et exécutions** : où vivent les exécutions faites dans un bac à sable (dans le `runs.db` du monde d'origine, ou dans un `runs.db` propre au bac) ; un bac à sable peut-il en engendrer un autre ?

## 4. Définition de « fini »

- La couche de service expose au moins : l'état et les compteurs d'un monde, les pages de wiki (auteur, joueur, à un point), les branches, points et journal, les signalements ; appliquer ou soumettre une édition ; ingérer un lot ; les opérations de bac à sable.
- Chaque opération rend un résultat de forme commune, sérialisable en JSON canonique ; les exécutions sont enregistrées et relisibles.
- Les bacs à sable se créent, se listent, se jettent ; une opération peut viser un bac à sable ; le monde de travail n'est jamais modifié par une opération sur un bac (test T1).
- Ligne de commande : les opérations nouvelles sont accessibles (I-CLI-01) ; les commandes existantes restent inchangées pour l'auteur.
- `pytest` vert, sans vrai modèle ; guide PowerShell vérifié ; documents mis à jour (cadre d'interface, analyse, CLAUDE.md).
