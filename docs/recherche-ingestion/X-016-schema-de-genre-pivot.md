# X-016 — Schéma de genre « fantasy jdr » comme ontologie pivot de l'extraction

- **Statut** : conclue, **non adoptée** : les deux variantes pivot font plus de faits faux que la référence sur les lots non vus (critère fixé d'avance non tenu) ; le cache, lui, marche
- **Hypothèse** : si C5 et la question ciblée répondent dans un schéma de genre complet et hiérarchisé (une énumération dont ils ne peuvent pas sortir), ramené au schéma du monde **sans modèle**, alors (1) la qualité est au moins celle de la configuration adoptée sur des lots non vus, (2) les généralisations (« mère de » → `parent_of`, « à la tête de » → `member_of`) passent du modèle au noyau, (3) le prompt système, stable et au-delà du seuil de cache, coûte peu.
- **Idée** : de l'auteur, 6 octobre 2026 ; voie A choisie (ontologie pivot pour l'extraction, cadre inchangé). Vision de l'auteur : des schémas par genre et par style, complets dès le départ.
- **Couches et modèles** : C5 et question ciblée en variante pivot ; énonciation ; critique v2 inchangé. Claude Haiku 4.5 par l'API (`api-haiku`, température 0, substitut).

## Ce qui est figé avant la mesure

