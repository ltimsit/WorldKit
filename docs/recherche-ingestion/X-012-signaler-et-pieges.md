# X-012 — Signaler sans décider, et un contre-corpus de pièges

- **Statut** : conclue — **résultat mitigé, aucune règle adoptée**
- **Hypothèses** :
  1. au lieu de règles qui décident, des **signaux** (un nom connu ressemblant devient une mention douteuse ; une entité nouvelle peu sûre, en minuscules et vue une seule fois, devient un doute) aident sans nuire ;
  2. un contre-corpus de pièges (homographes de noms connus) chiffre les faux positifs de ces signaux et des règles existantes.
- **Prudence de l'auteur, à garder en tête** : on tire des conclusions de petits corpus écrits par Claude, en simulant le rôle de l'auteur au lieu de l'exercer. Ce genre de problème (homographes, noms communs, faux rattachements) demande l'ingestion réelle avec l'étape d'annotation pour être jugé.

## Ce qui a été construit (options, pas des défauts)

- `--signals` (mentions et chaîne) : `similar_mentions`, une suite de mots ressemblant à un nom connu (même score que le recoupement, même initiale) qu'aucune mention ne couvre devient une mention **douteuse** avec son candidat, jamais rattachée d'office ; une entité nouvelle en minuscules, vue une seule fois dans le lot, devient un **doute** (« à confirmer comme nouvelle »).
- `--checkpoint` (chaîne) : l'auteur **simulé** confirme les entités avant les faits (§6.5), d'après le gold.
- Gestes : un doute dont le bon choix est proposé se règle en un geste de confirmation.
- Contre-corpus `corpus/pieges-v1/` : six passages sur le monde de Valmont, homographes de noms connus (axe AX-R11).

## Résultats (rejeu, un appel pour le contre-corpus)

Signaux, gestes simulés (mentions) :

| | sans | avec |
|---|---|---|
| Valmont propre | 35 | 36 |
| Corbelle | 41 | 44 |
| Valmont bruité l1 | 36 | 37 |
| Valmont bruité l2 | 45 | **39** |

Contre-corpus (6 passages, 5 mentions au gold) :

| | Faux positifs | Lesquels |
|---|---|---|
| sans modèle (règle exacte actuelle) | 2 | « une brume épaisse » → la ville de Brume ; « les veilleurs de nuit » → l'ordre des Veilleurs |
| sans modèle, avec signaux | 4 | en plus : « cendre » ≈ Cendrelande, « le cercle des (anciens) » ≈ Cercle des Cendres (doutes) |
| avec Haiku | 4 | les deux de la règle exacte ; « veilleurs de nuit de Hautval » rattaché aux Veilleurs par le **score** ; « temple » créé |
| avec Haiku et signaux | 6 | « temple » devient un doute, mais deux doutes de ressemblance en plus |

Le modèle, lui, évite presque tous les pièges : « brune », « une chute », « un loup », « une morsure », « le cercle des anciens », « la flamme » ne sont pas relevés.

## Lecture

1. **Les signaux aident sous un bruit fort et coûtent un peu partout ailleurs** : aucune généralisation possible ; ils restent une option.
2. **La règle exacte actuelle et le recoupement par score se font prendre par les homographes** : la casse ne protège plus quand on la tolère (AX-S4 et AX-R11 tirent en sens contraires) ; un score de ressemblance rattache « veilleurs de nuit » à un ordre qui s'appelle « les Veilleurs ». Le texte seul ne tranche pas : il faut le **contexte** (le modèle, qui s'en sort mieux ici) ou **l'auteur**.
3. **Le bon arbitre de ces cas est l'annotation** : un faux rattachement corrigé une fois (« les veilleurs de nuit ne sont pas les Veilleurs ») devrait l'être pour la suite. C'est ce que la mesure ne sait pas simuler honnêtement, et ce qui motive la mise en place de l'ingestion avec l'étape d'annotation.
4. Limites : 6 passages ; corpus et pièges écrits par Claude.
