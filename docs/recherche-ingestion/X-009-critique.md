# X-009 — Le critique (C6) : un fait qui pose une question, jugé contre son passage

- **Statut** : conclue (deux versions)
- **Hypothèse** : une question étroite par fait (« le passage affirme-t-il ce fait, tel quel et actuellement ? »), posée seulement sur ce qui pose une question (pas les supports), met de côté les relations devinées (E-010), le repère de temps (E-004) et la rumeur, sans perdre de faits justes ni rien changer sur un texte propre.
- **Couches et modèles** : chaîne d'X-008 (C5 normal, question ciblée avec relations et paires), puis C6 ; Claude Haiku 4.5 par l'API (`api-haiku`, substitut) ; entités du gold.
- **Écarts liés** : E-004, E-010, E-012 (rumeur), [E-013](E-013-critique-litteral.md).
- **Principe** (choix 2 du chantier) : le critique **met de côté**, de façon visible, sans décider ; l'auteur reprend un fait mis de côté en un geste ; l'avis du critique n'entre pas dans la mémoire des décisions (R-PRI-04).

## Protocole

- Un appel par fait qui n'est pas un support : le passage, le fait proposé en clair (« Ysolde Marcastel (Character) — habite — le Pont-aux-Ânes (Place) »), trois verdicts (`supported`, `not_supported`, `unsure`) et un motif court. Seul `not_supported` met de côté.
- Les catégories de la consigne viennent des axes de test (proximité, repère de temps, passé révolu, rumeur, hypothèse, opinion), exemples pris hors des corpus.
- C5 et la question ciblée rejoués depuis X-008 : seuls les jugements sont des appels. v1 : 26 appels, 0,020 $ ; v2 : 26 appels, 0,022 $. Traces : `llm-log/x009-*`.

## Résultats

| Faits, entités du gold | Corbelle : précision / rappel | Corbelle, questions | Valmont : précision / rappel | Valmont, questions |
|---|---|---|---|---|
| sans critique (X-008) | 0,44 / 0,92 | 0,43 / 1,0 | 0,82 / 0,82 | 0,89 / 0,80 |
| critique v1 | 0,53 / 0,75 | 0,67 / 0,67 | 0,82 / 0,82 | 0,89 / 0,80 |
| **critique v2** | **0,53 / 0,83** | **0,63 / 0,83** | 0,82 / 0,82 | 0,89 / 0,80 |

Verdicts sur Corbelle (v2) : 6 soutenus, 3 incertains (gardés), 7 mis de côté ; sur Valmont : 10 soutenus, rien de mis de côté.

| Mis de côté (v2) | Juste ? | Motif du critique |
|---|---|---|
| `corbelle located_in la-sorgue` | oui (E-010) | « sur » indique une proximité, pas « situé dans » |
| `ysolde lives_in pont-aux-anes` (C5 et question ciblée) | oui (E-010) | proximité ≠ résidence |
| `vieux-ecluse lives_in corbelle` | oui (E-010) | le passage ne nomme pas Corbelle |
| `jehan-leblond involved_in grande-crue` | oui (E-004) | repère de temps |
| `vouivre haunts corbelle` | oui (rumeur, E-012) | ouï-dire (« les vieux disent que ») |
| `bertrand-ostrel member_of bateliers` (persos) | **non** (E-013) | « maître » serait une direction, pas une appartenance |

**v1 → v2** : en v1, le critique mettait aussi de côté `agathe parent_of ostrel` (« passage marqué comme secret » : il confondait secret et non-vrai) et `ysolde detests bateliers` (« les bateliers, des personnes, pas la Guilde » : il ignorait l'autre nom de la Guilde). v2 ajoute une règle (« un fait secret reste un fait du monde ; sa notoriété est une autre question ») et donne les autres noms des entités : les deux faits sont gardés.

## Lecture

1. **Le critique fait le travail que la consigne stricte ne faisait pas** (X-008) : juger *un* fait contre *son* passage est une question étroite qu'un petit modèle tient ; écrire les faits et s'abstenir en même temps ne l'était pas. Il règle E-010 et E-004 sur Corbelle, et la rumeur que la question ciblée laissait passer.
2. **Aucun effet sur Valmont** : 10 faits sur 10 soutenus ; le critique ne nuit pas à un texte propre.
3. **Il coûte un geste quand il se trompe** : 1 fait juste sur 7 mis de côté en v2 (`member_of` d'Ostrel), à reprendre par l'auteur (choix 2). Le compromis précision contre rappel reste à régler par les gestes simulés : un fait faux accepté coûte un refus, un fait juste mis de côté coûte une reprise.
4. **Deux leçons de conception** : le critique doit connaître les autres noms des entités, et savoir que la notoriété ne le regarde pas. Ce sont des informations d'état données au modèle, pas des règles de plus sur le texte.
5. Restent en trop sur Corbelle (questions) : `conspires_with` (incertain, gardé), le titre « maître de la gdb » (attribut, que le critique jugeait soutenu), et un `located_in` jugé soutenu ou incertain selon la passe. Limites : une passe par version ; corpus écrits par Claude.
