# Recherche sur l'ingestion : journal

Journal de travail du chantier ingestion ([`../chantier-ingestion.md`](../chantier-ingestion.md), §4). On y consigne les **écarts** observés (fiches `E-nnn`) et les **expériences** menées (fiches `X-nnn`). Ce n'est pas un cadre : une conclusion qui tient passe dans le chantier, puis dans les cadres.

## Méthode

1. Observer un écart précis (faux positif, manque, erreur de type ou de résolution).
2. Le classer (grille H, I, S, G, R, N, T, V, chantier §10.1).
3. Expliquer pourquoi il se produit.
4. Remédier dans l'ordre de préférence :
   1. mesure ou gold ;
   2. règle déterministe ;
   3. consigne ou contexte, mesuré ;
   4. contribution humaine ;
   5. couche spécialisée (expérience).
5. Vérifier : l'écart disparaît-il, sans en créer d'autres ?

Contrainte permanente : on vise un **petit modèle**. Autre limite permanente : tant qu'il n'y a qu'un corpus (Valmont, synthétique et arbitraire), un remède qui marche n'est qu'un candidat ; les exemples des prompts sont pris hors de Valmont pour ne pas les régler sur lui. « Prendre un meilleur modèle » n'est pas un remède. Les mesures faites avec Haiku 4.5 portent la mention « substitut » (chantier §8).

Les axes de test et le plan des corpus sont dans [axes-corpus.md](axes-corpus.md).

## Index

