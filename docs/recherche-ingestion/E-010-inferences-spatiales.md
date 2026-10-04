# E-010 — Des relations inférées d'une proximité (« sur », « près de », « traverse »)

- **Statut** : ouverte
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

Aucun.
