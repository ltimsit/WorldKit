# Corpus synthétique Valmont — premier jet (v1)

**Objet :** monde de démonstration écrit pour tester et analyser le plus grand nombre possible de concepts de *cadre-fondation.md* (v1.15) et de *cadre-technique.md* (v2.5). C'est l'artefact du jalon J0.
**Nature :** corpus **synthétique**, construit exprès. Il sera complété par un second jet, écrit à la main par l'auteur, plus proche de vraies notes. Les métriques d'extraction (T2) mesurées sur ce premier jet sont donc optimistes par construction.
**Date :** 26 septembre 2026.

---

## 1. Contenu

```
valmont-v1/
├── schemas/
│   ├── fantasy-default.yaml        schéma de monde par défaut (R-SCH-05)
│   └── invalid/                    5 schémas invalides pour tester le validateur (J1)
├── valmont/
│   ├── world.yaml                  déclaration du monde
│   ├── schema.yaml                 schéma de Valmont (copie adaptée du défaut)
│   ├── systems/                    systèmes de règles A et B
│   ├── edits/base.yaml             vérité structurée : état de base (e001–e006)
│   ├── docs/                       9 documents en 8 lots (b1–b8) + batches.yaml
│   ├── gold/                       annotations attendues, passage par passage
│   ├── scenarios/                  2 scénarios versionnés, pistes d'auteur, déroulés
│   ├── walkthroughs/               18 parcours de test (W00–W17), actions et résultats attendus
│   └── questions.yaml              20 questions de compétence, réponses par vue
└── tools/check_corpus.py           contrôle de cohérence du corpus lui-même
```

`python3 tools/check_corpus.py` vérifie : chargement YAML ; types, attributs et relations déclarés ; entités existantes ; attributs multiples modifiés par `add_value` seulement ; absence de collision de clé dans l'état de base ; cohérence du gold avec l'état (supports, hors schéma, anomalies) ; existence des passages annotés. Il ne remplace pas le noyau : il garantit seulement que le corpus ne se contredit pas.

## 2. Le monde en bref

Valmont est un royaume. Le roi **Aldren II** est mort pendant **la Chute** (an 1492) : officiellement au combat, selon la **Chronique de la Chute** commandée par son frère **Mervin**, devenu roi ; en réalité empoisonné par Mervin (secret). Le prince **Corvin**, fils d'Aldren, a disparu : il vit caché parmi les **Veilleurs**, ordre monastique de **Cendrelande**, sous le nom de **Frère Cendre** (révélation secrète). **Odon de Brume**, baron du port de **Brume**, est membre du **Cercle des Cendres**, culte secret qui vénère le **Loup de cendre**. Le **conseil des marchands**, absent de l'état de base, apparaît par l'ingestion.

Deux scénarios : **L'éveil du Loup** (le Loup dévore le Cœur de braise) et **Le siège de Brume** (qui suppose le premier ; le conseil prend Brume, le baron survit ou meurt).

## 3. Formats provisoires (non validés)

Ces formats sont des choix de fixture, faits pour écrire le corpus ; ils ne préjugent pas des formats du produit.

