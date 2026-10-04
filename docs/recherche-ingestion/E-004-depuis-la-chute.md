# E-004 — « depuis la Chute » donne `odon involved_in la-chute`

- **Statut** : ouverte
- **Classe** : H (non dit) ; consigne explicite ignorée
- **Où** : b1, `notes-baron` v1, passage 1 ; extraction monolithique (future couche C5)
- **Observé avec** : Claude Haiku 4.5, `api-haiku`, prompt version 3, 4 octobre 2026 ; 1 passe sur 1 ([X-001](X-001-b1-haiku-reference.md)). Non observé sous Sonnet 5.
- **Coût en revue** : un refus.

## Observation

Passage : « Odon de Brume est le baron de Brume. Il gouverne la cité portuaire depuis la Chute. »

Sortie : `add_relation odon involved_in la-chute`, en plus des faits attendus (`title = baron`, `rules brume`). `involved_in` n'est pas dans le schéma.

La règle 10 du prompt cite ce cas mot pour mot : « pas de relation qui n'est pas dite (« depuis la Chute » ne dit pas que quelqu'un y a participé) ».

## Explication

1. **Consigne noyée** : la règle 10 est une des 13 ; sous Sonnet elle tenait, sous Haiku non. Hypothèse : un modèle plus petit applique moins de consignes à la fois.
2. **Toute mention d'entité appelle une relation** : le modèle relie les entités repérées dans la phrase, faute de comprendre qu'un complément de temps n'est pas une relation.

## Remèdes envisagés

1. *Mesure* : aucun.
2. *Déterministe* : `involved_in` est hors schéma, donc déjà signalé (T-ING-13). On pourrait mettre de côté les relations hors schéma vers un `Event` cité seulement comme repère de temps, mais c'est une heuristique fragile.
3. *Consigne* : déplacer la règle vers la couche qui en a besoin (C5), dans un prompt court ; mesurer si elle est alors respectée.
4. *Humain* : « ignorer » sur la proposition ; rien de réutilisable.
5. *Couche* : C5 à entités données reçoit « la Chute » marquée comme repère temporel (C1 ou C0) ; ou le critique C6 juge la relation contre sa preuve (« depuis la Chute » ne soutient pas `involved_in`).

## Essais

Aucun. Mesurer d'abord la stabilité : 1 passe ne dit pas si l'écart est systématique.

## Conclusion

À venir. Cas d'école pour le critique (C6) : écart H, preuve citable, jugement local.
