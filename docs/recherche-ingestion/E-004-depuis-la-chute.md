# E-004 — « depuis la Chute » donne `odon involved_in la-chute`

- **Statut** : rouverte (non reproduit sur Valmont par C5, revient sur Corbelle)
- **Classe** : H (non dit) ; consigne explicite ignorée
- **Où** : b1, `notes-baron` v1, passage 1 ; extraction monolithique (future couche C5)
- **Observé avec** : Claude Haiku 4.5, `api-haiku`, prompt version 3, 4 octobre 2026 ; 2 passes sur 2, identiques ([X-001](X-001-b1-haiku-reference.md)). Non observé sous Sonnet 5.
- **Coût en revue** : un refus.

## Observation

Passage : « Odon de Brume est le baron de Brume. Il gouverne la cité portuaire depuis la Chute. »

Sortie : `add_relation odon involved_in la-chute`, en plus des faits attendus (`title = baron`, `rules brume`). `involved_in` est bien dans le schéma de Valmont (« impliqué dans ») : le fait est conforme, simplement non dit.

La règle 10 du prompt cite ce cas mot pour mot : « pas de relation qui n'est pas dite (« depuis la Chute » ne dit pas que quelqu'un y a participé) ».

## Explication

1. **Consigne noyée** : la règle 10 est une des 13 ; sous Sonnet elle tenait, sous Haiku non. Hypothèse : un modèle plus petit applique moins de consignes à la fois.
2. **Toute mention d'entité appelle une relation** : le modèle relie les entités repérées dans la phrase, faute de comprendre qu'un complément de temps n'est pas une relation.

## Remèdes envisagés

1. *Mesure* : aucun.
2. *Déterministe* : rien de sûr ; `involved_in` est une relation du schéma, le noyau n'a aucune raison de la signaler. Mettre de côté une relation vers un `Event` cité seulement comme repère de temps serait une heuristique fragile.
3. *Consigne* : déplacer la règle vers la couche qui en a besoin (C5), dans un prompt court ; mesurer si elle est alors respectée.
4. *Humain* : « ignorer » sur la proposition ; rien de réutilisable.
5. *Couche* : C5 à entités données reçoit « la Chute » marquée comme repère temporel (C1 ou C0) ; ou le critique C6 juge la relation contre sa preuve (« depuis la Chute » ne soutient pas `involved_in`).

## Essais

- L'écart est reproduit à l'identique sur deux passes de l'extracteur actuel (stabilité 1,0 sur ce passage).
- **4 octobre 2026, X-004** : C5 (document entier, cinq consignes, dont « un repère de temps n'est pas une relation ») ne le produit pas, avec les entités du gold comme avec celles de la chaîne ; il rend au contraire « Il gouverne la cité portuaire » par `odon rules brume`, juste. Une passe.

- **4 octobre 2026, [X-006](X-006-corbelle-chaine.md)** : sur Corbelle, « faisait passer les gens avant la grande crue » donne `jehan-leblond involved_in grande-crue` (C5, entités du gold et de la chaîne) : la consigne tient sur un texte propre, pas sur un texte familier.
- **4 octobre 2026, [X-008](X-008-consignes-et-question.md)** : consigne stricte (« avant l'incendie » n'est ni un fait ni une relation) : sans effet, `involved_in grande-crue` reste. Candidat suivant : le critique C6.

## Conclusion

À venir. Cas d'école pour le critique (C6) : écart H, preuve citable, jugement local.
