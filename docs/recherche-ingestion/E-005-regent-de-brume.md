# E-005 — « régent de Brume » au lieu de « régent »

- **Statut** : ouverte
- **Classe** : S (forme de surface) ; consigne explicite ignorée
- **Où** : b1, `notes-baron` v1, passage 7 ; extraction monolithique (future couche C5)
- **Observé avec** : Claude Haiku 4.5, `api-haiku`, prompt version 3, 4 octobre 2026 ; 2 passes sur 2, identiques ([X-001](X-001-b1-haiku-reference.md)). Non observé sous Sonnet 5.
- **Coût en revue** : une adaptation (corriger la valeur), et une fausse collision si « régent » existe ailleurs.

## Observation

Passage : « Depuis la Chute, Odon porte le titre de régent de Brume. »

Sortie : `odon.title = "régent de Brume"`, recopié du texte. Attendu : `odon.title = "régent"`.

La règle 9 du prompt cite ce cas mot pour mot : « sous leur forme la plus courte (« régent », pas « régent de Brume ») ».

## Explication

1. **Consigne noyée**, comme E-004 : sous Sonnet elle tenait.
2. **Le complément porte une information vraie** (régent *de Brume*) que l'attribut `title` ne sait pas exprimer : le modèle la garde dans la valeur faute d'autre place. La relation `rules brume` existe déjà.

## Remèdes envisagés

1. *Mesure* : aucun.
2. *Déterministe* : normalisation des valeurs d'un attribut à vocabulaire court (indication de schéma, chantier §10.5) : si la valeur commence par une valeur connue du vocabulaire de `title` (« régent ») suivie d'un complément « de <entité connue> », proposer la forme courte et garder le complément comme indice de relation. Aucun appel en plus. Même famille de remède que E-001.
3. *Consigne* : règle de forme dans le prompt court de C5, mesurée.
4. *Humain* : adapter la valeur, un geste.
5. *Couche* : aucune nouvelle couche ne paraît justifiée pour ce cas ; le déterministe suffit probablement.

## Essais

Aucun.

## Conclusion

À venir. Avec E-001, argument pour un vocabulaire par attribut dans le schéma, essayé avant toute couche.
