# Fiche de démarrage — Jalon J9 : les notes (descriptions)

**Statut :** préparé le 11 octobre 2026, pas commencé. Branche prévue : `j9-notes`.
**Contexte :** le niveau 1 de « ingérer plus que les faits » (chantier §10.6) montre les passages qui nomment une entité (R-VUE-05) ; tout ce qui n'est pas un fait à clé — un portrait, un jugement, une habitude — reste « non capté ». Le brainstorm du 11 octobre a fixé la conception des **notes** (chantier, choix 43 à 48). Ce jalon les construit, du noyau à l'écran.

## 1. Objectif

Sur ses notes de Corbelle, l'auteur lance, après les faits, la couche « descriptions » de l'atelier. Il voit sous chaque passage les **bribes** proposées : « Ysolde — apparence : « une vieille rousse sèche » (âge : vieille · cheveux : roux) ». Il les garde, corrige (facette, sujets, forme courte) ou retire. « Proposer » les envoie comme **notes** ; la revue les accepte en lot par passage. La page d'Ysolde montre alors, par facette, ce que les textes disent d'elle, chaque bribe avec sa source et sa notoriété ; la vue joueur n'en montre que ce qui est public, plafonné par les entités nommées.

## 2. Ce qui est décidé (chantier, choix 43 à 48)

| | Décision |
|---|---|
| Usages | maintenant : relire et retrouver (suivi du graphe) ; à anticiper : wiki encyclopédique, textes produits pour l'auteur selon la notoriété, extraction par un agent, incohérences ; hors cadre : LLM joueur |
| Forme | citation exacte, rangée par facette, et forme courte facultative « aspect : valeur » |
| Statut | atelier puis journal : nouvelle sorte d'élément du monde, sans collision, acceptable en lot |
| Facettes | déclarées par le schéma, par type ; « autre » toujours présente |
| Notoriété | comme un fait (défaut : celle du document), plafonnée par sujets et mentions (R-NOT-04) |
| Frontière | les notes prennent ce que les faits laissent |
| Sujets | un ou plusieurs, sans ordre, et des mentions |

## 3. Évolutions des cadres proposées (à valider au démarrage)

**Cadre de la fondation.** Périmètre (§1.4) : les notes descriptives entrent dans la fondation. Nouvelle famille de règles `R-NTE` (projet) :

| ID | Règle proposée |
|---|---|
| R-NTE-01 | Une **note** est un élément du monde : une citation (texte), une facette, **un ou plusieurs sujets sans ordre**, des mentions, une forme courte facultative (« aspect : valeur »), et sa source (document et passage) quand elle vient d'un document. |
| R-NTE-02 | Une note **n'a pas de clé de fait** : elle n'entre jamais en collision. Deux notes peuvent se contredire sans contradiction au sens de §7, comme fait et affirmation (R-DOC-08). |
| R-NTE-03 | Notoriété d'une note : comme un fait (R-NOT-01 ; défaut : celle du document), **plafonnée** par ses sujets et ses mentions (R-NOT-04). R-NOT-02 s'étend aux notes. |
| R-NTE-04 | Les **facettes** sont déclarées par type dans le schéma (avec libellés) ; `other` existe toujours. Une note dont les sujets n'ont pas de facette commune va dans `other`. |
| R-NTE-05 | À l'ingestion, une note ne décrit pas ce qu'un fait confirmé du même passage dit déjà (notes et faits complémentaires). |
| R-NTE-06 | Une note issue d'un document reste attachée à sa source (R-DOC-04) ; si son passage disparaît à la ré-ingestion, elle est **signalée orpheline**, jamais retirée d'office (comme R-FAI-06). |

Vues : R-VUE-02 (une page montre aussi ses notes, par facette ; « mentionné dans » pour une mention). Glossaire FR ↔ EN : note `note`, facette `facet`, sujet `subject`, mention `mention`, forme courte `short_form`.

**Méta-schéma** (R-SCH) : `TypeDef.facets` (identifiant anglais, libellés), hérité par les sous-types ; le validateur les vérifie.

