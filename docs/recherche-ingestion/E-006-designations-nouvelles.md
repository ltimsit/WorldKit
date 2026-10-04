# E-006 — Des désignations proposées comme entités nouvelles

- **Statut** : ouverte
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

Aucun.

## Conclusion

À venir. Remède 2 d'abord (déterministe, avec abstention), mesuré par rejeu sans appel.
