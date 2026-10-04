# X-011 — Valmont bruité (texte non vu) et chaîne complète de Corbelle en conditions réelles

- **Statut** : conclue (diagnostic)
- **Hypothèses** :
  1. les seuils du recoupement par score et les marqueurs d'énonciation, réglés sur Valmont et Corbelle, tiennent sur un texte qu'ils n'ont pas vu (Valmont b1 bruité par script, deux niveaux) ;
  2. la chaîne complète (C1, C2, C5, question ciblée, énonciation, critique), nourrie par ses propres entités et non par celles du gold, garde l'essentiel de la qualité mesurée avec les entités du gold.
- **Couches et modèles** : chaîne d'X-010 ; Claude Haiku 4.5 par l'API (`api-haiku`, substitut).
- **Corpus** : [Valmont bruité](../../corpus/valmont-bruite-v1/README.md) (dérivé, l1 léger, l2 fort) ; Corbelle (ciblé).

## Protocole

Valmont bruité, par niveau : C1b en direct (2 appels), puis les faits sur la chaîne (C5, question ciblée, critique). Corbelle : C1 rejoué (X-006), faits, question et critique en direct. ~65 appels, ~0,08 $. Traces : `llm-log/xb-*`.

## Résultats

### Mentions (C1, C2)

| | Valmont propre | l1 (léger) | l2 (fort) | Corbelle |
|---|---|---|---|---|
| Sans modèle : mentions trouvées | 17 / 28 | 18 / 28 | 13 / 28 | 17 / 36 |
| Avec Haiku : mentions trouvées | 28 / 28 | 27 / 28 | 23 / 28 | 35 / 36 |
| Bien recoupées | 27 / 28 | 25 / 27 | 21 / 23 | 34 / 35 |
| Fausses créations (après correction ci-dessous) | 1 (Roi Gris) | 1 (Roi Gris) | 2 (Roi Gris, « vallee ») | 2 (« apothicairerie », « Rouquine ») |
| Attributions trouvées / attendues | 1 / 1 | 1 / 1 | 1 / 1 | 1 / 1 |

### Faits (chaîne complète)

| Précision / rappel | Faits | Questions |
|---|---|---|
| l1 (léger) | 0,85 / 0,65 | 0,88 / 0,70 |
| l2 (fort), avant correction de la mesure | 0,53 / 0,53 | 0,33 / 0,30 |
| Corbelle, chaîne complète | 0,44 / 0,58 | 0,33 / 0,50 |
| Corbelle, entités du gold (X-010, rappel) | 0,59 / 0,83 | 0,71 / 0,83 |

## Ce que le bruit a révélé, et ce qui a été corrigé

1. **Mesure : une entité nouvelle se compare par ses mentions, pas par son nom.** Au niveau l2, le conseil des marchands n'apparaît que comme « CdM » : la chaîne en fait bien une entité nouvelle unique, nommée `cdm` ; le gold l'appelle `conseil-marchands`. Cinq faits justes comptaient manqués et en trop. Désormais, la mesure rapproche une entité nouvelle de la chaîne de celle du gold par les mentions qu'elles recouvrent (le nom d'une entité nouvelle est un choix de surface, que l'auteur fixe). Le chiffre l2 corrigé demande une nouvelle passe (les entités ont aussi changé, point 2).
2. **Désignation avec un nom fautif** : « port de Burme », « royaume de vaalmont » devenaient des entités nouvelles ; la règle « <titre> de <nom connu> » exige désormais un nom connu *ressemblant* (même score que le recoupement), pas identique : ce sont maintenant des doutes, avec l'indice. Rejeu des mentions : aucune régression sur les quatre corpus.

## Lecture

1. **Le recoupement par score tient sur un texte non vu** : 25 sur 27 (l1) et 21 sur 23 (l2) bien recoupées, aucune fausse création due à une faute sur un nom connu. Les seuils n'étaient donc pas réglés « sur mesure » pour Corbelle.
2. **L'énonciation tient** : la rumeur trouvée dans les quatre corpus, aucun faux positif.
3. **Ce qui casse quand le bruit est fort** :
   - C1 sans modèle ne trouve que les noms exacts (« la chuute », « Brme », « hautvl » lui échappent) ; le modèle en rattrape une partie. Piste : chercher aussi les noms connus *ressemblants* dans le texte (même score), sans modèle ;
   - un nom commun ou générique repéré comme entité (« vallee », « apothicairerie ») crée une fausse entité, qui attire des faits ;
   - un sigle d'entité nouvelle jamais développé (« CdM ») : la chaîne ne peut pas savoir qu'il s'agit du conseil des marchands ; c'est à l'auteur (annotation) ou à un autre document du lot.
4. **La chaîne complète perd par rapport aux entités du gold sur Corbelle** (0,44 / 0,58 contre 0,59 / 0,83) : propagation des erreurs de l'amont (fausse entité « apothicairerie »), et **variabilité de C5 d'une passe à l'autre** (titres « bourgmestre » et « abbesse », « Ostrel membre de la guilde » oubliés cette fois-ci, trouvés en X-008). Une seule passe ne suffit plus pour comparer des variantes de C5 : il faut mesurer la stabilité ou plusieurs passes.
5. **Descriptions prises pour des attributs** : « ~45 ans », « vieille » → `condition` ; le critique les a jugées soutenues. Le schéma n'a pas d'attribut d'âge ni d'apparence ; c'est la place des notes et facettes (chantier §10.6).
6. Reste à corriger : un alias égal au nom d'une entité nouvelle, écrit comme attribut simple, n'est pas écarté par les contrôles (identifiant de l'entité nouvelle différent entre le modèle et la chaîne).
