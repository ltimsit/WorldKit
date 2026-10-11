# Fiche de démarrage — Jalon I10 : les pistes d'auteur à l'écran

**Statut :** préparé le 11 octobre 2026, pas commencé. Branche prévue : `i10-pistes`.
**Contexte :** une piste d'auteur (R-SCN-09) est une édition **en attente**, avec un titre et les entités qu'elle concerne (`concerns`), qu'on **adopte** (elle s'applique, origine `adopted_draft`) ou qu'on **écarte**. C'est la place de ce qui n'est pas encore décidé : une hésitation (« genre 2000 habitants jsp encore », axe AX-E3), une idée d'intrigue (« et si le passeur trahissait la guilde ? »). Aujourd'hui elle ne se crée que par un fichier YAML (`worldkit draft load`) et ne se voit qu'entité par entité (« Pistes ouvertes », vue d'auteur). La séance X-018 a montré le besoin : une hésitation gardée en note devient une vérité du monde.

## 1. Objectif

Dans l'atelier, sur un fait ou une bribe dont il n'est pas sûr, l'auteur fait **« En faire une piste »** : un formulaire prérempli (titre tiré de la citation, entités, changement, source) crée la piste ; l'annotation ne part pas avec « Proposer ». Une page **`/pistes`** les montre toutes (titre, entités, source, état : en attente, à revérifier après un retcon), avec **adopter** et **écarter**, et la création d'une piste libre. Exemple : « Corbelle compte-t-elle environ 2000 habitants ? », concerne Corbelle, `population = environ 2000` (secret), source : notes en vrac p1.

## 2. Ce qui existe

- Noyau (`worldkit/core/workflows/scenarios.py`) : `load_author_drafts` (édition en attente, étiquette `draft`, écrite contre un point), `adopt` (origine `adopted_draft`), `open_drafts` (pistes ouvertes par entité, pour le wiki) ; `World.abandon` pour écarter ; une piste reportée par un rejeu (R-RED-03).
- Ligne de commande : `worldkit draft load | list | adopt | discard`.
- Service : `drafts.load` seulement.
- Wiki : « Pistes ouvertes » sur la page d'une entité (vue d'auteur, R-VUE-04).

## 3. Décisions à prendre (cadre d'interface, projets)

- **I-ATL-11** : le geste « En faire une piste » dans l'atelier (fait ou bribe), son formulaire, ce que devient l'annotation.
- **I-VUE-13** : l'écran `/pistes` (liste, adopter, écarter, créer).
- Opérations du service : `drafts.list`, `drafts.create`, `drafts.adopt`, `drafts.discard` (en plus de `drafts.load`).

## 4. Étapes (chacune testée et commitée)

1. **Service** : les quatre opérations ; une piste créée par l'atelier garde sa source (document, passage) en remarque ; tests.
2. **Atelier** : le geste sur un fait et sur une bribe, formulaire prérempli, état de l'annotation ; tests d'écran.
3. **Écran `/pistes`** : liste filtrée (ouvertes, adoptées, écartées), adopter, écarter, créer (changements écrits comme dans la Saisie, vérifiés en direct) ; entrée de navigation.
4. **(Selon la question 3) revue** : « En faire une piste » sur un changement proposé.
5. **Documents** : cadre d'interface, glossaire, carte des outils, guide exécuté, chantier (le geste « en faire une piste » sort des pistes), CLAUDE.md.

## 5. Questions à l'auteur (une à la fois)

1. **L'annotation mise en piste** : un état propre « en piste » (lien vers la piste, ne part pas avec « Proposer »), ou simplement « retirée » avec un lien ?
2. **Une piste sur une entité nouvelle** pas encore créée (Bertrand Ostrel avant la revue) : la refuser (« proposer d'abord l'entité »), ou la permettre en la faisant dépendre de la création en attente (comme un lot de faits, T-ING-07) ?
3. **Le geste dans la revue** (sur un changement proposé) : dans ce jalon, ou plus tard ?
4. **Une piste sans changement** (une question pure : « Corbelle a-t-elle 2000 habitants ? », rien à appliquer encore) : admise, ou une piste porte toujours au moins un changement ?
5. **Créer une piste libre sur la page** (hors atelier) : dans ce jalon, ou la page ne fait d'abord que lister, adopter, écarter ?

## 6. Hors du jalon

La doctrine des hésitations (consigne commune aux faits et aux notes, mesurée sur AX-E3) ; la mémoire des tournures ; les scénarios (déroulés, transposition) restent tels quels.

## 7. Définition de « fini »

Depuis l'atelier de `corbelle.db`, l'auteur met en piste la population de Corbelle, la retrouve sur `/pistes` et sur la page de Corbelle, l'adopte ou l'écarte ; tous les tests passent, dont le guide exécuté ; le cadre d'interface, l'aide et CLAUDE.md sont à jour.