- **Schéma de genre** : `worldkit/periphery/pivot/fantasy-jdr.yaml`, version 1. 9 types, 59 relations, hiérarchie (`broader`), sens canonique, définition et exemple par relation. Sources : ACE 2005 (types et sous-types, `Located` distinct de `Near`), ARF 2025 (relations de fiction), usages du genre. Exemples tirés de la fiction connue (Tolkien, Martin, Rowling, Shakespeare…), jamais des corpus.
  - **Contamination retirée avant le gel** : une première rédaction reprenait des tournures vues dans nos corpus, dont certaines des lots réservés à la mesure (« sur le port », « tomber au combat », « abbesse sur son abbaye », « maître », « avant la crue », « régent », « moine d'un ordre », « travailler près d'un lieu n'est pas y habiter »). Elles ont été retirées. Reste un biais qu'on ne peut pas exclure : le choix des relations est fait par quelqu'un qui a lu ces corpus.
  - **Taille** : 11 relations propres au jeu de rôle (quête, captivité, espion, trahison, contrôle, dette, monture ou familier, commerce, ascendance, héritier, successeur) ont été ajoutées pour compléter le genre ; elles font passer le prompt système au-delà du seuil de cache de Claude Haiku 4.5 (4 096 tokens) : 4 432 tokens pour C5, 4 346 pour la question ciblée (comptage de l'API).
- **Correspondances** : `corpus/valmont-v1/valmont/pivot-map.yaml` et `corpus/corbelle-v1/corbelle/pivot-map.yaml` : types du monde → types du pivot ; relations du pivot → relations du monde, écrites d'après le seul schéma du monde. Règle (`PivotMap.to_world`) : la relation exacte si le monde l'a ; sinon la plus proche relation plus générale qui y figure (la forme exacte passée au critique) ; sinon hors schéma, identifiant du pivot (R-SCH-06, l'auteur décide).
- **Prompts** : système = règles de la couche puis schéma de genre entier (identique d'un appel à l'autre) ; message = entités avec leur type du monde et du pivot, attributs du monde, texte. Variante **indice** : les relations du pivot compatibles avec les types des entités rappelées en fin de message (ne touche pas au préfixe mis en cache).
- Code : `worldkit/periphery/pivot/`, `FactFinder(pivot_map=…, hint=…)`, `RelationProbe(pivot_map=…, hint=…)`, options `--pivot-map`, `--pivot-hint` de `worldkit eval facts`. Tests : `tests/test_pivot.py`.

## Protocole

- **Configurations** :
  - **référence** : configuration adoptée (C5, question ciblée avec relations connues et signal par paire, énonciation, critique v2). Réponses déjà tracées le 6 octobre (`llm-log/x015-ref-*`, `llm-log/c-facts-2026-10-06-full-p1`, `llm-log/x014-b1-adopted`) : prompts inchangés depuis.
  - **pivot** : `--pivot-map … --probe --probe-pairs --enunciation --critic` ;
  - **pivot + indice** : la même avec `--pivot-hint`.
- **Lots de décision** (non vus pendant la conception) : Valmont b2 à b8, Valmont bruité l1-b1 et l2-b1, pièges p1. **Lots rapportés à part** (vus) : Corbelle c1, Valmont b1.
- **Unité** : le score « questions » (supports exclus), vrais et faux positifs et manques sommés sur les lots de décision.
- **Critère, fixé d'avance** : une variante pivot est **candidate** si, sur les lots de décision, elle a **au moins autant de faits justes** et **au plus autant de faits faux** que la référence. Si les deux variantes passent, la préférée a le moins de faits faux, puis le moins de tokens. Le résultat est rapporté quel qu'il soit.
- **Biais connu, contre le pivot** : une relation du pivot sans correspondant (`near`, `works_at`, `enemy_of`…) part hors schéma ; si le gold ne la note pas, elle compte comme fait faux, même juste. Ces cas sont comptés à part.
- **Cache** : part des tokens d'entrée lus en cache (`cache_read_tokens`) pour C5 et la question ciblée, coût par lot comparé à la référence.
- **Coût estimé** : 0,15 à 0,30 $ pour les deux variantes ; arrêt et compte rendu si le cache ne prend pas au premier lot.
- **Limite qui demeure** : corpus synthétiques écrits par Claude ; seul le second jet de l'auteur tranchera (T-TST-01).

## Résultats (6 octobre 2026, une passe, température 0)

Score « questions » (supports exclus) et score « faits », sommés ; coût des trois couches ; part des tokens d'entrée de C5 et de la question ciblée lus en cache. Traces : `llm-log/x016-pivot-*`, `llm-log/x016-hint-*`.

| Lots de décision (10) | Questions : justes / faux / manqués | Faits : justes / faux / manqués | Coût | Entrée C5 + question | dont en cache |
|---|---|---|---|---|---|
| référence | 22 / **6** / 19 | 40 / 18 / 28 | 0,080 $ | 26 518 | 0 % |
| pivot | 22 / **22** / 19 | 39 / 33 / 29 | 0,115 $ | 204 903 | 92 % |
| pivot + indice | 23 / **11** / 18 | 39 / 23 / 29 | 0,105 $ | 211 093 | 94 % |

| Lots vus (Corbelle c1, Valmont b1) | Questions | Faits | Coût |
|---|---|---|---|
| référence | 12 / 5 / 4 | 23 / 10 / 6 | 0,051 $ |
| pivot | 12 / 6 / 4 | 23 / 12 / 6 | 0,049 $ |
| pivot + indice | 9 / 11 / 7 | 20 / 18 / 9 | 0,055 $ |

**Critère non tenu** par les deux variantes (faits faux > référence). Coût total de la mesure : ~0,33 $ (estimation : 0,15 à 0,30 $).

### Les faits faux propres au pivot (lots de décision, variante sans indice)

| Sorte | Nombre | Exemples |
|---|---|---|
| hors schéma (le biais annoncé) | 6 | `veilleurs → maëlle` (« confiée aux Veilleurs » : sans doute `guardian_of`, juste), `odon → serment` (`bound_by`, juste), `odon → brume` deux fois, `flamme-azur → veilleurs` (phrase de rumeur) |
| attributs | ~8 | « condition : règne avec sagesse », `death_cause`, `author_name`, `date` d'une chronique, « condition : vieux », titres « frère », « roi » : le prompt pivot change la façon dont C5 relève les attributs, qui ne passent pourtant pas par le pivot |
| généralisations ramenées au monde | 5 | `died_in` → `involved_in` (« tomba en combattant », « périt dans l'incendie », dans une chronique), `hautval located_in valmont` (deux fois), `conseil-des-marchands rules brume` |

Même sans le biais hors schéma, le pivot fait 16 faits faux contre 6.

## Lecture

1. **Le cache marche** : 92 à 96 % des tokens d'entrée de C5 et de la question ciblée sont relus en cache, à environ un dixième du prix. Un prompt **huit fois plus long** ne coûte que ~40 % de plus. C'est le résultat solide de cette mesure, et il vaut pour tout schéma complet placé dans le prompt système.
2. **La qualité baisse** : plus de choix rend C5 plus bavard (attributs en trop, relations « générales » ramenées dans le schéma, hors schéma). Le rappel ne gagne rien (22 contre 22). C'est le résultat déjà noté au chantier (§10.2 : la largeur de la tâche gêne un petit modèle), retrouvé ici sous une autre forme.
3. **L'indice aide sans suffire** : rappeler les relations compatibles divise par deux les faits faux (22 → 11), mais reste au-dessus de la référence ; sur les lots vus, il fait moins bien que le pivot seul. Une passe chacune : l'écart entre les deux variantes pivot est à prendre avec prudence ; l'écart avec la référence (6 contre 11 et 22) est net.
4. **La hiérarchie a joué comme prévu** (`leader_of` → `member_of`, `mother_of` → `parent_of`) mais elle ramène aussi dans le schéma des faits que la référence ne produisait pas, pas toujours justes (`died_in` → `involved_in`).
5. **Budget d'entrée** : avec le pivot, chaque appel de C5 et de la question ciblée dépasse le budget de 4 000 tokens fixé pour les petits modèles (5 400 à 5 900 tokens). Le cache de l'API réduit le prix, pas la longueur du contexte qu'un petit modèle doit lire.

## Suite

- **Ne pas adopter** le pivot pour l'extraction. Garder le schéma « fantasy jdr » comme **première version d'un schéma de genre pour les mondes** (vision de l'auteur) : c'est un usage différent (le monde le choisit, le modèle ne reçoit que la part utile), qui reste à proposer au cadre (R-SCH-05).
- Le cache est acquis pour la suite : tout prompt système stable de plus de 4 096 tokens (Claude Haiku 4.5) est relu à un dixième du prix. Pour un petit modèle local, l'équivalent est la réutilisation du préfixe (cache KV), à vérifier selon le moteur.
- Piste non testée : un schéma de monde **riche mais filtré par types** (comme aujourd'hui), où le monde aurait les relations du pivot dès le départ.
