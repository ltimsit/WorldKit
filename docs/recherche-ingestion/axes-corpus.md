# Axes de test des corpus d'ingestion

Référence pour concevoir et lire les corpus de test : chaque **axe** est une façon dont un texte réel s'écarte d'un texte propre, avec l'identifiant à citer (`AX-S3`), un exemple, ce qu'on attend de la chaîne, et la couche qu'il éprouve. Les corpus déclarent les axes qu'ils couvrent ; les fiches d'écart citent l'axe en cause. Voir aussi le chantier (§12) et le journal ([README](README.md)).

Couches : C0 découpage, C1a noms connus, C1b repérage par le modèle, C2 recoupement, C5 faits, question ciblée (phrases muettes), C4 notoriété et énonciation ; « noyau » pour la qualification.

## Sortes de corpus

| Sorte | Qui l'écrit | Sert à | Biais |
|---|---|---|---|
| **Dérivé** | un script, à partir d'un corpus existant (perturbations contrôlées, taux réglable) | mesurer la robustesse axe par axe ; le gold du corpus source reste valable | aucun sur le fond ; le désordre est artificiel (régulier) |
| **Ciblé** | Claude, petit, quelques axes à la fois | éprouver une couche sur un phénomène précis, construire un modèle solide | optimiste : faux naturel, et même famille que le modèle testé (T-TST-01) |
| **Auteur** | l'auteur, ses vraies habitudes | la mesure qui compte : choisir le modèle, valider l'architecture sur des cas réels | aucun ; gold proposé par la chaîne puis corrigé, biais signalé |

## 1. Surface du texte (AX-S)

| Axe | Phénomène | Exemple | Attendu | Couches |
|---|---|---|---|---|
| AX-S1 | faute de frappe ou d'orthographe sur un **nom** | « Odonn », « Hautvall », « Marcastell » | rattaché à l'entité connue, jamais une entité nouvelle ; au pire un doute | C1a, C1b, C2 |
| AX-S2 | faute sur un **terme** ou une valeur | « apothicairerie », « bourgmèstre » | valeur ramenée à sa forme juste, ou signalée | C5, normalisation |
| AX-S3 | **accents** oubliés | « Abbesse Agathe », « l'eglise », « frere » | comme AX-S1 | C1, C2 |
| AX-S4 | **casse** incohérente | « corbelle », « CORBELLE », « la guilde des bateliers » | même entité | C1a, C2 |
| AX-S5 | **abréviations**, sigles | « le GdB » (Guilde des Bateliers), « bcp », « pr », « cf. » | sigle rattaché s'il est défini ou évident ; sinon doute | C1b, C2 |
| AX-S6 | **ponctuation** absente ou irrégulière, phrases sans majuscule, une phrase interminable | « jehan il est mou sa soeur decide tout » | mêmes faits que la version ponctuée ; découpage en phrases robuste | C0, C5, question ciblée |
| AX-S7 | **registre familier**, oralité | « le baron il est pas net », « bref », « genre » | les faits seulement, pas le ton | C5 |
| AX-S8 | **symboles** à la place de mots | « Jehan → bourgmestre », « Ysolde = soeur de Jehan », « ?? » | lus comme des affirmations (ou des doutes pour « ? ») | C5 |
| AX-S9 | **langues mêlées** | « the Guild runs the docks », « cf. le lore » | valeurs et alias dans la bonne langue | C1, C5 |

## 2. Structure (AX-T)

| Axe | Phénomène | Exemple | Attendu | Couches |
|---|---|---|---|---|
| AX-T1 | **télégraphique**, sans verbe | « Ysolde : apothicaire, pont, déteste bateliers » | faits retrouvés | C5 |
| AX-T2 | **listes à puces** | « - bourgmestre : Jehan » | une puce = une unité, contexte du titre | C0, C5 |
| AX-T3 | **tableaux**, fiches de stats dans le texte | « PV 12, FOR 14 » | méta, jamais un fait du monde (R-DEC-05) | C0, méta |
| AX-T4 | **document long**, au-delà du budget | chronique de 20 pages | découpage déterministe, références d'une fenêtre à l'autre | C0, C1, C5 |
| AX-T5 | **document minuscule** | une ligne | aucune perte | toutes |
| AX-T6 | **plusieurs sujets** sans titre | notes en vrac | chaque fait rattaché au bon sujet | C1, C5 |
| AX-T7 | **renvois** | « voir plus haut », « comme dit avant » | la référence suivie si elle est dans la fenêtre | C5 |
| AX-T8 | **dialogue** | « — T'as vu le passeur ? » | énonciation : paroles rapportées | C4 |

