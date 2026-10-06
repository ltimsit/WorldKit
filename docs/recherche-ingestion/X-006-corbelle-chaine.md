# X-006 — La chaîne sur des notes brouillon (Corbelle, c1)

- **Statut** : conclue (diagnostic) ; remèdes à mener
- **Hypothèse** : la chaîne mise au point sur Valmont (C1, C2, C5, question ciblée) tient sur des notes brouillon (fautes, casse, familier, abréviations, notes de travail, listes) ; l'extracteur actuel, lui, s'y dégrade.
- **Couches et modèles** : extracteur actuel ; C1a, C1b (prompt de base et variante A), C2, C5, question ciblée ; Claude Haiku 4.5 par l'API (`api-haiku`, substitut).
- **Corpus** : [Corbelle](../../corpus/corbelle-v1/README.md), corpus **ciblé** écrit par Claude (biais : optimiste, même famille que le modèle). 3 documents, 13 passages, 36 mentions, 12 faits attendus dans le périmètre de C5.

## Protocole

Mêmes commandes que sur Valmont (`eval extraction`, `eval mentions`, `eval facts --probe`), monde neuf à l'état de base. ~32 appels, ~0,10 $ en tout. Traces : `llm-log/c-x001/` (extracteur actuel), `c-x002/` (C1 de base, deux passes), `c-x003/` (variante A), `c-x004-gold/` et `c-x004-chain/` (C5 et question ciblée).

## Résultats

| | Valmont b1 | **Corbelle c1** |
|---|---|---|
| Extracteur actuel : précision / rappel | 0,65 / 0,59 | **0,28 / 0,65** |
| idem, questions | 0,50 / 0,47 | **0,20 / 0,55** |
| C1 sans modèle : mentions trouvées | 18 / 28 | 17 / 36 |
| C1 avec Haiku : mentions trouvées | 28 / 28 | **35 / 36** (stabilité 1,0) |
| C2 : bien recoupées | 27 / 28 | **29 / 35** |
| C2 : fausses créations | 1 | **8** |
| C5 et question, entités du gold : précision / rappel | 0,88 / 0,82 | **0,22 / 0,42** |
| idem, entités de la chaîne | 0,93 / 0,82 | **0,18 / 0,33** |

Variante A (consigne des formes courtes) : même rappel, plus de bruit (13 fausses créations au lieu de 8) : **écartée sur Corbelle**. Variante B (formes courtes sans modèle) : ne trouve jamais « Ysolde », dont le nom complet n'apparaît pas.

## Écarts classés

| Couche | Écart | Exemples | Axes | Remède le moins coûteux | Fiche |
|---|---|---|---|---|---|
| C2 | variante de surface d'un nom connu prise pour une entité nouvelle | « Jehan Marcastell », « pont-aux-anes », « st fiacre », « GdB », « Jehan L. » | AX-S1, S3, S4, S5 | déterministe : pliage des accents et de la casse, distance d'édition, abréviations (« st » → saint), sigles, initiales | [E-008](E-008-variantes-de-surface.md) |
| C2 | variante d'une entité **nouvelle** d'un autre document | « Bertrand Ostrell » / « Bertrand Ostrel », « Ostrel » seul (entité « Ostrel » à part) | AX-S1, AX-C3, AX-R1 | déterministe : regroupement des nouvelles par proximité dans le lot | E-008 |
| C1 et C2 | nom commun ou idée d'intrigue repéré comme entité | « apothicairerie », « fête des lanternes », « Rouquine » (surnom pris à part) | AX-E5, AX-R3 | silence des passages d'idée et de note (à concevoir) ; surnom : alias proposé | E-008 |
| C1a | texte barré lu comme une mention | « ~~la vouivre~~ » | AX-E4 | déterministe : C0 écarte le texte barré | [E-009](E-009-texte-barre.md) |
| C5 | relation inférée d'une proximité | « ville sur la sorgue » → `located_in` ; « tient l'apothicairerie près du pont » → `lives_in` ; « traverse corbelle » → `located_in` | AX-S7 (I) | consigne ou critique ; à mesurer | [E-010](E-010-inferences-spatiales.md) |
| C5 | repère de temps pris pour une relation | « avant la grande crue » → `involved_in` | AX-D4 | **E-004 revient** sur texte familier | E-004 |
| C5 | relation aux types incompatibles avec le schéma | « maître de la guilde » → `rules` vers une Faction | — | déterministe : contrôle des types (le noyau le signale déjà) | [E-011](E-011-controles-c5.md) |
| C5 | alias égal au nom ; valeur avec faute | `la-sorgue aliases « la sorgue »` ; `title = bourgmèstre` | AX-S2 | déterministe : alias égal au nom écarté ; valeur rapprochée de la valeur connue | E-011 |
| Question ciblée | synonyme d'une relation existante | « la mère de » → `mother_of` au lieu de `parent_of` | — | donner à la question la liste des relations compatibles, comme préférence | [E-012](E-012-question-ciblee-limites.md) |
| Question ciblée | relation hors schéma dans une phrase **non muette** | « elle deteste les bateliers » : la phrase a produit `lives_in`, donc pas de question | AX-M3 | signal par paire d'entités plutôt que par phrase | E-012 |
| Mesure | preuve recopiée sur deux passages | sibling_of de p5 cité avec p4 | — | rattachement corrigé (plus de preuve introuvable) ; le passage choisi reste p4 | — |

## Lecture

1. **Le repérage par document entier tient** (35 mentions sur 36, stable) : la question étroite sur une fenêtre large résiste au désordre.
2. **Le recoupement déterministe est le maillon faible sur du texte réel** : il était exact sur Valmont parce que les noms y étaient bien écrits. Fautes, accents, abréviations et sigles produisent 8 fausses créations, puis contaminent C5 (entités de la chaîne : précision 0,18). Les remèdes sont **déterministes** : c'est le premier chantier.
3. **C5 se dégrade aussi avec les entités du gold** (0,22) : sur du texte familier, le modèle infère des relations de proximité (« sur », « près de », « traverse ») et prend un repère de temps pour une relation. Une partie se filtre sans modèle (types, alias, valeurs) ; le reste (inférence) demande un essai de consigne ou de critique.
4. **La question ciblée a deux limites** : elle invente des synonymes de relations existantes, et elle ne voit pas un hors schéma dans une phrase qui a déjà produit un fait.
5. **L'extracteur actuel s'effondre** (précision 0,28) : 24 faits en trop sur 30 qui posent une question. Sur ce corpus, la chaîne en couches ne le bat que sur le repérage ; c'est le recoupement et C5 qu'il faut durcir.
6. Limites : corpus écrit par Claude (optimiste), une passe pour C5, 12 faits attendus.

## Suites proposées

1. **Déterministe d'abord**, mesuré par rejeu gratuit : C2 tolérant (E-008), texte barré (E-009), contrôles de C5 (E-011).
2. Puis les remèdes qui touchent au modèle : liste de préférence pour la question ciblée et signal par paire (E-012), consigne ou critique contre les inférences de proximité et de temps (E-010, E-004).
3. Le silence des notes de travail et des idées d'intrigue (question 10 du chantier).
