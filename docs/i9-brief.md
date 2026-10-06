# I9 — L'atelier d'ingestion, deuxième incrément : les faits

**Statut :** fiche de jalon, version 0.1 — 6 octobre 2026. Décisions de l'auteur Q1 à Q4 actées le 6 octobre 2026.
**Contexte :** I8 a rendu réelle la couche « mentions » : l'auteur confirme les entités d'une source sur le texte. Le chantier a construit et mesuré la chaîne des faits (C5, question ciblée, énonciation, critique ; X-004 à X-016), toujours en simulant l'auteur. Ce jalon la met à l'écran : l'auteur **voit en pratique** ce que les couches proposent, pourquoi, et le décide.

## 1. Objectif

Sur une source dont les entités sont confirmées, l'auteur lance la couche « faits » ; il voit chaque fait proposé **sous le passage qui le porte**, avec sa preuve surlignée, la couche qui l'a trouvé, le verdict du critique et ce que l'énonciation a retenu ; il garde, retire, corrige, reprend un fait mis de côté, en ajoute un ; puis « Proposer » envoie entités et faits vers la revue.

## 2. Ce qui existe déjà

- Les couches : `FactFinder` (C5), `RelationProbe` (question ciblée, avec relations connues et signal par paire : configuration adoptée), `enunciation` (C4, sans modèle), `Critic` (C6, v2) dans `worldkit/periphery/facts.py`.
- Le magasin d'atelier (annotations en ajout seul, lecture par lignée), les gestes et portées, « Proposer », l'écran `/atelier` (I-ATL-01 à I-ATL-05).

## 3. Plan

1. **Couche « faits »** : `atelier.run` avec `layer: facts`. Entrée : les entités **confirmées par l'auteur** (point d'arrêt, chantier §6.5). Elle enchaîne C5, la question ciblée, l'énonciation et le critique, et écrit des annotations `kind: fact` : brouillon (relation ou attribut), preuve, passage, couche d'origine, verdict du critique et sa raison, voix retenue (rumeur, note). Appels au modèle estimés et confirmés, en tâche de fond (I-LLM-01).
2. **Écran** : sous chaque passage, la liste de ses faits, en français (libellés du schéma) : « Ysolde — déteste — la Guilde des Bateliers » ; la preuve surlignée dans le texte au survol ; une pastille par état (soutenu, douteux, mis de côté par le critique, retenu par l'énonciation, décidé par l'auteur) ; la raison du critique au survol.
3. **Gestes sur un fait** : garder ; retirer ; reprendre (un fait mis de côté ou retenu) ; corriger (relation, sens, attribut, valeur) ; ajouter (sujet, relation, objet ou attribut et valeur, choisis dans des listes).
4. **« Proposer »** : le lot contient les entités confirmées, les alias retenus **et les faits** (selon la question 1).
5. **Mesure réelle** : les gestes sur les faits sont des annotations ; leur nombre donne l'effort réel, à comparer aux gestes simulés du chantier.
6. **Documents** : cadre d'interface (I-ATL), glossaire, carte des outils, guide pas à pas, chantier, CLAUDE.md.

## 4. Décisions de l'auteur

| Q | Décision | Raison |
|---|---|---|
| Q1 | **(b)** « Proposer » envoie tous les faits proposés, sauf ceux que l'auteur a retirés et ceux que le critique a mis de côté (sauf repris) | l'atelier sert à voir et corriger ; la revue re-décide chaque fait : pas de travail en double |
| Q2 | **(b)** un second lot par version, réservé aux faits (`atelier-<source>-<version>-faits`), qui s'appuie sur les entités déjà proposées (acceptées : identifiant réel ; en attente : dépendance, comme entre deux lots) | les entités sont le point d'arrêt avant les faits (chantier §6.5) ; l'historique ne fait que s'allonger (R-HIS-01) |
| Q3 | **(a)** l'écran montre tous les faits, les écartés (mis de côté par le critique, retenus par l'énonciation) **grisés**, raison au survol | voir la pratique des couches : un faux rejet (E-013) ou une rumeur prise pour un fait se repère là ; filtre plus tard si l'écran se charge |
| Q4 | **(a)** ajouter un fait à la main dans ce jalon : sujet, relation ou attribut, objet ou valeur, choisis dans des listes (entités confirmées, schéma du monde) ; preuve = le passage | un fait manqué reste dans le champ de vision et se compte (geste « ajout ») |

## 5. Questions pour l'auteur

1. ~~Quels faits partent avec « Proposer » ?~~ Tranché (Q1).
2. ~~Une source déjà proposée~~ Tranché (Q2).
3. ~~Ce que l'écran montre par défaut~~ Tranché (Q3).
4. ~~Ajouter un fait à la main~~ Tranché (Q4).

## 6. Étapes (après les réponses)

1. `atelier.run layer=facts` : annotations de faits, relance qui respecte l'auteur, tâche de fond.
2. `atelier.annotate` sur un fait : garder, retirer, reprendre, corriger (et ajouter selon Q4).
3. « Proposer » étendu aux faits.
4. Écran : faits sous les passages, pastilles, gestes.
5. Documents et guide (exécuté par les tests).
