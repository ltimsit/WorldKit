# X-008 — Consigne stricte pour C5 ; question ciblée avec relations connues et signal par paire

- **Statut** : conclue
- **Hypothèses** :
  1. une consigne plus stricte dans C5 (proximité, travail, repères de temps) réduit les relations devinées (E-010, E-004) ;
  2. donner à la question ciblée les relations connues comme préférence évite les synonymes (`mother_of`) ;
  3. déclencher la question par **paire d'entités non reliées** (dans le passage) plutôt que par phrase muette retrouve les hors schéma perdus (« elle deteste les bateliers »).
- **Couches et modèles** : C5 (normal ou strict) et question ciblée (d'origine ou avec relations et paires) ; Claude Haiku 4.5 par l'API (`api-haiku`, substitut). Entités du gold (qualité propre de C5).
- **Corpus** : Valmont b1 et Corbelle c1. Exemples des consignes pris hors des deux corpus.
- **Écarts liés** : E-004, E-010, E-012.

## Protocole

Grille 2 × 2 sur chaque corpus, tout ce qui était tracé rejoué. ~33 appels, ~0,044 $. Traces : `llm-log/x008-*`.

**Correction de mesure faite en cours** : une relation **hors schéma** se compare désormais par sa paire d'entités, pas par l'identifiant proposé (`detests` contre `hates`, `vassal_of`) : c'est l'auteur qui fixera l'identifiant en l'acceptant (§6.6). Toute la grille a été remesurée par rejeu avec cette règle.

## Résultats (faits, entités du gold)

| C5 + question ciblée | Corbelle : précision / rappel | Corbelle, questions | Valmont : précision / rappel | Valmont, questions |
|---|---|---|---|---|
| normal + d'origine | 0,29 / 0,50 | 0,18 / 0,33 | 0,88 / 0,82 | 0,89 / 0,80 |
| **normal + relations et paires** | **0,44 / 0,92** | **0,43 / 1,0** | 0,82 / 0,82 | 0,89 / 0,80 |
| strict + d'origine | 0,29 / 0,50 | 0,15 / 0,33 | 0,80 / 0,71 | 0,67 / 0,60 |
| strict + relations et paires | 0,42 / 0,83 | 0,38 / 1,0 | 0,82 / 0,82 | 0,73 / 0,80 |

Ce que la nouvelle question a trouvé sur Corbelle : `ysolde detests bateliers` (hors schéma, « déteste »), `ysolde sibling_of jehan-marcastel`, `agathe rules saint-fiacre`, `ostrel member_of bateliers` (« maître de la guilde »), `jehan-marcastel spouse_of clemence` (« marié à »), `agathe parent_of ostrel` (et non plus `mother_of`). Sur Valmont : toujours `odon vassal_of mervin`, rien de nouveau en trop sur les questions (le fait en plus est un support).

## Lecture

1. **La consigne stricte ne sert à rien** : nulle sur Corbelle, nuisible sur Valmont (rappel 0,82 → 0,71) ; elle rend C5 plus prudent sans le rendre plus juste. **Écartée.** Les relations devinées par proximité (E-010) et le repère de temps (E-004) restent : ce n'est pas une affaire de consigne. Prochain candidat : le critique (C6), qui juge un fait contre sa preuve, ou une question de vérification.
2. **La nouvelle question ciblée est le grand gain** : rappel sur Corbelle 0,50 → 0,92, et 1,0 sur les questions ; la liste des relations comme préférence remplace `mother_of` par `parent_of` ; le signal par paire, à l'échelle du passage, retrouve « déteste » et le mariage. Sans régression sur les questions de Valmont. **Adoptée** (`--probe --probe-relations --probe-pairs`).
3. **Ce qui reste en trop sur Corbelle** (8 faits qui posent une question) :
   - relations devinées : `corbelle located_in la-sorgue`, `la-sorgue located_in corbelle`, `ysolde lives_in pont-aux-anes` (C5 **et** question ciblée, « habite près du »), `vieux lives_in corbelle` (E-010) ;
   - repère de temps : `jehan-leblond involved_in grande-crue` (E-004) ;
   - jugement vague : `ostrel conspires_with agathe` (« magouille avec ») ;
   - **rumeur** : `vouivre haunts corbelle`, tiré de « les vieux disent que » : la question ciblée ignore l'attribution (couche C4, à construire) ;
   - titre : « maître de la GdB ».
4. Limites : une passe par configuration ; corpus écrits par Claude ; les supports comptent dans la précision des faits (pas dans celle des questions).
