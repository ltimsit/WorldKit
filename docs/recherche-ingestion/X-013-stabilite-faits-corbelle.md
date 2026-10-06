# X-013 — Stabilité de la chaîne des faits sur Corbelle (entités du gold)

- **Statut** : conclue
- **Hypothèse** : la baisse des faits entre X-010 (0,59 / 0,83 avec les entités du gold) et X-011 (0,44 / 0,58 sur la chaîne complète) vient de la variabilité de C5 d'une passe à l'autre ; plusieurs passes avec les entités du gold devraient retrouver le niveau d'X-010 en moyenne.
- **Couches et modèles** : C5, question ciblée, énonciation (C4), critique (C6) ; Claude Haiku 4.5 par l'API (`api-haiku`, température 0, substitut).
- **Corpus** : Corbelle, lot c1 (trois documents), entités du gold (`--entities gold`) : les faits sont jugés seuls, sans les erreurs de la couche mentions.
- **Écarts liés** : E-010, E-013 (et deux écarts nouveaux, plus bas).

## Protocole

Monde neuf à l'état de base (`corbelle-mesure.db`), 6 octobre 2026. Deux séries :

| Série | Options | Passes | Appels par passe | Coût par passe |
|---|---|---|---|---|
| **témoin** | `--probe --enunciation --critic` | 4 | 16 à 17 | ~0,022 $ |
| **adoptée** (X-008) | `--probe --probe-relations --probe-pairs --enunciation --critic` | 3 | 25 à 26 | ~0,032 $ |

La série témoin est née d'un oubli : les deux options de la question ciblée adoptées en X-008 (relations connues en préférence, signal par paire) n'avaient pas été passées. Elle mesure donc la chaîne sans elles. Total : 7 passes, ~0,18 $. Traces : `llm-log/c-facts-2026-10-06*` (rapports `report.json`).

## Résultats

| Passe | Faits P / R | Questions P / R |
|---|---|---|
| témoin 1 | 0,44 / 0,58 | 0,43 / 0,50 |
| témoin 2 | 0,53 / 0,67 | 0,57 / 0,67 |
| témoin 3 | 0,38 / 0,50 | 0,25 / 0,33 |
| témoin 4 | 0,44 / 0,58 | 0,38 / 0,50 |
| adoptée 1, 2, 3 | **0,53 / 0,75** (identiques) | 0,50 / 0,67 (identiques) |
| X-010, rappel | 0,59 / 0,83 | 0,71 / 0,83 |

Série adoptée : 9 faits justes, 8 en trop, 3 manqués, aux trois passes.

### Écarts de la série adoptée (3 passes sur 3)

| Passage | Écart | Où naît-il | Fiche |
|---|---|---|---|
| brouillon p2 | **manque** le titre « bourgmestre » de Jehan Marcastel (« le bourgmestre c Jehan Marcastel ») | C5 ne le produit jamais (7 passes sur 7) | nouveau (a) |
| brouillon p4 | **manque** « Ysolde déteste les bateliers » | trouvé par la question ciblée, **mis de côté par le critique** : « les bateliers, des gens, pas la Guilde », alors qu'il reçoit l'autre nom « les Bateliers » | E-013 |
| persos p1 | **manque** « Ostrel membre de la Guilde » (« maître de la GdB ») | trouvé par la question ciblée, mis de côté par le critique : « maître » serait une direction | E-013 |
| brouillon p4 | en trop « Ysolde vit au Pont-aux-Ânes » (« près du ») | la question ciblée le formule « habite près du » ; le critique doute (`unsure`) sans l'écarter | E-010 |
| brouillon p6 | en trop « Ostrel magouille avec l'abbesse » (hors schéma) | jugement vague, le gold attend le silence ; le critique doute | X-008 (cas connu) |
| persos p1 | en trop `condition = « ~45 ans »` pour Jehan Marcastel | un âge versé dans un attribut d'état | nouveau (b) |
| persos p1 | en trop `title = « maître de la gdb »` | le sigle n'est pas développé dans une valeur (C2 le résout pour une mention, pas dans un texte de valeur) | nouveau (b) |
| quatre faits | en trop, mais **supports** (déjà dans l'état) : `jehan-marcastel rules corbelle`, `jehan-leblond member_of bateliers`, titre « passeur », `ysolde sibling_of jehan-marcastel` relevé en p4 (« la soeur ») au lieu de p5 | aucun coût en revue | p4/p5 : classe G (le gold place le fait en p5 seulement) |

Le critique écarte bien trois inférences fausses à chaque passe : `corbelle located_in la-sorgue` (« sur »), `vieux lives_in corbelle`, `jehan-leblond involved_in grande-crue` (« avant la crue »).

## Lecture

1. **L'hypothèse ne tient pas.** À température 0, la chaîne adoptée donne **trois passes identiques**. Seule la série témoin varie (0,38 à 0,53 en précision), et même là, ce sont les mêmes écarts d'une passe à l'autre. La baisse n'est pas un tirage malchanceux : les écarts sont **systématiques**, et chacun appelle un remède propre, pas des passes multiples. La remarque d'X-011 (« une seule passe ne suffit plus ») vaut pour la série témoin, pas pour la chaîne adoptée.
2. **Les options d'X-008 rapportent** : rappel 0,58 → 0,75 en moyenne. `parent_of` revient à la place de `mother_of`, le mariage et « déteste » sont trouvés.
3. **Le critique coûte deux des trois manques.** Les deux faits justes qu'il met de côté relèvent d'E-013 : un nom commun pluriel pris au pied de la lettre (« les bateliers »), et une direction confondue avec une appartenance. Sans critique, le rappel serait de 11 sur 12, mais trois faits faux passeraient. Dans l'atelier, un fait mis de côté reste visible et se reprend en un geste (choix 2).
4. **Les supports comptent comme « en trop »** : 4 sur 8. Hors supports, la précision serait de 9 sur 13 (0,69). C'est la même règle de mesure qu'en X-010, donc la comparaison reste juste ; mais pour estimer le coût en revue, il faut les mettre à part.
5. **Écart avec X-010** (0,59 / 0,83 → 0,53 / 0,75) : un fait juste de moins (« déteste », gardé en X-009 v2, mis de côté ici à chaque passe) et quelques faits en trop. La cause n'est pas établie : les traces d'X-010 ne sont pas sur cette machine. Hypothèses : évolution du modèle derrière l'alias `claude-haiku-4-5`, ou effet des changements d'X-011 et X-012 sur les noms donnés au critique.

## Suite

- **E-013** : deux cas de plus, stables ; c'est maintenant le premier coût de rappel de la chaîne. Candidat : la consigne « un nom commun pluriel désigne les membres d'une faction » et « un fait plus faible que le passage est soutenu », à mesurer contre E-010.
- **Nouveaux écarts, à ficher** :
  - (a) titre manqué dans une phrase brouillon « le <titre> c <nom> » ;
  - (b) valeurs d'attribut en forme brute : sigle non développé, âge versé dans `condition`.
- Les mesures de la chaîne à température 0 peuvent se faire **en une passe** ; garder une seconde passe de contrôle quand un prompt change.
