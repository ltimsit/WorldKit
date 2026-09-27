# Fiche de démarrage — Jalon J8 : méta (systèmes et fiches)

**Modules :** M6 (déclaration, marqueurs), M7 (extraction, oracle et LLM), M9 (propositions, revue, décisions), M1 (conformité des fiches), M10–M11 (pages, export).
**Règles :** R-MET-01 à R-MET-06, R-SCH-02, R-SCH-06, R-SCH-10, R-DEC-01 à R-DEC-03, R-ING-01, R-PRI-04 ; T-ING-02, T-ING-11, T-ING-13, T-ING-17, T-FAI-01 ; cadre de la fondation §4.4, §5.2, §5.3.
**Test d'acceptation :** parcours W08 de `corpus/valmont-v1/valmont/walkthroughs/walkthroughs.yaml` (« Bestiaire : fiche, système, détection de nature »).
**Tests :** automatique, la conformité des fiches ; humain (cadre technique §7), le Loup de cendre sous deux systèmes.

---

## 1. Ce que dit le cadre

- **Nature** (§5.2) : `diegetic`, `meta_system`, `meta_sheet` ou `mixed` ; elle dit où va l'information : univers, système ou fiche.
- **Déclaration** (§5.3), par priorité décroissante : l'en-tête du document, les marqueurs `[meta] … [/meta]` sur un passage, puis la détection par indices. Un niveau supérieur l'emporte (R-DEC-01), et la détection **propose sans jamais décider** (R-DEC-02).
- **Le méta vit hors de l'univers** (R-MET-01) : dans les systèmes (règles, catégories) et dans les fiches (valeurs par entité et par système). Critère de classement (R-MET-03) : une information qui reste vraie si l'on change de système est diégétique.
- **Fiches** (R-MET-02, tranché avant J8) : une par système, avec un rattachement immuable `(of, system, category)` ; `has_sheet` et `conforms_to` sont calculées.
- **Double face** (R-MET-04, tranché) : `counterpart_of`, une contrepartie par système.
- **Même validateur** pour le monde et les systèmes (R-SCH-02). Un fait devenu non conforme après une modification de système est toléré et signalé (R-SCH-10, R-MET-06).
- Jusqu'ici (cadre technique §7), un passage méta est découpé et conservé, **sans proposition** (drapeau `meta`).

## 2. Ce qui existe déjà et se réutilise

- **Déclaration** (`worldkit/ingest/declaration.py`) : les natures, l'en-tête, le marqueur `[meta]`. Ce marqueur donne aujourd'hui toujours `meta_system`, alors que le gold de b4 p3 attend `meta_sheet`.
- **Lot** (`worldkit/ingest/batch.py`) : un passage méta y reçoit le drapeau `meta` et ses brouillons sont écartés. C'est le verrou à lever.
- **Oracle** (`worldkit/periphery/extraction.py`) : il lit déjà `nature` et `declared_by` dans le gold.
- **Noyau** : le code sait déjà créer une fiche, écrire ses valeurs vérifiées contre la catégorie du système, et modifier un système dans la même édition qu'un changement hors schéma (T-ING-13). Il signale aussi les fiches manquantes et non conformes (`check_conformity`), et gère les supports par clé, clés de schéma comprises (T-FAI-01).
- **Vues** : fiches sur les pages, section `sheets` de l'export.
- **Extracteur LLM et mesure T2** (`worldkit/periphery/llm_extractor.py`, `evaluation.py`) : les passages méta sont exclus de la mesure (« méta : J8 ») et le prompt ne décrit que le schéma de monde.

## 3. Points à trancher avec l'auteur (une question à la fois)

1. **Détection de nature (R-DEC-02).** Le paragraphe b4 p6 (« Système B : niveau 7, menace 8. ») n'a pas de marqueur, mais c'est une fiche. Comment la nature proposée devient-elle décidée ? Une « question de nature » dans la revue, sans proposition tant qu'elle n'est pas acceptée ? Ou des propositions créées tout de suite, marquées « nature détectée » ?
2. **Destination d'un segment `[meta]`.** Le marqueur ne dit pas s'il s'agit d'un système ou d'une fiche. Faut-il deux marqueurs (`[meta:sheet]`, `[meta:system]`), ou déduire la destination des changements produits ?
3. **Garde de classement (R-MET-03).** Que devient un changement diégétique extrait d'un segment méta (« PV 5, et il hante Cendrelande »), ou un changement de fiche extrait d'un passage déclaré diégétique ?
4. **Extraction LLM du méta.** Il faut décider de ce que le prompt décrit (systèmes, catégories, fiches existantes) et de la façon de désigner le sujet d'une fiche quand il vient du contexte du document (p6), puis étendre la mesure T2 aux passages méta. Une mesure complète consomme le quota : demander avant de la lancer.

## 4. Attendus de W08

- Avant J8, les passages 3, 4 et 6 sont conservés sans proposition (déjà vrai).
- p3 : supports pour les valeurs de la fiche A (PV 5, Force 12…) ; « Constitution 13 » est hors schéma dans le système A (R-SCH-06), applicable seulement si le système est étendu dans la même édition.
- p4 : support pour la règle `Creature.hp` 1–10 du système A (clé de schéma, T-FAI-01), sans édition.
- p6 : la nature méta est proposée, jamais décidée. Une fois acceptée, la fiche B du Loup est créée (niveau 7, menace 8) et le signalement de fiche manquante disparaît.
- Après e102 (`hp` 6–10) : la fiche A du Loup (PV 5) est signalée non conforme, sans être modifiée.
- Pièges : p5 (« Certains disent que la Flamme d'azur… ») reste une attribution, sans fait ; aucune faiblesse « Flamme d'azur » n'est ajoutée au Loup.

## 5. Définition de « fini »

- `pytest` vert : T1 sur la déclaration et les décisions de nature (déterministes, jamais redemandées, R-PRI-04) ; W08 passe avec l'oracle ; la conformité des fiches est testée.
- T2 étendu aux passages méta (mesure lancée seulement avec l'accord de l'auteur).
- Documents mis à jour selon CLAUDE.md (cadre technique, analyse 00.xx et question, CLAUDE.md), choix non validés listés dans la réponse.
