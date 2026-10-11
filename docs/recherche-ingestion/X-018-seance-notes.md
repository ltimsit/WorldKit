# X-018 — Séance réelle de la couche « descriptions » (J9) : l'auteur sur ses notes de Corbelle

- **Statut** : conclue (bilan d'une séance ; mesure de « fini » du jalon J9, question 6, option A)
- **Hypothèse** : les gestes réels de l'auteur sur les notes disent ce que la couche vaut et ce qui coûte, mieux qu'un gold écrit par Claude (leçon de X-017).
- **Couche et modèle** : couche « descriptions » (`NoteFinder`, prompt `notes-1`), Claude Haiku 4.5 par l'API (`api-haiku`, profil des faits).
- **Données** : `corbelle.db`, source `corbelle-notes-en-vrac` (9 passages), après les entités et les faits de X-017 ; facettes ajoutées par une édition de schéma ; exécutions enregistrées ; 11 octobre 2026, deux passes (10 h 55 et 20 h 11, heure du serveur).

**Limites** : une source, une séance ; entre les deux passes, deux correctifs (garde-fou des faits gardés, règle de relance) ; durée non mesurée (T3).

## Coût

| Passe | Appels | Coût | Bribes proposées | Écartées par les contrôles |
|---|---|---|---|---|
| 1 | 1 | 0,0036 $ | 4 | 1 |
| 2 (relance) | 1 | 0,0040 $ | 5 | 1 |

## Gestes

| Geste | Nombre | Détail |
|---|---|---|
| garder | 5 | toutes les bribes de la passe 2 |
| retirer | 4 | les 4 bribes de la passe 1, **réapparues par un défaut** (voir plus bas) : gestes inutiles |
| corriger | 1 | Corbelle : facette « aspect » → « autre » |
| revue : accepter | 4 | un lot par passage (p1, p2, p6, p7) |

Les 5 bribes gardées, acceptées en revue, sont dans l'état :

| Passage | Sujet | Facette | Citation | Forme courte |
|---|---|---|---|---|
| p1 | Corbelle | aspect → **autre** | « corbelle c'est la ville sur la sorgue, genre 2000 habitants » | population : environ 2000 habitants |
| p2 | Jehan Marcastel | caractère | « un type mou » | caractère : mou |
| p2 | Jehan Marcastel | autre | « tout le monde sait que c sa soeur qui decide » | autorité réelle : sa sœur décide à sa place |
| p6 | Bertrand Ostrel | caractère | « Ostrel est pas fiable, il magouille » | fiabilité : pas fiable · comportement : magouille |
| p7 | Jehan Leblond | histoire | « le passeur (jehan leblond) faisait passer les gens avant la grande crue, maintenant il bosse pr la guilde » | activité passée, activité présente |

**Pertinence** : 5 bribes sur 5 gardées ; la couche a bien pris ce que les faits laissaient (un jugement, un portrait, une histoire). La passe 2 a mieux découpé p2 (deux bribes : le caractère, et qui décide). **Une facette fausse sur 5** : « population » rangée en « aspect ».

## Écarts

1. **Bribes d'une passe ancienne réapparues** (défaut, corrigé) : le dernier lancement d'une couche était lu dans les seules annotations courantes ; quand l'auteur a gardé toutes les bribes de la passe 2, plus aucune n'était « courante », et la passe 1 est redevenue la dernière. Quatre retraits inutiles. Corrigé : la dernière passe se lit dans tout l'historique (vaut pour les trois couches ; un numéro de passe n'est plus réutilisé). Le premier diagnostic (une reformulation de la forme courte) était incomplet ; la règle de relance normalisée qu'il a donnée reste utile.
2. **Une relation répétée en note** (« elle deteste les bateliers », passe 1) : corrigé avant la passe 2 (faits connus dits en clair, garde-fou sans modèle, R-NTE-05) ; la passe 2 l'a écartée.
3. **Facette forcée** : « population : environ 2000 habitants » rangée en « aspect » (apparence d'un lieu) faute de mieux. Remèdes possibles : une définition d'une ligne par facette dans le schéma (indication, chantier §10.5), ou, comme le propose l'auteur, un attribut `population` dans le schéma — ce serait alors un **fait**, et la note ne le répéterait plus (R-NTE-05).
4. **Hésitation gardée en note** (« genre 2000 habitants jsp encore ») : l'auteur l'a gardée en connaissance de cause. Décision de l'auteur : **pas de règle sans modèle** sur les marques de doute (trop propre à ce passage, le doute s'exprime de mille façons) ; l'auteur tranche ; une consigne au modèle (« écarter ce qui est donné comme incertain ») est à envisager plus tard, mesurée (coût, fiabilité).

## Décisions de l'auteur sur la suite (chantier §10.6)

- **Synthèse des formes courtes** : pas maintenant ; garder les notes séparées, une ligne par note, même si plusieurs lignes disent un même aspect (« X lignes de comportement ne me dérangent pas »). La séparation sert aussi la future détection des incohérences.
- **Hésitations** : voir l'écart 4.

## Lecture

La couche coûte peu (un appel par passe, moins d'un centime) et vise juste sur ce texte ; le coût de la séance est venu de **deux défauts de l'atelier**, tous deux corrigés le jour même, et d'une facette forcée. Prochaines pistes, sans urgence : définitions de facettes (§10.5), l'attribut `population` dans le monde de l'auteur, une consigne mesurée sur les hésitations.
