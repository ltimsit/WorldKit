# X-016 — Schéma de genre « fantasy jdr » comme ontologie pivot de l'extraction

- **Statut** : protocole figé, mesure à faire
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
