# X-014 — Question ciblée à candidats classés, choix sans modèle

- **Statut** : conclue, **non adoptée** : la version gardée fait jeu égal avec la configuration adoptée sur les deux corpus, pour ~30 % de tokens de plus dans la question ciblée (option `--probe-ranked` conservée)
- **Hypothèse** : si la question ciblée rend plusieurs relations classées, de la plus exacte à la plus générale, une règle sans modèle peut retenir la première connue du schéma (« la mère de » : `mother_of`, puis `parent_of`). Et le critique, informé de la forme exacte, cesse de mettre de côté un fait plus faible que le texte (« maître de la GdB » : `member_of`, E-013).
- **Couches et modèles** : C5, question ciblée v1 + relations connues + signal par paire + **candidats classés**, énonciation, critique v2 (qui reçoit la forme exacte quand le fait retenu est plus général) ; Claude Haiku 4.5 par l'API (`api-haiku`, température 0, substitut).
- **Idée** : de l'auteur, 6 octobre 2026, à la lecture d'X-013.
- **Écarts liés** : E-013, E-010, E-004.

## Protocole

- **Prompt** (règle 6, exemples hors des corpus) : pour chaque relation affirmée, des `candidates` : d'abord le sens exact (`same`), puis les relations plus générales que la phrase **implique nécessairement** (`broader` : « commande la compagnie » implique « fait partie de la compagnie »). Jamais une relation voisine ou devinée (« travailler à côté d'un lieu n'implique pas d'y habiter »). Chaque candidat a son sujet et son objet.
- **Choix** (`choose_candidate`, sans modèle) : le premier candidat connu du schéma dont les types conviennent ; sinon le premier hors schéma ; à défaut le premier. Si le retenu n'est pas le premier, la relation exacte est passée au critique : « le passage dit plus précisément … ; le fait proposé en est une forme plus générale ».
- **Mesure** : une passe (température 0, X-013) sur Corbelle c1 et sur Valmont b1, entités du gold. 43 appels, ~0,058 $. Traces : `llm-log/x014-corbelle/`, `llm-log/x014-b1/`.

## Résultats

| Faits, entités du gold : précision / rappel | Corbelle | Corbelle, questions | Valmont b1 | Valmont b1, questions |
|---|---|---|---|---|
| configuration adoptée (X-013, 6 octobre) | 0,53 / 0,75 | 0,50 / 0,67 | — | — |
| configuration adoptée (X-010, 4 octobre) | 0,59 / 0,83 | 0,71 / 0,83 | 0,82 / 0,82 | — |
| **candidats classés** | **0,53 / 0,75** | 0,57 / 0,67 | **0,72 / 0,77** | 0,73 / 0,80 |

Valmont n'a pas été remesuré aujourd'hui dans la configuration adoptée : une part de l'écart avec 0,82 peut venir d'autre chose (même question qu'en X-013, point 5).

### Ce que le modèle a classé

| Phrase | Candidats | Retenu | Juste ? |
|---|---|---|---|
| « le maitre de la guilde c Bertrand Ostrel » | `master_of` (same), `member_of` (broader) | `member_of` | **oui** : l'effet visé |
| « il bosse pr la guilde » | `works_for` (same), `member_of` (broader) | `member_of` | oui (support) |
| « Depuis la Chute, Odon porte le titre de régent de Brume » | `regent_of` (same), `rules` (broader) | `rules` | oui (support) |
| « Bertrand Ostrell : maître de la GdB » (persos) | `leads_faction` (same), **rien de plus général** | `leads_faction`, hors schéma | non : le critique le met de côté (« maître pourrait être un titre ») ; `member_of` manque toujours |
| « elle tient l'apothicairerie pres du pont-aux-anes. elle deteste les bateliers » | `lives_in` (**broader**) seul | `lives_in` | **non** (E-010) ; et « déteste » **disparaît** |
| « Il gouverne la cité portuaire depuis la Chute » | `involved_in` (**broader**) | `involved_in` | **non** (E-004 revient) ; le critique doute, garde |
| « c'est la vouivre qui la fait deborder » | `causes_flooding_of` (same), `haunts` (broader) | `haunts` | non (rumeur ; retenu par l'énonciation, sans dommage) |
| « mère agathe c la mère d'Ostrel » | — | `parent_of` trouvé par C5 cette fois | — |

