# X-015 — Critique v3 : fait plus faible impliqué, nom commun pluriel pour une faction

- **Statut** : conclue, **non adoptée** : sur données non vues, la v3 met de côté deux faits justes que la v2 gardait (critère fixé d'avance non tenu)
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

## Limite de la mesure ci-dessus (remarque de l'auteur, 6 octobre 2026)

La v3 a été écrite **pour** les deux faux rejets de Corbelle, puis mesurée **sur** Corbelle : la mesure vérifie que le correctif corrige ce qu'il visait, pas qu'il généralise. Les exemples du prompt, « hors corpus », en sont des calques (« les tisserands » pour « les bateliers »). Corbelle c1 compte 12 faits attendus : ±1 fait vaut ±0,08. Sur Valmont b1, le critique ne met rien de côté, ni en v2 ni en v3 : la « non-régression » n'y prouve presque rien. Corbelle est écrit par Claude (T-TST-01) : il sert à construire, pas à décider.

## Mesure sur données non vues (protocole fixé avant la mesure)

- **v3 gelée** : prompt inchangé depuis le commit `d15d833`. Aucune retouche pendant ni après cette mesure.
- **Données** : non utilisées pour régler le critique : Valmont **b2 à b8** (aucune couche des faits n'y a été réglée), Valmont bruité **l1, l2** (texte dérivé de b1, bruit non vu), contre-corpus de **pièges** p1. Entités du gold, monde à l'état de base.
- **Comparaison appariée** : une passe de référence complète (C5, question ciblée de la configuration adoptée, énonciation, critique v2) ; puis le critique v3 seul, sur **les mêmes réponses** de C5 et de la question ciblée (rejeu).
- **Unité** : les faits **jugés** par le critique (seuls ceux-là peuvent changer), classés justes ou faux contre le gold ; un fait hors gold est lu à la main et dit tel quel.
- **Critère d'adoption, fixé d'avance** : la v3 est adoptée si, sur l'ensemble, elle (1) ne met de côté **aucun fait juste** que la v2 gardait, et (2) écarte **au moins autant de faits faux** que la v2. Sinon, elle reste une option. Le résultat est rapporté quel qu'il soit.
- **Limite qui demeure** : Valmont et les pièges sont eux aussi synthétiques et écrits par Claude ; seul le second jet de l'auteur tranchera (T-TST-01).

### Résultats (6 octobre 2026)

Passe de référence : 10 lots (b2 à b8, l1-b1, l2-b1, p1), C5, question ciblée, énonciation, critique v2 ; puis critique v3 sur les mêmes réponses de l'amont. 39 faits jugés. ~0,12 $ (référence ~0,08 $, critique v3 ~0,04 $). Traces : `llm-log/x015-ref-*`, `llm-log/x015-v3-*`.

| | Faits mis de côté | dont justes (faux rejets) | Faux écartés |
|---|---|---|---|
| critique v2 | 7 | 0 | 7 |
| critique v3 | 9 | **2** | 7 |

Tous les verdicts sont identiques, sauf deux, et ce sont les mêmes :

| Lot | Fait | v2 | v3 |
|---|---|---|---|
| l1-b1 | `taverne-heron located_in brume` (« La taverne du héron, sur le port de Brme… ») | soutenu | **mis de côté** : « la proximité au port n'affirme pas une localisation dans la ville » |
| l2-b1 | le même (« sur le port de Burme ») | soutenu | **mis de côté** : « la proximité n'implique pas une résidence dans la ville » |

Rappel : l1-b1 0,765 → 0,706 ; l2-b1 0,824 → 0,765. Aucun autre lot ne bouge.

**Critère non tenu** (point 1 : aucun fait juste perdu) : la v3 **n'est pas adoptée**.

### Lecture

1. **La remarque de l'auteur était fondée.** La phrase qui avait « renforcé » E-010 sur Corbelle (« une proximité n'implique pas une résidence ») est celle qui fait rejeter « sur le port de Brume » : être sur le port d'une ville, c'est bien y être. Le gain mesuré sur Corbelle était un réglage sur Corbelle.
2. **Sur ces 10 lots, la v2 ne fait aucun faux rejet** : ses 7 mises de côté sont justes (meurtres inventés d'un personnage par lui-même, rumeur, relation tirée d'une vieille note, faction absente du passage). E-013 n'apparaît pas hors de Corbelle : c'est peut-être un écart propre à ce corpus (notes brouillon, « maître de la GdB », « les bateliers »), à revoir sur les notes de l'auteur.
3. **Méthode** : un remède se mesure sur des données qui n'ont pas servi à l'écrire, avec un critère posé avant. Les mesures « sur le corpus qui a montré l'écart » restent utiles pour vérifier qu'un correctif fait ce qu'il vise, jamais pour l'adopter.

