# E-005 — « régent de Brume » au lieu de « régent »

- **Statut** : résolue sur b1 (règle sans modèle, 11 octobre 2026 ; choix 42 du chantier)
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

- **4 octobre 2026, X-004** : persiste dans C5, malgré une consigne de forme courte réduite à cinq règles (exemple pris hors de Valmont). Argument de plus pour le remède déterministe (vocabulaire d'attribut).

- **11 octobre 2026, règle sans modèle** (décision de l'auteur : la règle d'abord, le vocabulaire déclaré plus tard) : dans les contrôles d'après C5 (`check_facts`), une valeur « X de <entité> » devient « X » quand le sujet est déjà relié à cette entité, dans l'état ou par un fait de la même réponse ; la tête garde au plus trois mots ; la forme d'origine reste en précision (`exact`, « le texte dit plus précisément » dans l'atelier). Mesuré par **rejeu** des réponses de X-004, sans appel :

  | b1, Haiku 4.5 | Avant : précision / rappel | Après |
  |---|---|---|
  | entités du gold | 0,867 / 0,765 | **0,933 / 0,824** |
  | entités de la chaîne | 0,929 / 0,765 | **1,0 / 0,824** |
  | questions (gold) | 0,875 / 0,70 | **1,0 / 0,80** |

  « régent de Brume » disparaît, « régent » est trouvé. Corbelle (réponses de X-004, entités du gold) : inchangé (0,333 / 0,5 avant comme après). Deux jeux de traces plus anciens (`c-x007-gold`, `c-x004-chain`) ne sont plus rejouables (prompts changés depuis).

## Conclusion

Résolue sans modèle ni déclaration. Le vocabulaire par attribut (chantier §10.5) reste prévu pour les synonymes (E-001, « cité portuaire » → « port »), quand l'écart réapparaîtra sur un vrai texte.