## 3. Énonciation et statut (AX-E)

| Axe | Phénomène | Exemple | Attendu | Couches |
|---|---|---|---|---|
| AX-E1 | **note de travail de l'auteur** | « TODO : trouver un nom pour la taverne », « à creuser » | **silence** : aucun fait, aucune entité | C1b, C5 |
| AX-E2 | **hors sujet** | « acheter des dés », « session décalée à jeudi » | silence | C1b, C5 |
| AX-E3 | **hésitation, alternative** | « soit c'est Ysolde soit l'abbesse », « peut-être » | aucun fait certain ; au mieux une piste d'auteur (R-SCN-09) | C5 |
| AX-E4 | **correction en cours d'écriture** | « non en fait c'est son cousin », `~~sa soeur~~ son cousin` | la dernière version seule, pas de contradiction | C5 |
| AX-E5 | **idée d'intrigue**, futur | « le passeur pourrait trahir la guilde » | piste d'auteur proposée, pas un fait (R-SCN-09) | C5 |
| AX-E6 | **voix d'un document du monde** | chronique, lettre, mensonge d'un personnage | affirmations, pas des faits (R-DOC-06 à 08) | C4 |
| AX-E7 | **rumeur**, ouï-dire | « on dit que », « paraît que » | attribution, aucun fait (R-DEC-03) | C4 |
| AX-E8 | **secret** | « personne ne le sait mais » | notoriété secrète proposée (R-NOT) | C4 |
| AX-E9 | **opinion** de l'auteur sur un personnage | « un type mou », « elle est géniale » | pas un fait du monde (sauf trait de caractère explicite) | C5 |

## 4. Référence et identité (AX-R)

| Axe | Phénomène | Exemple | Attendu | Couches |
|---|---|---|---|---|
| AX-R1 | **prénom seul**, nom de famille seul | « Jehan », « Marcastel » | rattaché si une seule personne convient | C1, C2 |
| AX-R2 | **homonyme** | deux « Jehan » | doute, jamais un rattachement au hasard | C2 |
| AX-R3 | **surnom**, épithète | « le Mou », « la Rouquine » | doute ou alias proposé ; l'auteur tranche | C1b, C2 |
| AX-R4 | **fonction**, titre | « le bourgmestre », « l'abbesse » | titre porté par une seule entité : rattaché | C1a, C2 |
| AX-R5 | **description** seule | « le vieux du phare » | entité nouvelle ou doute | C1b, C2 |
| AX-R6 | **anonyme**, générique | « un garde », « les gens du port » | aucune entité | C1b |
| AX-R7 | **pronom** ambigu | « il » entre deux hommes | rattaché si le document tranche ; sinon rien | C5 |
| AX-R8 | **lieu et personne** de même nom | « Brume » et « Odon de Brume » | deux entités, imbriquées | C1, C2 |
| AX-R9 | **renommage**, identité double | « l'ancien nom de la ville » | alias, ou identité (R-IDT) par décision de l'auteur | C2 |
| AX-R11 | **homographe** d'un nom connu | « une brume épaisse » (brouillard) à côté de la ville de Brume ; « les veilleurs de nuit » à côté de l'ordre des Veilleurs | aucune mention ; au pire un doute | C1a, C1b, C2 |
| AX-R10 | **groupe** désigné de plusieurs façons | « les Bateliers », « la guilde », « le GdB » | une seule entité | C1, C2 |

## 5. Temps (AX-D)

| Axe | Phénomène | Exemple | Attendu | Couches |
|---|---|---|---|---|
| AX-D1 | **passé révolu** | « régnait autrefois », « était passeur avant la crue » | pas un fait actuel | C5, question ciblée |
| AX-D2 | **changement d'état** | « était bourgmestre, maintenant ruiné » | l'état actuel seul (le passé : fenêtre de validité, préparée) | C5 |
| AX-D3 | **date relative** | « il y a trois ans », « l'hiver dernier » | sans date absolue, pas de valeur inventée | C5 |
| AX-D4 | **repère de temps** | « depuis la crue » | pas une relation | C5 |
| AX-D5 | **futur**, projet | « va épouser » | pas un fait ; piste d'auteur au mieux | C5 |