| Fiche | Titre | Classe | Statut |
|---|---|---|---|
| [E-001](E-001-cite-portuaire.md) | « la cité portuaire » prise pour une catégorie | S | ouverte |
| [E-002](E-002-roi-gris.md) | « le Roi Gris » créé au lieu d'un alias d'Aldren II | R, T | ouverte |
| [E-003](E-003-conseil-valeur.md) | « le conseil des marchands » pris pour une valeur, jamais créé | N | résolue sur b1 (C1, C2, C5) |
| [E-004](E-004-depuis-la-chute.md) | « depuis la Chute » donne `odon involved_in la-chute` | H | résolue sur Corbelle par le critique |
| [E-005](E-005-regent-de-brume.md) | « régent de Brume » au lieu de « régent » | S | ouverte |
| [E-006](E-006-designations-nouvelles.md) | des désignations proposées comme entités nouvelles | N | résolue sur b1 |
| [E-007](E-007-hors-schema-omis.md) | une relation hors schéma est omise (« vassal du roi Mervin ») | — | résolue sur b1 |
| [E-008](E-008-variantes-de-surface.md) | une variante de surface d'un nom devient une entité nouvelle (Corbelle) | R | en cours (8 → 3) |
| [E-009](E-009-texte-barre.md) | un texte barré est lu comme une mention | — | résolue sur Corbelle |
| [E-010](E-010-inferences-spatiales.md) | relations inférées d'une proximité (« sur », « près de ») | I | en cours (« près du » douteux, gardé : X-013) |
| [E-011](E-011-controles-c5.md) | faits de C5 qu'un contrôle sans modèle écarterait | S | résolue sur Corbelle |
| [E-012](E-012-question-ciblee-limites.md) | limites de la question ciblée : synonymes, phrases non muettes | — | en grande partie résolue |
| [E-013](E-013-critique-litteral.md) | le critique trop littéral met de côté un fait juste | — | ouverte (la v3 du critique, qui réglait « les bateliers », n'est pas adoptée : X-015 ; aucun faux rejet hors de Corbelle) |
| [E-014](E-014-forme-courte-nouvelle.md) | la forme courte d'une entité nouvelle n'est pas repérée, et l'auteur ne peut pas l'y rattacher (« Ostrel ») | R | en cours (geste fait, repérage ouvert) |

| Expérience | Titre | Statut |
|---|---|---|
| [X-001](X-001-b1-haiku-reference.md) | Mesure de référence : b1 sous Haiku 4.5 (API), extracteur actuel | conclue |
| [X-002](X-002-c1-c2-fenetre.md) | Repérer puis recouper : C1 et C2 sur une fenêtre au document (b1) | conclue (première itération) |
| [X-003](X-003-formes-courtes.md) | Formes courtes : consigne (A) ou règle sans modèle (B) | conclue sur b1, non tranchée |
| [X-004](X-004-c5-faits.md) | C5 : les faits entre entités confirmées (b1) | conclue (première itération) |
| [X-005](X-005-question-ciblee.md) | Question ciblée sur les phrases muettes (hors schéma) | conclue (première itération) |
| [X-006](X-006-corbelle-chaine.md) | La chaîne sur des notes brouillon (Corbelle) | conclue (diagnostic) |
| [X-007](X-007-recoupement-par-score.md) | Recoupement par score, texte barré, contrôles de C5 (sans modèle) | conclue (première itération) |
| [X-008](X-008-consignes-et-question.md) | Consigne stricte pour C5 ; question ciblée avec relations connues et signal par paire | conclue |
| [X-009](X-009-critique.md) | Le critique (C6) : un fait jugé contre son passage | conclue (deux versions) |
| [X-010](X-010-enonciation.md) | Énonciation sans modèle (C4) : rumeur → attribution, note → silence | conclue (première itération) |
| [X-011](X-011-bruit-et-chaine-reelle.md) | Valmont bruité (texte non vu) et chaîne complète de Corbelle | conclue (diagnostic) |
| [X-012](X-012-signaler-et-pieges.md) | Signaler sans décider, et un contre-corpus de pièges | conclue, résultat mitigé |
| [X-013](X-013-stabilite-faits-corbelle.md) | Stabilité de la chaîne des faits sur Corbelle (entités du gold) | conclue |
| [X-014](X-014-candidats-classes.md) | Question ciblée à candidats classés, choix sans modèle (et garde « plus général seul ») | conclue, non adoptée (jeu égal) |
| [X-015](X-015-critique-v3.md) | Critique v3 : fait plus faible impliqué, nom commun pluriel pour une faction | conclue, non adoptée (deux faux rejets sur données non vues) |
| [X-016](X-016-schema-de-genre-pivot.md) | Schéma de genre « fantasy jdr » comme ontologie pivot de l'extraction (correspondance sans modèle, cache) | protocole figé |

Statuts : **ouverte** (observée, non traitée), **en cours** (remède essayé), **résolue** (remède mesuré, sans régression), **acceptée** (on vit avec, avec la raison), **transformée** (devenue une expérience ou une question du chantier).

## Modèle de fiche d'écart

```markdown
# E-nnn — titre court

- **Statut** : ouverte | en cours | résolue | acceptée | transformée
- **Classe** : H | I | S | G | R | N | T | V
- **Où** : lot, document, passage ; couche concernée
- **Observé avec** : modèle, profil, version du prompt, date ; fréquence (n appels sur m)
- **Coût en revue** : geste demandé à l'auteur (fausse anomalie, fausse création, aucun)

## Observation
Texte du passage, sortie obtenue, attendu (gold).

## Explication
Pourquoi le modèle produit cela ; hypothèses, de la plus probable à la moins probable.

## Remèdes envisagés
Dans l'ordre de préférence (mesure, déterministe, consigne, humain, couche), avec ce que chacun coûte.

## Essais
Date, remède, mesure avant et après, effets de bord.

## Conclusion
Ce qu'on retient, et ce qui passe dans le chantier.
```

## Modèle de fiche d'expérience

```markdown
# X-nnn — titre court

- **Statut** : prévue | en cours | conclue
- **Hypothèse** : ce qu'on croit, formulé pour pouvoir être faux
- **Couches et modèles** : ce qui varie, ce qui est fixe
- **Écarts liés** : E-nnn

## Protocole
Entrées (lots, passages), variantes comparées, indicateurs (chantier §9), coût estimé et accord.

## Résultats
Tableau des indicateurs par variante ; exécutions (`runs`) de référence.

## Lecture
Ce que ça confirme ou infirme ; limites (substitut, taille de l'échantillon).
```
