# E-010 — Des relations inférées d'une proximité (« sur », « près de », « traverse »)

- **Statut** : en cours (résolue en X-009 ; en X-013, « habite près du » est jugé douteux et gardé)
- **Classe** : I (inféré, au-delà du texte)
- **Où** : Corbelle c1, `brouillon-corbelle` p1 et p4, `la-sorgue` p1 et p2 ; couche C5
- **Observé avec** : Claude Haiku 4.5, C5 à entités du gold et de la chaîne, 4 octobre 2026 ([X-006](X-006-corbelle-chaine.md)) ; une passe
- **Coût en revue** : un refus par fait (4 à 5 sur le lot)

## Observation

| Texte | Fait produit | Pourquoi c'est faux |
|---|---|---|
| « corbelle c'est la ville sur la sorgue » | `corbelle located_in la-sorgue` | une ville n'est pas dans une rivière |
| « la sorgue traverse corbelle » | `la-sorgue located_in corbelle` | traverser n'est pas être situé dans |
| « elle tient l'apothicairerie pres du pont-aux-anes » | `ysolde lives_in pont-aux-anes` | travailler près d'un lieu n'est pas y habiter |
| « le vieux de l'écluse » (écluse au sud de la ville) | `vieux lives_in corbelle` | non dit |

## Explication

Le schéma n'a pas de relation pour « au bord de », « traverse », « près de » ; le modèle choisit la plus proche de la liste plutôt que de s'abstenir. La consigne 1 (« ne déduis pas au-delà du texte ») ne suffit pas sur un texte familier. C'est l'envers d'E-007 : là, la liste réduite empêchait le hors schéma ; ici, elle attire des relations approchées.

## Remèdes envisagés

2. *Déterministe* : aucun sûr.
3. *Consigne* : « une relation de la liste seulement si le texte l'affirme telle quelle ; sinon, ne rien produire » (et laisser la question ciblée proposer un hors schéma). À mesurer par un appel par document.
5. *Couche* : le critique C6, sur ce qui pose une question : « la phrase soutient-elle `located_in` ? » ; cas d'école avec E-004.

## Essais

- **4 octobre 2026, [X-008](X-008-consignes-et-question.md)** : consigne stricte de C5 (« être au bord, près, traverser n'est pas être situé ; travailler n'est pas habiter ; sinon ne rien produire ») : **aucun effet** sur Corbelle, et régression sur Valmont (rappel 0,82 → 0,71). Écartée. Les relations devinées viennent aussi de la question ciblée (« habite près du »). Prochain candidat : le critique C6 (un fait contre sa preuve).
- **4 octobre 2026, [X-009](X-009-critique.md)** : le critique C6 met de côté `corbelle located_in la-sorgue`, `ysolde lives_in pont-aux-anes` (deux fois) et `vieux lives_in corbelle` (« proximité ≠ résidence ») ; rien de mis de côté sur Valmont. Juger un fait contre son passage marche là où la consigne d'écriture ne marchait pas.
- **6 octobre 2026, [X-013](X-013-stabilite-faits-corbelle.md)** : sur trois passes identiques, le critique écarte toujours `corbelle located_in la-sorgue` et `vieux lives_in corbelle`, mais juge `ysolde lives_in pont-aux-anes` douteux (`unsure`) : le fait est gardé. La question ciblée le formule elle-même « habite près du ». Un verdict `unsure` sur un motif de proximité pourrait aussi mettre de côté (remède 5 d'E-013).
- **6 octobre 2026, [X-015](X-015-critique-v3.md)** : avec la v3 du critique (« une proximité n'implique pas une résidence »), `ysolde lives_in pont-aux-anes` est de nouveau mis de côté, aux deux occurrences (C5 et question ciblée).
- **6 octobre 2026, X-015, données non vues** : la phrase de la v3 « une proximité n'implique pas une résidence » fait rejeter `taverne-heron located_in brume` (« sur le port de Brume »), un fait juste, deux fois. La frontière entre « près de » (inférence) et « sur le port de » (localisation) ne se règle pas par une phrase générale ; v3 non adoptée.