## 6. Le jeu lui-même (AX-J)

| Axe | Phénomène | Exemple | Attendu | Couches |
|---|---|---|---|---|
| AX-J1 | **compte rendu de session** | « les joueurs ont tué la vouivre » | ce qui s'est passé dans le monde, distingué de la table | C5, déroulés |
| AX-J2 | **personnages joueurs** | « Bram (joué par Léa) » | le joueur n'est pas une entité du monde | C1b |
| AX-J3 | **règles mêlées à la fiction** | « jet de Perception raté », « niveau 5 » | méta, pas un fait | méta |
| AX-J4 | **préparation de partie** | « scène 2 : l'embuscade » | piste ou déroulé, pas un fait | C5 |

## 7. Échelle et monde (AX-M)

| Axe | Phénomène | Attendu | Couches |
|---|---|---|---|
| AX-M1 | **monde persistant** de plusieurs centaines d'entités | recoupement exact et rapide, liste courte au modèle seulement en cas d'ambiguïté | C1a, C2 |
| AX-M2 | **autre genre** (science-fiction, contemporain, horreur) | prompts et heuristiques sans hypothèse de fantasy (ex. le type « personne » de la variante B) | toutes |
| AX-M3 | **schéma pauvre ou absent** | hors schéma regroupé par l'ontologiste, propositions à l'auteur (§6.6) | question ciblée, ontologiste |
| AX-M4 | **types propres au monde** | `MonasticOrder`, `Starship` | types reconnus, héritage respecté | C1b, C2 |

## 8. Plusieurs documents (AX-C)

| Axe | Phénomène | Attendu | Couches |
|---|---|---|---|
| AX-C1 | **contradiction** entre documents | collision détectée par le noyau (R-FAI-05), jamais tranchée par un modèle | noyau |
| AX-C2 | **nouvelle version** d'une note | diff, cache, mémoire des décisions (T-ING-10) | ingestion |
| AX-C3 | **entité présentée ici, évoquée ailleurs** | une seule entité dans le lot (T-ING-07) | C2 |
| AX-C4 | **doublon** d'information | support, pas une nouvelle proposition (T-ING-11) | noyau |

## Plan des corpus

| Corpus | Sorte | Axes principaux | État |
|---|---|---|---|
| Valmont v1 | ciblé (premier jet) | règles du cadre ; AX-R4, AX-R8, AX-D1, AX-D4, AX-E7, AX-E8, AX-C1 à C4 | fait |
| **Corbelle, brouillon** (`corpus/corbelle-v1/`) | ciblé | AX-S1 à S8, AX-T1, T2, T6, AX-E1 à E5, E9, AX-R1 à R6, R10, AX-D1 à D4 | fait, mesuré ([X-006](X-006-corbelle-chaine.md)) |
| **Valmont bruité** (`corpus/valmont-bruite-v1/`) | dérivé (script) | AX-S1, S3, S4, S5, S6 à deux niveaux | fait, mesuré ([X-011](X-011-bruit-et-chaine-reelle.md)) |
| **Pièges** (`corpus/pieges-v1/`) | ciblé | AX-R11 (homographes) | fait, mesuré ([X-012](X-012-signaler-et-pieges.md)) |
| Session | ciblé | AX-J1 à J4, AX-D, AX-E5 | prévu |
| Valmont grossi | dérivé (généré) | AX-M1, AX-R2 | prévu |
| Autre genre | ciblé | AX-M2 à M4 | prévu |
| Chronique longue | ciblé | AX-T4, AX-T7, AX-R7 | prévu |
| Notes réelles de l'auteur | auteur | tous, dans leurs vraies proportions | plus tard, sur la base du modèle établi |

## Extensions du gold demandées par ces axes

- **Silence attendu** : un passage (ou une phrase) qui ne doit produire ni entité ni fait (AX-E1, AX-E2). Champ `silent: author_note | off_topic | hesitation | plot_idea` sur le passage.
- **Mentions fautives** : la forme telle qu'écrite, rattachée à l'entité (« Marcastell » → `jehan-marcastel`) ; c'est le format actuel des `mentions`.
- **Doute attendu** : une mention qui doit rester un doute (homonyme, surnom inconnu) : valeur `doubt:` suivie des candidats (`doubt:jehan-marcastel|jehan-leblond`).
- **Piste attendue** : une idée d'intrigue qui devrait devenir une piste d'auteur (R-SCN-09), à mesurer plus tard.
