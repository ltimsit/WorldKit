# X-003 — Formes courtes : consigne (A) ou règle sans modèle (B)

- **Statut** : conclue sur b1, **non tranchée** (les deux variantes font jeu égal sur ce corpus)
- **Hypothèse** : les mentions manquées par C1 en X-002 (« Odon » seul, « le baron ») se récupèrent soit par une consigne de plus au modèle (A), soit par une règle déterministe (B), et la mesure dit laquelle choisir.
- **Couches et modèles** : C1a, C1b, C2 de [X-002](X-002-c1-c2-fenetre.md) ; Claude Haiku 4.5 par l'API (substitut).
- **Écarts liés** : formes courtes d'X-002 ; [E-006](E-006-designations-nouvelles.md) (ouvert en cours de route).

**Limite à garder en tête** : un seul corpus, synthétique et arbitraire (Valmont, lot b1, 28 mentions). Un remède qui marche ici n'est pas encore une règle ; il devient un candidat à éprouver sur d'autres corpus.

## Protocole

Trois remèdes, mesurés contre les mentions du gold de b1 :

1. **Titres uniques dans C1a** (sans modèle, appliqué d'office : c'est la règle de titre que C2 utilisait déjà) : « le <titre> » est cherché quand le titre est porté aujourd'hui par une seule entité (« le baron » : Odon) ; un titre partagé (« le roi » : Aldren II et Mervin) ne l'est pas.
2. **Variante A, consigne** : une règle de plus dans le prompt de C1b, « relève aussi chaque forme plus courte ou chaque désignation d'une entité déjà relevée », avec un exemple **pris hors de Valmont** (« Marianne » pour « Marianne Ostrel », « le capitaine ») pour ne pas régler le prompt sur le corpus. 2 appels (`llm-log/x003/`), 0,005 $, au plus 1 049 tokens par appel.
3. **Variante B, sans modèle** : les mots d'un nom de personne repérée (« Odon » dans « Odon de Brume ») sont cherchés dans le document, sauf un mot qui est lui-même un nom connu (« Brume ») ou qui appartient au nom de plusieurs personnes ; recherche sensible à la casse.

Toutes les combinaisons sont remesurées **par rejeu** des réponses tracées (X-002 et X-003), sans nouvel appel.

## Résultats

| | Mentions du gold trouvées | Bien recoupées | En trop | Gestes pondérés |
|---|---|---|---|---|
| Sans modèle (C1a avec titres, C2) | 18 / 28 | 18 / 18 | 3 | 51 |
| Sans modèle + B | 22 / 28 | 22 / 22 | 3 | 43 |
| Haiku, prompt de base | 24 / 28 | 23 / 24 | 6 | 43 |
| Haiku + B | **28 / 28** | 27 / 28 | 6 | **35** |
| Haiku + A | **28 / 28** | 27 / 28 | 6 | **35** |
| Haiku + A + B | 28 / 28 | 27 / 28 | 6 | 35 |

Seule erreur de recoupement dans tous les cas : le Roi Gris (E-002, à l'auteur). Les « en trop » sont de vraies mentions absentes du gold (« le baron » en notes p1 et p3, « la Chute » en p7 : classe G) et trois désignations recoupées comme entités nouvelles (E-006).

**Défaut trouvé en cours de route** (déterministe, corrigé) : avec la consigne A, le modèle a écrit « **le** conseil des marchands » ; la forme exacte n'apparaît pas en p4 (« **au** conseil des marchands »), et la mention y était perdue. C1b cherche désormais aussi la forme sans article initial, comme C1a pour les noms connus.

## Lecture

1. **Sur b1, A et B se valent exactement** : chacune récupère les 4 « Odon » ; les titres uniques récupèrent « le baron » sans modèle. Le corpus ne permet pas de les départager.
2. **Ce qui les distingue n'est pas dans b1** :
   - A dépend du modèle (une règle de plus, une centaine de tokens, une passe seulement : stabilité inconnue) mais couvre en principe les formes que B ne devine pas : un nom de famille employé seul (« Ostrel »), un surnom, une fonction sans titre enregistré (« le capitaine »).
   - B est gratuite et stable, mais c'est une heuristique : elle suppose un type « personne » nommé `Character` (schéma de Valmont), des noms à majuscule, et un prénom employé seul. Elle se tromperait sur « Saint », « Maître », ou deux personnes au même prénom (dans ce cas elle s'abstient).
3. **La règle des titres uniques est sûre et générale** tant qu'elle s'abstient sur un titre partagé ; elle est gardée d'office.
4. **Le recoupement reste entièrement déterministe** : 27 bonnes sur 28.

## Suites

- Garder A et B comme options (`--prompt-short-forms`, `--short-forms`), sans défaut choisi, jusqu'à un corpus qui les départage : noms de famille employés seuls, surnoms, fonctions, homonymes de prénom.
- Traiter [E-006](E-006-designations-nouvelles.md) : trois désignations proposées comme entités nouvelles (fausses créations en revue).
- Passer ensuite à C5 (faits entre entités confirmées), dont E-003 attend la vérification.
