# X-015 — Critique v3 : fait plus faible impliqué, nom commun pluriel pour une faction

- **Statut** : conclue ; **proposée à l'adoption** (option `--critic-v3`, en attente de l'accord de l'auteur)
- **Hypothèse** : deux règles de plus au critique suppriment les faux rejets d'E-013 sans relâcher les motifs qui écartent les inférences (E-010, E-004).
- **Couches et modèles** : C5 et question ciblée (configuration adoptée d'X-008) **rejouées** depuis les traces d'X-013 (Corbelle) et d'X-014 (Valmont b1) ; énonciation ; critique v3 seul en direct. Claude Haiku 4.5 par l'API (`api-haiku`, température 0, substitut).
- **Écarts liés** : E-013 (cible), E-010, E-004 (à ne pas rouvrir).

## Protocole

Règles ajoutées au prompt du critique v2 (exemples pris hors des corpus) :

1. Un fait plus faible que ce que dit le passage est soutenu s'il en **découle nécessairement** (« commande la compagnie » soutient « membre de la compagnie » ; « est l'oncle de » soutient « de la famille de »). Une proximité n'implique pas une résidence ; un repère de temps n'implique pas une participation.
2. Un nom commun au pluriel peut désigner une faction par ses membres (« déteste les tisserands » soutient « déteste la Guilde des tisserands »).

Mêmes réponses de C5 et de la question ciblée que la référence : seule la couche jugée change. 26 appels au critique, 0,026 $. Traces : `llm-log/x015-corbelle/`, `llm-log/x015-b1/`.

## Résultats

| Faits, entités du gold : précision / rappel | Corbelle | Corbelle, questions | Valmont b1 | Valmont b1, questions |
|---|---|---|---|---|
| critique v2 (référence, mêmes réponses amont) | 0,53 / 0,75 | 0,50 / 0,67 | 0,875 / 0,82 | 0,89 / 0,80 |
| **critique v3** | **0,59 / 0,83** | **0,63 / 0,83** | 0,875 / 0,82 | 0,89 / 0,80 |

Verdicts : Corbelle 8 soutenus, 2 incertains, 6 mis de côté ; Valmont 10 soutenus, rien de mis de côté.

| Fait | v2 | v3 | Juste ? |
|---|---|---|---|
| `ysolde detests bateliers` (« elle deteste les bateliers ») | mis de côté | **soutenu** | oui : règle 2 |
| `ysolde lives_in pont-aux-anes` (« près du », C5 et question ciblée) | douteux, gardé | **mis de côté** (« une proximité de lieu de travail n'implique pas une résidence ») | oui : E-010, effet de bord heureux de la phrase de garde de la règle 1 |
| `bertrand-ostrel member_of bateliers` (« maître de la GdB », persos) | mis de côté | **mis de côté** (« ne précise pas ce que signifie maître ») | non : la règle 1 ne joue pas, le modèle doute du sens de « maître » |
| `corbelle located_in la-sorgue`, `vieux lives_in corbelle`, `jehan-leblond involved_in grande-crue` | mis de côté | mis de côté | oui : rien de rouvert |
| `ostrel conspires_with agathe` (« magouille avec ») | douteux | douteux | gold : silence (jugement vague) |

## Lecture

1. **Gain net sur Corbelle** (+1 fait juste, −1 fait faux), **rien perdu sur Valmont**. Les motifs qui écartent les inférences tiennent : la phrase « une proximité n'implique pas une résidence » les a même renforcés.
2. **E-013 à moitié réglé** : le nom commun pluriel est compris ; le « plus faible impliqué » ne l'est pas sur « maître de la GdB », parce que le modèle ne tient pas « maître » pour une direction. C'est une question de vocabulaire (un titre de la guilde), pas de règle : à laisser à l'auteur (un geste) ou au schéma (une relation `leads`).
3. **Limite** : deux corpus, dont un écrit pour ce chantier ; une seule passe du critique. Le prompt est plus long de ~150 tokens par appel (11 896 tokens en entrée pour 16 appels sur Corbelle).

## Suite

- Adopter la v3 comme critique par défaut si l'auteur l'accepte (chantier §16), puis la vérifier sur le contre-corpus de pièges (X-012) avant de la passer au cadre.
- « maître de la GdB » : ni la question ciblée ni le critique ne le règlent ; à reprendre avec la relation de direction au schéma de Corbelle (choix de l'auteur), ou à laisser au geste « reprendre ».
