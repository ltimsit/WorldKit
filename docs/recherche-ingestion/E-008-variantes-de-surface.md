# E-008 — Une variante de surface d'un nom devient une entité nouvelle

- **Statut** : en cours (5 fausses créations sur 8 réglées sans modèle)
- **Classe** : R (recoupement) sur une forme de surface (AX-S1, S3, S4, S5, AX-R1, AX-C3)
- **Où** : Corbelle c1 ; couche C2 (et C1b pour les noms communs)
- **Observé avec** : Claude Haiku 4.5 pour C1b, C2 déterministe, 4 octobre 2026 ([X-006](X-006-corbelle-chaine.md)) ; deux passes identiques
- **Coût en revue** : 8 fausses créations à refuser, puis des faits rattachés à de fausses entités (C5 sur la chaîne : précision 0,18)

## Observation

| Mention (C1b) | Recoupée en | Attendu | Nature de l'écart |
|---|---|---|---|
| « Jehan Marcastell » | nouvelle | Jehan Marcastel | faute (lettre doublée) |
| « pont-aux-anes » | nouvelle | le Pont-aux-Ânes | accents et casse |
| « st fiacre » | nouvelle | l'abbaye Saint-Fiacre | abréviation, casse, trait d'union, nom partiel |
| « GdB » | nouvelle | la Guilde des Bateliers | sigle |
| « Jehan L. » | nouvelle | Jehan Leblond | initiale du nom de famille |
| « Bertrand Ostrell » / « Ostrel » | trois entités nouvelles (« bertrand ostrel », « bertrand ostrell », « ostrel ») | une seule | faute et nom seul sur une entité **nouvelle** |
| « Rouquine » | nouvelle | Ysolde (surnom donné dans la même ligne) | surnom |
| « apothicairerie », « fête des lanternes » | nouvelles | rien | nom commun ; idée d'intrigue (passage à silence attendu) |

## Explication

C2 ne connaît que l'égalité de noms normalisés (casse, espaces, article) et quelques règles de forme (titre, nom contenu, partie d'un nom). Sur Valmont, les noms étaient bien écrits ; ici, la moindre variante tombe en « nouvelle ». Le regroupement des nouvelles dans le lot (T-ING-07) n'a lui aussi que l'égalité.

## Remèdes envisagés

1. *Mesure* : aucun.
2. *Déterministe*, dans C2, chacun avec abstention (doute) si plusieurs candidats :
   - pliage des accents et des signes (« pont-aux-anes » = « Pont-aux-Ânes ») ;
   - abréviations usuelles (« st », « ste » → saint, sainte) et nom partiel contenu ;
   - distance d'édition faible pour un nom assez long, à type compatible (« Marcastell ») ;
   - sigle formé des initiales des mots pleins d'un nom connu (« GdB » : Guilde des Bateliers) ;
   - prénom suivi d'une initiale (« Jehan L. » : le seul Jehan dont le nom commence par L) ;
   - les mêmes règles entre entités **nouvelles** du lot (« Ostrell » = « Ostrel », « Ostrel » = partie de « Bertrand Ostrel »).
3. *Consigne* : aucune ; c'est au recoupement de tolérer.
4. *Humain* : l'auteur rattache en un geste ; une variante rattachée devient un alias (§6.3) et la fois suivante est exacte.
5. *Couche* : liste courte au modèle pour les cas où plusieurs règles divergent (plus tard).

Surnom et noms communs : à traiter à part (surnom donné explicitement : alias proposé ; nom commun : C1b ; idée d'intrigue : silence, question 10 du chantier).

## Essais

- **4 octobre 2026, [X-007](X-007-recoupement-par-score.md)** : recoupement par score (pliage, Jaro-Winkler, inclusion de mots, sigle, initiale ; trois issues ; regroupement des nouvelles indépendant de l'ordre). Corbelle : bien recoupées 29 → 34 sur 35, fausses créations 8 → 3 ; Valmont inchangé. Restent « apothicairerie » (nom commun), « fête des lanternes » (idée d'intrigue), « Rouquine » (surnom).
