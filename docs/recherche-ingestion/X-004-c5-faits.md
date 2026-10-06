# X-004 — C5 : les faits entre entités confirmées (b1)

- **Statut** : conclue (première itération)
- **Hypothèse** : à entités données, avec le document entier, un schéma réduit aux types présents et cinq consignes, un petit modèle extrait les relations et attributs mieux que l'extracteur actuel, et les écarts de consigne observés en X-001 (E-004, E-005) diminuent.
- **Couches et modèles** : C5, Claude Haiku 4.5 par l'API (`api-haiku`, substitut) ; entités du gold (qualité propre) ou de la chaîne C1 puis C2 (rejouée depuis X-002, formes courtes sans modèle, E-006 appliqué).
- **Écarts liés** : E-003, E-004, E-005, [E-007](E-007-hors-schema-omis.md).

**Limite** : un seul corpus, synthétique et arbitraire (Valmont, b1). Exemples du prompt pris hors de Valmont.

## Protocole

- Fenêtre : le document entier. Entrée : les entités confirmées présentes (identifiant, type, nom) ; les relations du schéma dont les types de départ et d'arrivée sont présents ; les attributs de ces types (sauf `name`).
- Une question, cinq consignes (ne rapporter que ce qui est dit ; identifiants de la liste ; relation hors liste en snake_case ; valeur courte ; fait révolu et repère de temps exclus ; preuve recopiée). Sortie sans union.
- Chaque fait cite sa preuve ; le passage est retrouvé sans modèle par la preuve.
- Mesure : changements du gold par passage, clé de la mesure T2, facultatifs neutres. **Hors de C5**, donc exclus : création des entités et leur nom (C2), notoriété (`set_visibility`, C4).
- 2 appels par variante (4 en tout), 0,0148 $, au plus 1 184 tokens par appel. Traces : `llm-log/x004-gold/`, `llm-log/x004-chain/`.

## Résultats

| | Entités du gold | Entités de la chaîne |
|---|---|---|
| Faits : précision / rappel | 0,87 / 0,77 (13 vp, 2 fp, 4 fn) | 0,93 / 0,77 (13 vp, 1 fp, 4 fn) |
| Questions : précision / rappel | 0,88 / 0,70 | 0,88 / 0,70 |
| Facultatifs trouvés | 1 / 2 | 1 / 2 |
| Preuves introuvables | 0 | 0 |

Pour mémoire, l'extracteur actuel sous Haiku (X-001) : précision 0,65, rappel 0,59 ; questions 0,50 et 0,47. **Périmètres différents** : X-001 compte aussi les créations, les noms et la notoriété ; la comparaison est indicative.

| Écart | Classe | Statut |
|---|---|---|
| E-003 : relations du conseil des marchands | N | **extraites** : gouverne Brume (p3), Odon membre (p4), siège à Brume (p4), siège à Hautval (lieux p2) |
| E-004 : « depuis la Chute » → `involved_in` | H | **non reproduit** |
| E-005 : « régent de Brume » | S | **persiste**, malgré la consigne de forme courte |
| E-007 : « vassal du roi Mervin » | — | **omis** : `vassal_of` est hors schéma (à dessein), le modèle ne propose rien |
| alias « le Roi Gris » d'Aldren II | R | manqué, même avec Aldren II donné : relève de l'annotation de l'auteur (§6.3), pas de C5 |
| `cendrelande.category = plaines` | — | manqué (support) |
| `cendrelande located_in valmont` | — | en trop (support, déjà dans l'état) |

**Défaut de mesure trouvé et corrigé** (remesuré par rejeu) : le nom d'une entité nouvelle se lisait document par document ; « siège à Hautval » comptait comme manqué et en trop à la fois (`conseil-marchands` contre `conseil des marchands`).

## Lecture

1. **La chaîne tient jusqu'aux faits** : E-003, l'écart le plus coûteux d'X-001, est résolu de bout en bout ; E-004 disparaît ; « Il gouverne la cité portuaire » est compris (Odon gouverne Brume) grâce au document entier, sans couche de coréférence.
2. **Aucune erreur héritée de l'amont sur b1** : le rappel est le même avec les entités du gold et celles de la chaîne.
3. **Restent deux consignes ignorées** : la forme courte (E-005) et la relation hors schéma (E-007). La forme courte se traite mieux sans modèle (vocabulaire d'attribut, E-005) ; la relation hors schéma est une question de conception : le modèle doit-il proposer ce que le schéma ne prévoit pas ?
4. **L'alias du Roi Gris** n'est pas une affaire de C5 : il naît de la confirmation de l'auteur (« le Roi Gris = Aldren II »), qui sort par proposition (§6.3).
5. Limites : une passe par variante (stabilité non mesurée), 12 passages, 17 faits attendus.
