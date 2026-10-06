# E-013 — Le critique trop littéral met de côté un fait juste

- **Statut** : ouverte (la v3 du critique n'est pas adoptée, X-015 ; écart observé sur Corbelle seulement)
- **Classe** : critique (faux rejet)
- **Où** : Corbelle c1, `persos` p1 ; couche C6
- **Observé avec** : Claude Haiku 4.5, critique v1 et v2, 4 octobre 2026 ([X-009](X-009-critique.md)) ; une passe chacune
- **Coût en revue** : un geste « reprendre » par fait juste mis de côté (choix 2 : visible, réversible)

## Observation

| Fait | Version | Motif du critique | Pourquoi c'est faux |
|---|---|---|---|
| `bertrand-ostrel member_of bateliers` (« Bertrand Ostrell : maître de la GdB ») | v2 | « maître » indique une direction, pas une simple appartenance | le maître d'une guilde en est membre ; le schéma n'a pas de relation de direction |
| `agathe parent_of ostrel` (« Secret … : mère agathe c la mère d'Ostrel ») | v1 | passage marqué comme secret | un secret est un fait (notoriété, R-NOT) ; corrigé en v2 |
| `ysolde detests bateliers` (« elle deteste les bateliers ») | v1 | les bateliers sont des personnes, pas la Guilde | « les Bateliers » est un autre nom de la Guilde ; corrigé en v2 (autres noms donnés) |

## Explication

Le critique juge le fait tel qu'il est formulé contre le texte, au pied de la lettre : il ne sait pas qu'un fait **plus faible** que le texte (être membre, quand le texte dit « maître ») reste soutenu, ni ce que le schéma permet d'exprimer.

## Remèdes envisagés

2. *Déterministe* : rien de sûr.
3. *Consigne* : « un fait plus faible que ce que dit le passage (être membre, quand il dit diriger) est soutenu » ; donner au critique la liste des relations du schéma qui relient ces deux types, pour qu'il sache que la plus proche a été choisie. À mesurer : l'ajout ne doit pas lui faire accepter les relations devinées (E-010).
4. *Humain* : reprendre le fait mis de côté, un geste (choix 2).
5. *Couche* : verdict à trois niveaux déjà en place ; on pourrait ne mettre de côté que sur `not_supported` avec un motif d'une catégorie connue (proximité, temps, rumeur…), et garder sinon. Risque : catégories mal étiquetées.

## Essais

- v1 et v2 (X-009).
- **6 octobre 2026, [X-013](X-013-stabilite-faits-corbelle.md)** : trois passes identiques ; deux faits justes mis de côté à chaque passe : `bertrand-ostrel member_of bateliers` (« maître de la GdB ») et `ysolde detests bateliers` (« les bateliers, des gens, pas la Guilde », alors que le critique reçoit l'autre nom « les Bateliers » ; gardé en X-009 v2). C'est le premier coût de rappel de la chaîne sur Corbelle (2 manques sur 3).
- **6 octobre 2026, [X-015](X-015-critique-v3.md)** : critique v3 (« un fait plus faible qui en découle nécessairement est soutenu » ; « un nom commun pluriel peut désigner une faction par ses membres »). `ysolde detests bateliers` est soutenu ; `bertrand-ostrel member_of bateliers` reste mis de côté (« ne précise pas ce que signifie maître ») : question de vocabulaire, pas de règle. Corbelle 0,53 / 0,75 → 0,59 / 0,83 ; Valmont b1 inchangé.
- **6 octobre 2026, X-015, données non vues** : sur 10 lots (Valmont b2 à b8, bruité, pièges), la v2 ne fait **aucun** faux rejet ; la v3 en fait deux (« sur le port de Brume » rejeté pour proximité). La v3 n'est pas adoptée. E-013 est peut-être propre aux notes brouillon de Corbelle : à revoir sur le second jet de l'auteur.