| Élément | Convention |
|---|---|
| Édition | `id`, `branch`, `origin`, `tags`, `changes` ; un changement = une opération du catalogue §6.1 avec ses champs (`entity`, `attribute`, `value`, `from`, `relation`, `to`, `visibility`, `kind`, `scope`). |
| Notoriété | Absente = `unqualified`. |
| Système de règles | Même langage que le schéma de monde, avec `kind: rule_system` ; éléments du système adressés `system-a:bite`. |
| Fiche | `create_entity` de type `Sheet` avec `sheet: { of, system, category }` ; identifiant `entité@système`. Rattachement immuable, une fiche par système (lacune L2 tranchée). |
| Fiches exigées | Dans `world.yaml`, par système : `sheets: { TypeDuMonde: Catégorie }`, sous-types compris (R-MET-06). |
| Changements de schéma | `schema_set_relation` : `relation` + `definition` complète ; `schema_set_type` : `type` + `definition` complète, ou `attribute` + `definition` d'attribut, ou `attribute` + `constraint` (`min`, `max`, `required`). |
| Affirmations (gold) | `claims` par passage, ou `segments` quand un marqueur `[in_world: …]` découpe le passage ; `suggested` est la conclusion attendue du noyau, que l'extracteur oracle ne transmet pas. |
| Entité en attente (gold) | `pending:étiquette` : entité dont la création est proposée par un lot encore en attente (T-ING-07). |
| Notoriété désignée | `set_visibility` : `target` textuel (« `a relation b` », « `entité.attribut` », « `entité` ») ou structuré (`entity`, `attribute`, `value`, `from`, `relation`, `to`). |
| Passages | Paragraphes du corps du document, titres exclus, numérotés à partir de 1. |
| Gold | Par passage : `mentions` (résolution attendue ; `new:` = entité nouvelle, `pending:` = entité seulement proposée), `changes` avec `outcome`, `must_not` (pièges), `optional`. |
| Outcomes | `support`, `enrichment`, `anomaly`, `intention`, `batch_conflict`, `competing`, `out_of_schema`, `hint_visibility`, `attribution` ; pour les affirmations : `claimed` et `suggested` (`true` / `false` / `undetermined`). |
| Points nommés | `@base`, `@after-b1`, `@after-b4`, `@after-siege`, définis par les parcours (`do: set_point`) ; distincts des points de sauvegarde (`checkpoint`, T-STO-01). |

## 4. Couverture du cadre

| Famille | Règles | Où |
|---|---|---|
| Monde | R-MON-01 à 04 | world.yaml ; W13 (variante hérite du schéma) ; W15 (nouvelle branche de référence) |
| Schémas | R-SCH-01, 02, 03, 04, 05, 06, 07, 08, 10 | schemas/ ; systems/ ; W00 (invalides) ; W08 (non-conformité après e102) ; W09 (extension dans la même édition) ; gold b1 p2, b4 p3, b6 p6 (hors schéma) |
| Types noyau | R-NOY-01, 02 | schemas/invalid/core-type.yaml ; `concerns`, `same_as`, fiches |
| Fait | R-FAI-01, 02, 03, 04, 05, 06 | base.yaml (clés, `diegetic_window` préparé) ; W10 (fait orphelin) ; W04, W07 (valeurs multiples) |
| Méta | R-MET-01, 02, 04, 05, 06 | systems/ ; base e006 ; b4 ; W08 ; pt-1 (lore + fiche dans une édition) |
| Documents | R-DOC-01, 02, 04, 05, 06, 07, 08 | batches.yaml ; b2 (in-world) ; W06 (promotion) ; W10 (ré-ingestion) ; W14 (obsolète) ; `authority` préparé (b8) |
| Identité | R-IDT-01 à 05 | base e004 (révélation secrète) ; W16 (doublon) ; W01 (page consolidée) |
| Notoriété | R-NOT-01, 03, 04, 05, 06, 07 | base (secret, public, non qualifié, propagation) ; W05, W07 (notoriété par valeur) ; W06 (héritage) |
| Alimentation | R-ALI-01, R-ING-01, 02, R-DEC-01, 02, 03 | toutes les ingestions ; b1 p6, b4 p5 (attribution) ; b3 p4 (marqueur) ; b4 p6 (détection) |
| Priorité | R-PRI-01, 02, 03, 04, 05, 07 | W02 (lot symétrique) ; W03 (concurrence) ; W05 (décisions) ; W10 (non-redemande) |
| Édition | R-EDI-01 à 09 | tous les parcours ; W05, W09 (confirmation partielle ou adaptée) ; W16 (delete_entity) |
| Cycle | R-CYC-01 à 04 | W11 (abandon) ; W12 (alternatives) ; W04 (à revérifier) |
| Historique | R-HIS-01 à 06 | W13 (branche, transposition) ; W15 (rejeu) ; W17 (ordre des scénarios) |
| Redéfinitions | R-RED-01 à 04 | W13 (ponctuelle) ; W15 (rétroactive) |
| Scénarios | R-SCN-01 à 09 | scenarios/ ; W12 ; W13 ; W17 |
| Contradictions | R-CON-01 à 04 | les trois familles : `history` (W02–W05, W13, W15), `conformity` (W08, W09), `identity` (W01, W16) |
| Vues | R-VUE-01, 02, 03 ; R-LLM-01 | W01 ; W13 (redéfini plus tard) ; questions.yaml |

