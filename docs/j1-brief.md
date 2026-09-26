# Fiche de démarrage — Jalon J1 : validateur de schéma et clés de fait

**Module :** M1 `schema` (cadre technique §3).
**Décisions et règles concernées :** T-SCH-01, T-FAI-01 ; R-SCH-01, R-SCH-02, R-SCH-04, R-SCH-06, R-SCH-07, R-SCH-10, R-NOY-01, R-FAI-05, R-MET-06.
**Test d'acceptation :** parcours W00 de `corpus/valmont-v1/valmont/walkthroughs/walkthroughs.yaml`.

---

## 1. Périmètre

J1 livre trois capacités, avec **un seul validateur** pour le schéma de monde et les systèmes de règles (R-SCH-02) :

1. **Valider un schéma** (monde ou système) contre un méta-schéma écrit en pydantic.
2. **Calculer la clé de fait** d'un changement (R-FAI-05, T-FAI-01).
3. **Vérifier un changement ou une fiche** contre un schéma : distinguer **hors schéma** (refusé à l'application, R-SCH-06) et **non-conformité** (tolérée et signalée, R-SCH-10).

Hors J1 : journal, stockage SQLite, projection, branches, ingestion (J2 et suivants). Les fonctions de J1 sont **pures** : elles prennent des objets en mémoire et rendent des résultats.

## 2. Méta-schéma (T-SCH-01)

Ce qu'un schéma YAML peut déclarer (voir `corpus/valmont-v1/schemas/fantasy-default.yaml` et `valmont/systems/`) :

| Élément | Contenu |
|---|---|
| En-tête | `schema` (identifiant), `version`, `kind` (`world` par défaut, ou `rule_system`), `copied_from` (optionnel) |
| Type | `attributes`, `extends` (un parent, déclaré), `labels` (préparé, R-SCH-08) |
| Attribut | `type` ∈ `text`, `integer`, `boolean`, `list[T]`, `ref[Type]` (et `list[ref[Type]]`) ; `required` ; `min` / `max` (entiers, `min ≤ max`) ; `labels` |
| Relation | `from`, `to` (un type ou une liste de types déclarés), `cardinality` ∈ `one_to_one`, `one_to_many`, `many_to_one`, `many_to_many` (défaut), `symmetric` (booléen), `labels` |

Rejets attendus (messages citant la règle) :
- type noyau déclaré dans un schéma de monde (`Document`, `Batch`, `Claim`, `Edit`, `Draft`, `Proposal`, `Scenario`, `ScenarioVersion`, `Playthrough`, `Sheet`) — R-NOY-01 ;
- cardinalité inconnue, parent ou type de relation non déclaré — R-SCH-01 ;
- type d'attribut hors grammaire, bornes incohérentes — T-SCH-01 ;
- à proposer (non tranché) : relation symétrique entre types différents ; identifiants non anglais (R-SCH-07 — difficile à vérifier automatiquement, proposer une heuristique simple ou y renoncer).

Les cinq fichiers de `corpus/valmont-v1/schemas/invalid/` doivent être rejetés ; les quatre schémas valides acceptés.

## 3. Clés de fait (R-FAI-05, T-FAI-01)

| Cas | Clé |
|---|---|
| Existence d'une entité (`create_entity`, `close_entity`, `delete_entity`) | `(entity)` |
| Attribut simple | `(entity, attribute)` |
| Attribut `list[...]` (`add_value`, `remove_value`) | `(entity, attribute, value)` — une clé par valeur |
| Relation `many_to_many` | `(from, relation, to)` |
| Relation `one_to_many` | `(relation, to)` — une cible a au plus une source |
| Relation `many_to_one` | `(from, relation)` |
| Relation `one_to_one` | **les deux** clés précédentes |
| Relation symétrique | extrémités rangées dans un ordre canonique avant calcul |
| Notoriété d'un fait | sous-clé `(clé, visibility)` |
| Qualification d'une affirmation | sous-clé `(claim, qualification)` |

Attention : `tools/check_corpus.py` simplifie `one_to_one` à une seule clé ; l'implémentation de J1 doit produire les deux.

Exemples tirés de Valmont (tests attendus) :
- « Odon gouverne Brume » et « le conseil des marchands gouverne Brume » → même clé `(rules, brume)` → collision.
- « Aldren frère de Mervin » et « Mervin frère d'Aldren » → même clé (symétrie).
- vœux « silence » et « pauvreté » des Veilleurs → deux clés distinctes.
- `spouse_of(mervin, isabeau)` → deux clés.

## 4. Vérification d'un changement ou d'une fiche

- **Hors schéma** (R-SCH-06) : le changement cite un type, un attribut ou une relation non déclaré par le schéma de l'état visé. Exemples du corpus : `vassal_of` (b1 p2), `constitution` pour le système A (b4 p3), `ward_of` (b6 p6).
- **Extension dans la même édition** (R-SCH-03, R-MET-05) : une édition qui contient `schema_set_relation(vassal_of)` puis `add_relation(odon, vassal_of, mervin)` est validée contre le schéma obtenu **après** ses propres changements de schéma (parcours W09).
- **Non-conformité** (R-SCH-10, R-MET-06) : un élément valide à son écriture devenu invalide après une modification du schéma ; signalé, jamais modifié. Exemple : fiche du Loup (PV 5) après passage du système A à « PV de 6 à 10 » (W08).
- **Fiches manquantes** (R-MET-06) : le Loup n'a pas de fiche dans le système B à l'état de base.
- Champs préparés acceptés et ignorés (invariant 10) : `diegetic_window`, `labels`, `authority`.

Pour la forme des fiches, suivre le format provisoire du corpus (`create_entity` de type `Sheet` avec `sheet: {of, system, category}`) ; la forme définitive est la lacune L2, à trancher avant J8.

## 5. Interface

- API Python : `load_schema(path) -> Schema`, `validate_schema(doc) -> list[Issue]`, `fact_keys(change, schema) -> list[FactKey]`, `check_change(change, schema) -> list[Issue]`, `check_conformity(state_or_sheets, schema) -> list[Issue]`. Noms indicatifs : propose mieux si besoin.
- Chaque `Issue` porte un code, un message en français et l'identifiant de la règle.
- Ligne de commande : `worldkit schema validate <fichier.yaml>…`, code de sortie non nul en cas d'erreur.

## 6. Tests

- W00 : schémas valides acceptés, invalides rejetés avec la bonne règle citée.
- Clés : tableau §3, exemples Valmont.
- Tous les changements de `corpus/valmont-v1/valmont/edits/base.yaml` sont dans le schéma (aucun hors schéma, sauf `counterpart_of`, lacune L1 : à signaler proprement).
- Gold : chaque changement annoté `out_of_schema` est détecté comme tel.
- Propriétés (*hypothesis*) : le calcul des clés est déterministe ; l'ordre des extrémités d'une relation symétrique ne change pas la clé ; deux valeurs différentes d'un attribut `list[...]` ont des clés différentes.

## 7. Définition de « fini »

- `pytest` vert ; W00 passe.
- Le cadre technique n'a pas été contredit ; tout écart a été signalé et discuté.
- Si une décision a été prise en cours de route (par ex. heuristique R-SCH-07), les documents sont mis à jour selon les règles de `CLAUDE.md`.
