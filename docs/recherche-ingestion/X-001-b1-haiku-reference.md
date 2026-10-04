# X-001 — Mesure de référence : b1 sous Haiku 4.5 (API), extracteur actuel

- **Statut** : conclue
- **Hypothèse** : l'extracteur monolithique (un appel, 13 règles, schéma complet), conçu et réglé avec Sonnet, perd nettement en qualité avec un modèle plus petit, et ses pertes se concentrent sur ce qu'il demande de faire en une fois (repérer les entités, les créer, suivre les consignes de forme).
- **Couches et modèles** : extracteur actuel (prompt version 3), une seule « couche » ; Claude Haiku 4.5 par l'API (`api-haiku`, température 0, sans réflexion), **substitut** d'un petit modèle (chantier §8).
- **Écarts liés** : E-001, E-002, E-003, E-004, E-005.

## Protocole

- Lot b1 de Valmont v1 (12 passages : `notes-baron` v1, `lieux-de-valmont`), monde neuf à l'état de base.
- `worldkit eval extraction --profile api-haiku --batch b1`, une passe (pas de stabilité).
- Coût estimé 0,10 $, accordé par l'auteur le 4 octobre 2026.
- Indicateurs : T2 avec facultatifs neutres, usage et budget d'entrée (4 000 tokens).

## Résultats

| | Haiku 4.5, API (4 oct.) | Sonnet 5, `claude -p` (28 sept.) |
|---|---|---|
| Précision | 0,65 | 0,84 |
| Rappel | 0,59 | 0,81 |
| Précision, questions | 0,50 (7 vp, 7 fp) | 0,83 |
| Rappel, questions | 0,47 (8 fn) | 0,79 |
| Facultatifs trouvés | 1/4 | — |
| Pièges tombés | 1 (Roi Gris) | 1 (Roi Gris) |
| Erreurs d'extraction | 0 | 0 |
| Appels, durée | 12, 21,6 s | 12 |
| Tokens en entrée | 42 374 (au plus 3 538 par appel), 0 lu du cache | environ 4 900 par appel (`claude -p`) |
| Tokens en sortie | 1 678 | — |
| Coût | 0,051 $ | (abonnement) |
| Au-delà du budget | 0 appel | — |

Attention : la colonne Sonnet compte les facultatifs comme manqués (mesure d'avant leur neutralisation) ; son rappel est sous-estimé d'autant. Une seule passe de chaque côté.

### Écarts classés

| Passage | Écart | Classe | Coût en revue | Fiche |
|---|---|---|---|---|
| notes p3, p4 ; lieux p2 | « le conseil des marchands » jamais créé comme entité : valeur `brume.ruler` (hors schéma), titre « membre du conseil des marchands » ; d'où 6 manqués (création, nom, `rules`, `member_of`, deux `based_in`) et 2 en trop | N | fort : deux fausses valeurs à refuser, entité et relations à saisir | [E-003](E-003-conseil-valeur.md) |
| lieux p4 | « Roi Gris » créé, `rules hautval` et titre « roi » en plus (règle 5, « régnait autrefois », ignorée) | R, T | une fausse création et deux faits faux | [E-002](E-002-roi-gris.md) |
| notes p1 | `odon involved_in la-chute` tiré de « depuis la Chute » (règle 10, qui cite ce cas, ignorée) | H | un refus | [E-004](E-004-depuis-la-chute.md) |
| notes p7 | `odon.title = régent de Brume` au lieu de « régent » (règle 9, qui cite ce cas, ignorée) | S | une adaptation | [E-005](E-005-regent-de-brume.md) |
| lieux p5 | `cendrelande.category = plaines` manqué | — | aucun (support) | — |
| notes p6 | rumeur : attribution juste, plus une affirmation recopiée (« Le baron est un traître ») | — | aucun | — |

**Non reproduit** : E-001 (« cité portuaire » prise pour une catégorie), systématique sous Sonnet, n'apparaît pas sous Haiku (1 passe).

## Lecture

1. **L'écart dominant est structurel, pas de résolution** : une entité nouvelle qui n'est jamais reconnue comme entité (E-003) coûte à elle seule 6 manqués et 2 en trop, en cascade sur trois passages. Le protocole de création (créer, nommer, réutiliser l'étiquette) est une tâche à plusieurs pas que le petit modèle court-circuite en écrivant une valeur. C'est exactement ce que viserait une couche C1 « mentions » séparée.
2. **Trois consignes explicites ignorées**, dont deux citent mot pour mot le cas fautif (règles 5, 9, 10). Avec Sonnet, elles tenaient. Un prompt de 13 règles dépasse ce qu'un modèle plus petit applique : argument direct pour des couches courtes, chacune avec peu de consignes.
3. **Le schéma de sortie lui-même dépasse une limite** : 27 champs de type union, l'API en accepte 16. Il a fallu le réécrire dans l'adaptateur (chaîne vide pour null). Un schéma trop large est un coût pour un petit modèle aussi (décodage contraint plus lourd, plus de choix).
4. **Le budget d'entrée tient** : 3 538 tokens au plus par appel par l'API. Les 4 900 tokens mesurés avec `claude -p` comprenaient le surcoût de Claude Code. Le prompt système, sous le seuil de mise en cache de Haiku, n'est pas mis en cache (0 token lu du cache).
5. **Limites** : une passe, 12 passages, substitut plus capable qu'un vrai petit modèle, corpus optimiste (T-TST-01). Les chiffres sont un point de départ, pas un verdict.

## Stabilité (deuxième passe, 4 octobre 2026)

`--repeat 2` : la première extraction est relue du cache, la seconde rappelle le modèle (12 appels, 0,0515 $). Stabilité moyenne **0,875** : 10 passages identiques (1,0), deux instables, **notes p3 (0,5) et notes p4 (0,0)**, précisément ceux d'E-003. E-002, E-004 et E-005 sont donc reproduits à l'identique ; E-001 reste absent. La mesure ne gardait pas alors le contenu de la seconde extraction : elle le garde désormais (« 1re seule », « 2e seule »).

Troisième extraction (même jour, 12 appels, 0,0512 $, variante conservée et appels tracés) : stabilité **0,958**. notes p3 et p4 sont cette fois **identiques** à la première passe (le conseil reste une valeur) ; seul lieux p5 varie (`cendrelande.category = plaines` trouvé, un support). Sur trois extractions, E-003 a donc pris deux fois la même forme, une fois une forme inconnue. La température 0 ne rend pas Haiku déterministe.

Les traces montrent ce que reçoit le modèle : outre le prompt système, la liste des **19 entités connues** de l'état, y compris les capacités de système (`system-a:bite`), à chaque appel, quel que soit le passage.

## Suites

- E-003 est le premier écart à traiter (plus gros coût, cause unique) ; les remèdes vont de l'indication de schéma à une couche C1.
- E-003 : forme majoritaire établie (2 extractions sur 3) ; la forme minoritaire reste inconnue.
- Rejouer b1 sous Sonnet avec la mesure actuelle (facultatifs neutres) pour une comparaison juste, si le cache de la mesure du 28 septembre est retrouvé (sinon, coût d'abonnement seulement).
