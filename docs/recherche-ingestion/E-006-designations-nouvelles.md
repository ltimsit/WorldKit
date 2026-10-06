# E-006 — Des désignations proposées comme entités nouvelles

- **Statut** : résolue sur b1 (remède 2, déterministe)
- **Classe** : N (granularité : une désignation d'une entité prise pour une entité)
- **Où** : b1, `notes-baron` v1 p1 et p7, `lieux-de-valmont` p1 ; couches C1b (repérage) et C2 (recoupement)
- **Observé avec** : Claude Haiku 4.5, `api-haiku`, 4 octobre 2026 ; prompt de base (2 passes sur 2, identiques) et variante A ([X-002](X-002-c1-c2-fenetre.md), [X-003](X-003-formes-courtes.md))
- **Coût en revue** : trois fausses créations à refuser (et un doublon de Valmont si on l'accepte)

## Observation

| Texte | Mention relevée | Recoupement C2 | Ce que c'est |
|---|---|---|---|
| « Odon de Brume est le baron de Brume » | « baron de Brume », Character | entité nouvelle `baron de brume` | une désignation d'Odon (titre « de » lieu) |
| « Odon porte le titre de régent de Brume » | « régent de Brume », Character | entité nouvelle `régent de brume` | un titre d'Odon (voir E-005) |
| « un port du royaume de Valmont » | « royaume de Valmont », Faction | entité nouvelle `royaume de valmont` | Valmont lui-même, typé Faction au lieu de Place |

Ces mentions sont légitimes pour le repérage (elles désignent bien quelque chose) ; l'erreur est d'en faire des entités **nouvelles**.

## Explication

1. **Forme « <titre ou catégorie> de <nom connu> »** : la mention contient un nom connu (Brume, Valmont), mais C2 ne rattache par « nom contenu » que si les types sont compatibles. « baron de Brume » est un Character, Brume un lieu : pas de rattachement, donc « nouveau ».
2. **Le type proposé par le modèle pour « royaume de Valmont »** (Faction) empêche le rattachement à Valmont (Place). Le choix est défendable (un royaume est aussi une organisation) ; le schéma de Valmont n'a pas de type « royaume ».
3. C2 n'a pas d'issue intermédiaire : une mention est soit rattachée, soit nouvelle. Ici il faudrait « désignation de quelqu'un qu'on connaît, à préciser ».

## Remèdes envisagés

1. *Mesure* : rien à corriger ; le gold n'a pas ces mentions, elles comptent en trop, à juste titre pour celles qui créent une entité.
2. *Déterministe* : dans C2, une mention « <mot> de <nom connu> » dont le mot est un titre porté par une entité **liée à ce nom connu** se rattache à cette entité (« baron de Brume » → Odon, qui porte « baron » et gouverne Brume). Sinon, au lieu de « nouveau », un statut **à préciser** (doute) avec le nom connu contenu comme indice. À écrire sans viser b1 : la règle doit s'abstenir quand plusieurs entités conviennent.
3. *Consigne* : demander à C1b de ne pas relever une désignation qui n'est qu'un titre ou une catégorie suivi d'un nom (risque : perdre « le conseil des marchands », qui en a la forme).
4. *Humain* : l'auteur retire ou rattache, en un geste chacune ; ou pose une annotation « désignation de » une fois.
5. *Couche* : C2 avec liste courte au modèle (« baron de Brume » : candidats Odon, Brume) seulement pour ces cas ; à garder pour plus tard.

## Essais

- **4 octobre 2026, remède 2** (déterministe, mesuré par rejeu des réponses d'X-002 et X-003, sans appel). Règle de C2, après les règles existantes : une mention de la forme « <mot> de <nom connu> » est rattachée à l'entité qui porte ce titre **et** est reliée à l'entité nommée, si elle est seule ; sinon elle devient un **doute** avec l'entité nommée pour indice ; jamais une entité nouvelle. Une forme dont la fin n'est pas un nom connu (« conseil des marchands », « taverne du Héron ») n'est pas concernée.

  | | Avant | Après |
  |---|---|---|
  | Entités nouvelles proposées | 6 | **3** (conseil des marchands, taverne du Héron, Roi Gris) |
  | dont fausses (créations à refuser) | 4 | **1** (Roi Gris, à l'auteur : E-002) |
  | « baron de Brume » | nouvelle entité | **Odon** (seul baron, gouverne Brume) |
  | « régent de Brume » | nouvelle entité | doute, indice Brume (personne ne porte le titre « régent » dans l'état) |
  | « royaume de Valmont » | nouvelle entité | doute, indice Valmont (typé Faction, Valmont est un lieu) |

  Rappel C1 et recoupement inchangés (28 sur 28, 27 bien recoupées). La mesure compte désormais les créations proposées et les fausses (`new_proposed`, `new_false`).

## Conclusion

Résolu sur b1 par une règle déterministe qui s'abstient (doute) plutôt que de créer. Le doute garde l'information utile (l'entité nommée) pour l'auteur. Limites : un seul corpus ; la règle suppose la tournure française « <titre> de <lieu> » et un titre enregistré dans l'état ; « régent de Brume » reste un doute alors que c'est Odon, parce que l'état ne connaît pas ce titre (lien avec E-005).