**Cadre technique.**
- Changements `add_note` et `remove_note` ; `set_visibility` vise aussi une note. Clés (T-FAI-01) : `("note", id)` et sa sous-clé de notoriété ; une note n'écrit aucune clé de fait.
- T-ING-22 (projet) : la couche « descriptions » — entrée : entités confirmées et faits gardés (leurs preuves sont exclues) ; sortie : annotations `note` ; énonciation (rumeur, note de travail : pas de note, comme les faits, X-010) ; un appel par fenêtre (chantier §6.5).

**Cadre d'interface.** I-ATL-10 (projet) : la couche dans l'atelier, les gestes sur une bribe, « Proposer » ; la revue accepte une note en lot par passage ; I-VUE-07 : les notes sur la page ; I-VUE-12 : les facettes sur l'écran Schéma ; Saisie : `add_note`.

## 4. Étapes (chacune testée et commitée)

1. **Méta-schéma** : facettes par type, héritage, validateur ; libellés ; écran Schéma.
2. **Noyau** : `add_note`, `remove_note`, notoriété, projection (`state.notes`), forme canonique. Tests T1 : aucune collision ; plafonnement par sujets et mentions ; sujets sans ordre (même note quel que soit l'ordre) ; branches, transposition et rejeu (une note est une édition comme une autre) ; déterminisme.
3. **Vues** : section par facette (vue d'auteur : tout ; vue joueur : notoriété effective publique) ; « mentionné dans » ; Markdown et export JSON (les notes, selon le filtre).
4. **Ingestion** : propositions de notes (étapes E5 à E9), revue en lot, mémoire des décisions par empreinte (R-PRI-04), notes orphelines à la ré-ingestion (R-NTE-06).
5. **Périphérie** : `NoteFinder` (prompt, schéma de sortie), facettes du type, preuves des faits exclues, énonciation ; rejeu des traces ; format de gold pour les notes ; mesure T2.
6. **Atelier** : couche « descriptions » (`atelier.run`, `layer: notes`, estimation puis confirmation, I-LLM-01), annotations `note`, gestes (garder, retirer, corriger la facette, les sujets, les mentions, la forme courte ; ajouter par sélection), « Proposer ».
7. **Écrans** : atelier, revue, wiki, Schéma, Saisie.
8. **Documents** : cadres (fondation, technique, interface), analyse 00.65 et question 92, aide (glossaire, carte des outils, guide exécuté), chantier (les choix actés en sortent), CLAUDE.md.

## 5. Questions à l'auteur (une à la fois, au démarrage)

1. **Facettes par défaut** : la plateforme fournit-elle des facettes à un type qui n'en déclare pas (apparence, caractère, histoire, habitudes pour un personnage ; aspect, ambiance, histoire pour un lieu), ou chaque schéma les déclare-t-il (`mondes/corbelle`) ? Les schémas des corpus, instruments de mesure, ne devraient pas changer.
2. **Documents en jeu** : ce qu'une chronique dit d'Aldren (« un roi pieux et juste ») est-il une note attribuée à la chronique (voix, comme une affirmation, R-DOC-06), ou n'en produit-il pas ?
3. **Note écrite par l'auteur** sans document (Saisie, ou « ajouter » dans l'atelier hors passage) : admise ?
4. **Retirer une note** : `remove_note` (elle quitte l'état, l'historique la garde) en plus de la corriger ?
5. **Forme courte** : aspects libres (« cheveux », « chevelure » distincts) pour commencer, ou un vocabulaire d'aspects par facette dès maintenant (prépare les incohérences) ?
6. **Mesure** : gold des notes sur Corbelle (brouillon) et b1 ; nombre d'appels estimé avant de lancer (environ un par document et par passe sous Haiku 4.5, quelques centimes) — à confirmer le moment venu.

## 6. Hors du jalon

Détection des incohérences (approche à choisir) ; description consolidée (niveau 4) et textes produits pour l'auteur ; mémoire des tournures ; un attribut proposé quand une forme courte revient (l'incubateur du schéma).

## 7. Définition de « fini »

Sur `corbelle.db`, l'auteur obtient des notes depuis l'atelier, les accepte en revue et les lit par facette sur la page d'Ysolde (auteur et joueur) ; tous les tests passent, dont les T1 des notes et le guide exécuté ; la mesure T2 des notes est faite ou explicitement reportée ; les cadres, l'analyse, l'aide et CLAUDE.md sont à jour.
