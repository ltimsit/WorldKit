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

## Index

| Fiche | Titre | Classe | Statut |
|---|---|---|---|
| [E-001](E-001-cite-portuaire.md) | « la cité portuaire » prise pour une catégorie | S | ouverte |
| [E-002](E-002-roi-gris.md) | « le Roi Gris » créé au lieu d'un alias d'Aldren II | R, T | ouverte |
| [E-003](E-003-conseil-valeur.md) | « le conseil des marchands » pris pour une valeur, jamais créé | N | ouverte |
| [E-004](E-004-depuis-la-chute.md) | « depuis la Chute » donne `odon involved_in la-chute` | H | ouverte |
| [E-005](E-005-regent-de-brume.md) | « régent de Brume » au lieu de « régent » | S | ouverte |
| [E-006](E-006-designations-nouvelles.md) | des désignations proposées comme entités nouvelles | N | ouverte |

| Expérience | Titre | Statut |
|---|---|---|
| [X-001](X-001-b1-haiku-reference.md) | Mesure de référence : b1 sous Haiku 4.5 (API), extracteur actuel | conclue |
| [X-002](X-002-c1-c2-fenetre.md) | Repérer puis recouper : C1 et C2 sur une fenêtre au document (b1) | conclue (première itération) |
| [X-003](X-003-formes-courtes.md) | Formes courtes : consigne (A) ou règle sans modèle (B) | conclue sur b1, non tranchée |

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
