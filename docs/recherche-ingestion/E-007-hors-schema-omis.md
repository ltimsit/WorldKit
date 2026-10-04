# E-007 — Une relation hors schéma est omise (« vassal du roi Mervin »)

- **Statut** : résolue sur b1 (remède 5 : question ciblée sur signal, choix de l'auteur)
- **Classe** : consigne ignorée ; question de conception (hors schéma)
- **Où** : b1, `notes-baron` v1, passage 2 ; couche C5
- **Observé avec** : Claude Haiku 4.5, `api-haiku`, 4 octobre 2026, C5 à entités du gold et de la chaîne ([X-004](X-004-c5-faits.md)) ; 1 passe chacune
- **Coût en revue** : un ajout à la main (le fait manque), et surtout un **signal perdu** : le hors schéma est ce qui nourrit l'extension du schéma (R-SCH-06, ontologiste)

## Observation

Passage : « Odon est le vassal du roi Mervin, à qui il a prêté serment à Hautval. »

Attendu (gold) : `add_relation odon vassal_of mervin`, qualifié hors schéma par le noyau (`vassal_of` est absent du schéma de Valmont **à dessein**, pour tester R-SCH-06 et le parcours W09).

Sortie de C5 : rien pour ce passage. La consigne 3 (« si aucune relation ne convient, propose un identifiant anglais en snake_case ») est ignorée. L'extracteur actuel, sous Haiku, produisait bien `vassal_of` (X-001).

## Explication

1. **La liste des relations possibles cadre la réponse** : C5 reçoit les relations compatibles avec les types présents ; aucune ne dit « vassal ». Le modèle se tient à la liste plutôt que d'inventer.
2. Dans l'extracteur actuel, le schéma était décrit sans liste filtrée et la consigne de hors schéma plus visible ; la réduction du schéma, utile pour la précision, a un effet de bord sur le hors schéma.

## Remèdes envisagés

1. *Mesure* : aucun.
2. *Déterministe* : aucun pour trouver le fait ; on peut en revanche **signaler les phrases sans fait** (chantier §10.6, niveau 2 : « ce qui n'a pas été capturé ») : la phrase de p2 n'a produit aucun fait alors qu'elle cite deux entités confirmées.
3. *Consigne* : rendre la sortie hors schéma explicite dans le format (un champ « relation proposée » à côté de la liste) ; ou un exemple, pris hors de Valmont.
4. *Humain* : l'auteur ajoute la relation (un geste « ajouter ») ; s'il l'ajoute souvent, c'est le signal d'une extension de schéma.
5. *Couche* : un passage dédié aux phrases sans fait qui citent deux entités confirmées (« quelle relation le texte affirme-t-il entre A et B ? »), sans liste, avec proposition d'identifiant. Question étroite, déclenchée seulement par le signal du remède 2.

## Essais

- **4 octobre 2026, [X-005](X-005-question-ciblee.md)** (remède 2 puis 5, choisi par l'auteur) : signal sans modèle sur les phrases qui citent deux entités confirmées sans fait (deux sur b1), puis question étroite sans liste de relations. « Odon est le vassal du roi Mervin » donne `odon vassal_of mervin`, tournure « est le vassal de » ; la phrase du Roi Gris (« régnait autrefois ») ne donne rien. Rappel des faits 0,77 → 0,82.

## Conclusion

Tranché par l'auteur : le hors schéma vient d'une question ciblée sur les phrases muettes, pas de C5 (choix 28 du chantier). La relation proposée nourrit le schéma seulement par une décision de l'auteur, avec trois issues (choix 29). Limites : un seul corpus, deux phrases muettes.