**Non couvert dans ce jet :** R-RED-05 (redéfinition rétroactive d'un schéma ou d'un système) ; R-SCH-09 et R-VUE-04 (interface, sans objet avant J4) ; R-PRI-06 et le *rollback* ciblé (point ouvert §10.1).

## 5. Lacunes du cadre révélées par le corpus

Écrire le corpus a obligé à trancher des cas que le cadre ne règle pas. Chaque lacune est signalée à l'endroit où elle apparaît.

| # | Lacune | Où | Règles |
|---|---|---|---|
| L1 | ~~Le lien entre les deux nœuds d'un élément à double face n'a pas de nom.~~ **Tranchée** (cadre v1.20) : relation noyau `counterpart_of`, du monde vers un système, au plus une contrepartie par système ; une capacité de système peut servir plusieurs éléments du monde. | base e006 | R-MET-04 |
| L2 | ~~La forme d'une fiche dans les changements n'est pas fixée.~~ **Tranchée** (cadre v1.20) : un seul `create_entity` de type `Sheet` porte le rattachement immuable `(of, system, category)` ; une fiche par système ; `has_sheet` et `conforms_to` sont calculées, jamais écrites ; reclasser = clore puis recréer. | base e006, b4 | R-MET-01, R-MET-02, §4.4 |
| L3 | ~~Un lot peut citer une entité seulement proposée par un autre lot en attente.~~ **Tranchée** (cadre technique v2.3) : la résolution voit les créations en attente et en reprend l'identifiant ; dépendance envers la création. | b5 p1, W03 | T-ING-07, T-ING-05 |
| L4 | ~~La notoriété d'une qualification d'affirmation n'est pas fixée.~~ **Tranchée** (cadre v1.14) : la qualification porte sa propre notoriété, non qualifiée par défaut. | W06 | R-DOC-07, R-NOT-02 |
| L5 | ~~Un fait déclaré public qui mentionne une entité non qualifiée ou secrète.~~ **Tranchée** (cadre v1.13) : notoriété plafonnée par l'entité, levée explicite (`propagation_lifted`), faits masqués signalés. | Q01, W12 | R-NOT-04, R-NOT-07 |
| L6 | ~~Les éléments de schéma n'ont pas de clé de fait.~~ **Tranchée** (cadre technique v2.14) : clé `(portée, type|relation, nom[, attribut])`, écrite par les seules éditions de schéma ; une édition ordinaire ne la lit pas, sa dépendance aux définitions est vérifiée par la revalidation (M1, T-ING-14, R-SCH-10). | b4 p4, W09 | R-FAI-05, R-SCH-03 |
| L7 | ~~Aucune étiquette d'origine ne convient à une décision documentaire.~~ **Tranchée** (cadre v1.15) : origine `curation`, réservée aux changements de statut de document. | W14 | R-EDI-05, R-EDI-09 |

## 6. Ce que ce jet ne teste pas bien

- **Le style humain** : les documents sont courts, explicites, un fait par phrase. Le second jet devra apporter des notes désordonnées, des redites, des allusions, des listes, des fautes.
- **Le volume** : 9 documents, une quarantaine de passages. Suffisant pour les mécanismes, pas pour mesurer la charge de curation (T3).
- **Les ambiguïtés véritables** : ici, chaque passage a une seule bonne réponse, écrite par avance.