## Lecture

1. **Le principe marche quand le modèle sépare bien l'exact du plus général** : `master_of` → `member_of`, `works_for` → `member_of`, `regent_of` → `rules`. La règle sans modèle fait alors ce qu'on attendait d'elle.
2. **Mais « plus général » devient une porte d'entrée pour les inférences** que le critique devait arrêter : « près du » donne `lives_in`, « depuis la Chute » donne `involved_in`, toutes deux marquées `broader`, sans candidat exact. La consigne « jamais une relation voisine ou devinée » ne suffit pas à un petit modèle. C'est la même leçon qu'en X-008 (consigne stricte) : une consigne d'écriture ne retient pas une inférence ; un juge la retient mieux.
3. **E-013 n'est pas réglé** : sur « maître de la GdB », le modèle n'a donné aucun candidat plus général ; le critique n'a donc rien reçu. Et la forme exacte hors schéma (`leads_faction`) a été jugée à son tour trop forte.
4. **Bilan** : Corbelle inchangé (un fait gagné, un perdu), Valmont en baisse (`involved_in` en trop). **Non adoptée.**

## Deuxième version : la garde (rejeu, sans appel)

Règle changée, réponses du modèle rejouées depuis les traces : un candidat « plus général » ne compte que **s'il suit un candidat « même sens »** ; seul, c'est une inférence et rien n'est retenu.

| Faits, entités du gold : précision / rappel | Corbelle | Valmont b1 |
|---|---|---|
| candidats classés, première version | 0,53 / 0,75 | 0,72 / 0,77 |
| **candidats classés, avec la garde** | 0,53 / 0,75 | **0,76 / 0,76** (questions 0,80 / 0,80) |

- Écartés par la garde : `odon involved_in la-chute` (« depuis la Chute », E-004) et `ysolde lives_in pont-aux-anes` de la question ciblée (« près du », E-010). Gardés : `master_of` → `member_of`, `works_for` → `member_of`, `regent_of` → `rules`.
- Corbelle ne bouge pas : C5 produit lui-même `ysolde lives_in pont-aux-anes`, que le critique garde (`unsure`, E-010).
- Ce qui reste sur Valmont relève de C5, pas de la question ciblée : titres « baron de brume », « régent de brume » (E-005), alias « le Roi Gris » (E-002), `cendrelande.category`. L'écart avec 0,82 (X-010) ne se départage qu'en remesurant la configuration adoptée sur b1 aujourd'hui (une passe, ~0,025 $).

## Départage sur Valmont

Configuration adoptée remesurée sur b1 le même jour (16 appels, 0,019 $, `llm-log/x014-b1-adopted/`) : **0,875 / 0,82** (questions 0,89 / 0,80). L'écart avec la version gardée (0,76 / 0,76) vient surtout de **C5**, qui n'a pas répondu à l'identique d'une passe à l'autre malgré la température 0 (titre « baron de brume » en p1 dans une passe, pas dans l'autre). À **réponses de C5 identiques** (rejeu croisé, sans appel) :

| Valmont b1, mêmes réponses de C5 | Faits | Questions |
|---|---|---|
| configuration adoptée | 0,875 / 0,82 | 0,89 / 0,80 |
| candidats classés + garde | 0,82 / 0,82 | 0,89 / 0,80 |

Seule différence : un support de plus (`regent_of` → `rules`, déjà dans l'état, sans coût en revue). **Jeu égal**, comme sur Corbelle. La variante coûte plus de tokens (question ciblée : 4 017 contre 2 869 en entrée sur b1, 6 232 contre 5 194 sur Corbelle) sans rien rapporter de mesurable : **non adoptée**.

Leçon de mesure : à température 0, C5 est stable sur Corbelle (X-013, trois passes identiques) mais **pas parfaitement sur b1**. Pour comparer deux variantes d'une couche aval, rejouer les mêmes réponses de l'amont plutôt que relancer toute la chaîne.

## Suite

- La garde reste utile si l'on revient aux candidats classés (un corpus où les relations du schéma sont plus générales que les tournures du texte : là, la variante pourrait rapporter).
- Pour E-013, reste la consigne du critique (« un fait plus faible que le passage est soutenu »).
