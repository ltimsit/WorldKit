# X-007 — Recoupement par score, texte barré, contrôles de C5 (sans modèle)

- **Statut** : conclue (première itération)
- **Hypothèse** : les fausses créations de Corbelle (E-008) ne demandent pas une règle par cas, mais un **score de ressemblance** tiré d'indices généraux et trois issues (rattachée, doute, nouvelle) ; le texte barré (E-009) et une partie des faux faits de C5 (E-011) se règlent sans modèle ; et rien ne régresse sur Valmont.
- **Couches** : C1a, C2, contrôles après C5 ; **aucun appel** : tout est remesuré par rejeu des réponses tracées (X-002, X-004, X-005, X-006).
- **Écarts liés** : E-008, E-009, E-011.

**Limite** : seuils réglés sur Valmont et Corbelle, deux petits corpus écrits par Claude ; à vérifier sur un corpus qu'ils n'ont pas vu (Valmont bruité, Valmont grossi), puis sur les notes de l'auteur.

## Ce qui a été construit

**Recoupement par score** (`worldkit/periphery/matching.py`, choix de l'auteur : RapidFuzz plutôt que des distances écrites à la main), selon la méthode classique de résolution d'entités :

1. **Pliage pour comparer**, sans réécrire le texte : casse, article initial, accents, ponctuation et trait d'union, abréviations usuelles (« st » → saint).
2. **Indices**, le meilleur l'emporte : Jaro-Winkler sur les formes pliées (fautes) ; inclusion des mots pleins, le score croissant avec la part couverte (« Odon » dans « Odon de Brume ») ; sigle (« GdB ») ; prénom suivi d'une initiale (« Jehan L. »).
3. **Trois issues**, seuils provisoires : rattachée au-dessus de 0,90 si le meilleur candidat devance le second d'au moins 0,04 ; **doute** entre 0,80 et 0,90 (ou deux candidats proches : les deux Jehan) ; nouvelle en dessous. Type compatible exigé.
4. **Entités nouvelles regroupées dans le lot** avec le même score, **indépendamment de l'ordre des documents** (R-PRI-03) : forme la plus longue d'abord.

Les règles appuyées sur l'état restent avant ou après le score : titre porté par une seule entité, désignation reliée (E-006). Les règles au cas par cas d'X-002 (nom contenu, partie d'un nom) sont **remplacées** par l'inclusion de mots.

**Texte barré** : la fenêtre repère `~~…~~` ; C1a n'y cherche pas, et une mention du modèle qui n'y est que barrée est écartée (pas « introuvable »).

**Contrôles après C5** : relation du schéma aux types incompatibles écartée ; alias égal au nom écarté ; valeur proche de la valeur connue ramenée à celle-ci (support).

## Résultats (rejeu, aucun appel)

| | Avant (X-006, X-002) | Après |
|---|---|---|
| Corbelle, C2 : bien recoupées | 29 / 35 | **34 / 35** |
| Corbelle, fausses créations | 8 | **3** (« apothicairerie », « fête des lanternes », « Rouquine ») |
| Corbelle, gestes simulés (mentions) | 48 | **42** |
| Valmont, C2 : bien recoupées | 27 / 28 | 27 / 28 (inchangé) |
| Valmont, fausses créations | 1 | 1 (le Roi Gris) |
| Corbelle, C5 seul, entités du gold : précision / rappel | (non mesuré seul) | 0,33 / 0,50, 3 faits écartés par les contrôles |
| Valmont, C5 et question : précision / rappel | 0,88 / 0,82 | 0,88 / 0,82 (inchangé, rien d'écarté) |

Règles qui ont tranché sur Corbelle : nom exact 12, titre 6, **ressemblance 13**, nouvelle 4. Faits écartés sur Corbelle : `bertrand-ostrel rules bateliers` (types), deux alias égaux au nom ; « bourgmèstre » ramené à « bourgmestre ».

Non mesurés par rejeu : la chaîne complète de Corbelle (les entités ont changé, donc les prompts de C5 aussi) et la question ciblée sur Corbelle (les phrases muettes ont changé) ; il faut de nouveaux appels.

## Lecture

1. **Un score général remplace les règles au cas par cas** et règle 5 fausses créations sur 8 sans régression sur Valmont. Les 3 restantes sont hors de portée d'une ressemblance de noms : un nom commun (C1b), une idée d'intrigue (silence, question 10), un surnom (alias à proposer).
2. **Le doute fonctionne** : « jehan » seul entre deux Jehan reste un doute, jamais un rattachement au hasard.
3. **Les contrôles de C5 sont utiles mais limités** : ils écartent ce que le schéma interdit et corrigent les fautes de valeur ; les relations inférées d'une proximité (E-010) restent, et c'est l'essentiel des faux faits sur Corbelle.
4. Les seuils sont des choix provisoires : leur vraie épreuve est un corpus qu'ils n'ont pas vu.
