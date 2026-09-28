# Guide pas à pas

**Objet :** apprendre à se servir de worldkit par l'exemple : construire le monde de démonstration Valmont, lire un résultat, écrire un changement, essayer dans un bac à sable, ingérer un lot étape par étape, faire un retcon, tester un mécanisme seul, mesurer un extracteur, vérifier après un changement de code. Chaque section donne les gestes dans l'interface, la commande équivalente et ce que vous devez voir.
**Version :** 1.0 — 27 septembre 2026.
**Lecture :** les sections s'enchaînent sur un même monde ; suivez-les dans l'ordre la première fois. Les commandes se tapent sous PowerShell, **depuis la racine du projet**, environnement activé (`.venv\Scripts\activate`). Tout identifiant souligné dans l'interface (règle, étape, opération, statut) mène à sa définition ; en ligne de commande : `worldkit explain <code>`. La carte des écrans est dans *outils.md*, les définitions dans *glossaire.md*.
**Ce guide est testé :** `tests/test_guide.py` exécute chaque bloc de commandes et vérifie chaque bloc « sortie » et chaque écran annoncé. S'il ment, la suite de tests échoue.

---

## 1. Construire le monde de démonstration

Valmont est le monde du corpus de test (`corpus/valmont-v1/`) : un royaume, la ville de Brume, le baron Odon, le roi Aldren mort pendant la Chute. On crée la base avec son schéma, on applique les six éditions de départ, puis on nomme ce point `base` pour pouvoir y revenir.

```powershell
worldkit --db valmont.db world init corpus/valmont-v1/valmont/world.yaml
worldkit --db valmont.db edit apply corpus/valmont-v1/valmont/edits/base.yaml
worldkit --db valmont.db point set base
```

```text sortie
monde « valmont » créé
e001 : applied (rang 2)
e006 : applied (rang 7)
@base = rang 7
```

Chaque édition est inscrite au journal à un **rang** (`seq`) ; `e000`, au rang 1, a chargé le schéma. Le fichier `valmont.db` est tout le monde : le supprimer, c'est repartir de zéro.

## 2. Ouvrir l'interface

```powershell sans-test
pip install -e .[ui]
worldkit --db valmont.db serve
```

Le navigateur s'ouvre sur `http://127.0.0.1:8765/`, le **Tableau de bord**. En haut : le menu des écrans, puis la **barre de contexte** — cible (monde de travail ou bac à sable), branche, point, filtre auteur ou joueur. Le contexte vit dans l'adresse : un lien copié rouvre la même lecture. Sous le menu, chaque écran dit à quoi il sert ; le « ? » ouvre sa fiche. `Ctrl+C` dans le terminal arrête le serveur ; relancez-le après une mise à jour du code (l'en-tête affiche l'heure de démarrage).

<!-- écran / : "Tableau de bord" ; "Faits par notoriété" ; "Voir l'état d'un monde d'un coup d'œil" -->

## 3. Lire un résultat

Tout ce que fait l'outil passe par une **opération** du service, qui rend un **résultat** de même forme partout. La commande `worldkit call` appelle n'importe quelle opération :

```powershell
worldkit --db valmont.db call world.summary
```

```text sortie
world.summary [read] → world : ok
indicateurs :
entities : 20
facts : 59
facts_by_visibility : {'secret': 5, 'public': 44, 'unqualified': 10}
signals : {'missing_sheet': 1}
sortie :
world: valmont
reference_branch: reference
```

Comment le lire, ligne par ligne :

| Élément | Exemple | Ce qu'il dit |
|---|---|---|
| opération | `world.summary` | ce qui a été appelé ; `worldkit explain world.summary` la décrit |
| sorte | `[read]` | `read` lit sans écrire ; `compute` calcule (enregistré) ; `write` écrit (enregistré, rejouable) ; `admin` gère bacs et exécutions |
| cible | `→ world` | le monde de travail, ou `sandbox:<n>` pour un bac |
| statut | `ok` | `ok`, `refused` (rien n'a été fait : voir les signalements), `pending` (attend une confirmation), `error` (échec technique) |
| durée, exécution | `(12 ms, exécution #3)` | les opérations `compute`, `write` et `admin` sont enregistrées : `worldkit runs show 3` les relit |
| signalements | `- error [R-FAI-05] key_collision …` | sévérité, règle qui fonde le signalement, code, emplacement, message (section 5) |
| indicateurs | `facts : 59` | les nombres clés, comparables d'une exécution à l'autre |
| sortie | `world: valmont` | la donnée elle-même |

Ici, 59 faits dont 5 secrets, et un **signalement** : une fiche manque (`missing_sheet`). À l'écran, le Tableau de bord montre la même chose ; tout en bas, « Appels au service pour cet écran » liste les opérations appelées et leur **JSON brut** — le résultat complet, identique à `worldkit call world.summary --json`.

<!-- écran / : "missing_sheet" ; "Appels au service pour cet écran" ; "JSON brut" -->

## 4. Lire le monde : vue auteur, vue joueur

Aldren a été empoisonné par son frère Mervin — c'est **secret**. Comparez ce que voit l'auteur et ce que voit un joueur :

```powershell
worldkit --db valmont.db wiki page aldren-ii
```

```text sortie
- death_cause : poison _[secret · e003]_
- Mervin (`mervin`) killed → (cette entité) _[secret · e003]_
```

```powershell
worldkit --db valmont.db wiki page aldren-ii --filter player
```

```text sortie
- title : roi
- sibling_of → Mervin (`mervin`)
```

La vue joueur ne montre ni la cause de la mort ni le meurtre ; chaque fait de la vue auteur donne sa **notoriété** et l'édition qui l'a établi (`e003`, sa **provenance**). À l'écran : **Wiki**, page `aldren-ii`, et le filtre « joueur » dans la barre de contexte ; le lien « comparer » met les deux vues côte à côte.

<!-- écran /wiki/aldren-ii : "death_cause" ; "poison" -->
<!-- écran /wiki/aldren-ii?filter=player : "Aldren II" ; "roi" -->

Le **Graphe** montre la même chose en structure : le voisinage d'Aldren, vu par un joueur, compte 4 nœuds et 4 arêtes.

```powershell
worldkit --db valmont.db call graph.view --param entity=aldren-ii --param filter=player
```

```text sortie
graph.view [read] → world : ok
nodes : 4
edges : 4
```

À l'écran : **Graphe**, entité `aldren-ii`, filtre joueur. La bordure des nœuds code la notoriété ; une arête pointillée est secrète (en vue auteur seulement) ; un clic sur un nœud ouvre son détail ; la légende sous le graphe renvoie à chaque marque.

## 5. Écrire un changement et lire une contradiction

Une **édition** est une liste de **changements** ; on l'écrit en YAML. Supposons que Mervin s'empare de Brume :

```yaml fichier=mervin.yaml
edit:
  id: g1
  origin: enrichment
  changes:
    - {op: add_relation, from: mervin, relation: rules, to: brume}
```

On la **vérifie** sans rien écrire :

```powershell
worldkit --db valmont.db call edit.check mervin.yaml
```

```text sortie
edit.check [compute] → world : refused
- error [R-FAI-05] key_collision changes[0] : la clé (rules, brume) est occupée par rules(odon, brume) ; retirer ce fait dans la même édition pour le remplacer
```

Lire le signalement : `error` (bloquant) · `[R-FAI-05]` la règle — `worldkit explain R-FAI-05` en donne le texte · `key_collision` le code · `changes[0]` le changement en cause · puis le message. La relation `rules` est `one_to_many` : un lieu n'a qu'un gouvernant, et Brume a déjà Odon. C'est ainsi que le noyau détecte les contradictions : deux faits sur la même **clé de fait**, jamais par un modèle de langage. Pour remplacer, on retire l'ancien fait dans la même édition :

```yaml fichier=mervin-corrige.yaml
edit:
  id: g1
  origin: enrichment
  changes:
    - {op: remove_relation, from: odon, relation: rules, to: brume}
    - {op: add_relation, from: mervin, relation: rules, to: brume, visibility: secret}
```

```powershell
worldkit --db valmont.db call edit.check mervin-corrige.yaml
```

```text sortie
edit.check [compute] → world : ok
applicable: true
```

La sortie détaille les clés lues et écrites et l'état avant et après (`diff`). À l'écran : **Saisie** — l'éditeur attend l'édition elle-même, c'est-à-dire ce qui est sous `edit:` (les lignes `id`, `origin`, `changes`, ramenées à gauche). La vérification se refait à chaque pause de frappe, et chaque signalement est rattaché à la ligne de son changement. On n'applique pas cette édition : la suite du guide garde Odon à Brume.

## 6. Essayer dans un bac à sable, puis rendre réel

Un **bac à sable** est une copie du monde où l'on essaie sans risque. Le baron Odon devient régent :

```yaml fichier=regent.yaml
edit:
  id: g2
  origin: enrichment
  changes:
    - {op: set_attribute, entity: odon, attribute: title, value: régent}
```

Modifier un attribut n'est pas une contradiction : c'est un changement voulu (l'ancienne valeur est remplacée, et reste dans l'histoire). On crée un bac, on y applique l'édition, on compare :

```powershell
worldkit --db valmont.db sandbox create --note "Odon régent"
worldkit --db valmont.db call edit.apply regent.yaml --sandbox 1
worldkit --db valmont.db call wiki.page --param entity=odon --sandbox 1
```

```text sortie
sandbox.create [admin] → world : ok
note: Odon régent
edit.apply [write] → sandbox:1 : ok
status: applied
- title : régent
```

```powershell
worldkit --db valmont.db call wiki.page --param entity=odon
```

```text sortie
- title : baron
```

Le monde de travail n'a pas bougé. **Rendre réel** rejoue les écritures du bac sur le monde de travail : d'abord une répétition à blanc sur une copie fraîche, dont chaque action reçoit un verdict (`same`, `gap`, `divergence`) ; puis, avec `--yes`, l'application en tout ou rien.

```powershell
worldkit --db valmont.db sandbox promote 1
worldkit --db valmont.db sandbox promote 1 --yes
worldkit --db valmont.db call wiki.page --param entity=odon
```

```text sortie
rendre réel le bac 1 (chaîne [1]) : pending
edit.apply (sandbox:1) : identique
répétition réussie : relancer avec --yes pour appliquer au monde de travail
rendre réel le bac 1 (chaîne [1]) : ok
- title : régent
```

À l'écran : choisissez « bac 1 » dans la barre de contexte pour lire le bac ; **Saisie** applique par défaut dans un bac ; le Tableau de bord liste les bacs avec le lien « rendre réel », qui montre la répétition à blanc avant d'appliquer.

## 7. Ingérer un lot étape par étape

L'**ingestion** transforme des documents en **propositions** d'éditions, que l'auteur revoit. Elle est découpée en étapes : E1 Déclaration, E2 Passages, E3 Nature, E4 Extraction, E5 Traduction, E6 Classement, E7 Résolution, E8 Qualification, E9 Propositions, puis E9+ Enregistrer, E10 Revue, E11 Application, E12 Vues. Le lot `b1` contient les notes sur le baron et les lieux de Valmont. L'extracteur **oracle** lit les réponses attendues (`gold/`) au lieu d'appeler un modèle : gratuit, exact, idéal pour apprendre.

```powershell
worldkit --db valmont.db run stages --batch b1 --batches corpus/valmont-v1/valmont/docs/batches.yaml --oracle corpus/valmont-v1/valmont/gold
```

```text sortie
pipeline.run E1 → E9 : ok, exécution #8
E2 Passages
{"passages": 12}
E4 Extraction
"llm_calls": 0
E9 Propositions
"written": false
enregistrer : worldkit run save 8 [--sandbox N] [--to E12]
```

Rien n'est écrit (`"written": false`). Chaque étape a gardé son **artefact** ; celui de E4 contient les brouillons extraits de chaque passage :

```powershell
worldkit --db valmont.db call runs.artifact --param id=8 --param stage=E4
```

```text sortie
runs.artifact [read] → world : ok
```

À l'écran : **Pipeline**, lot `b1`, extracteur oracle, « Lancer » ; la page de l'exécution suit la progression, montre chaque étape avec ses indicateurs et un lien « voir » vers son artefact, qu'on peut modifier puis réinjecter à l'étape suivante (« reprendre »). Remplacez `8` par le numéro affiché chez vous : chaque opération enregistrée prend le numéro suivant.

On **enregistre** ensuite le lot — dans un bac, pour essayer :

```powershell
worldkit --db valmont.db sandbox create --note "revue de b1"
worldkit --db valmont.db run save 8 --sandbox 4
worldkit --db valmont.db call review.list --sandbox 4
```

```text sortie
sandbox.create [admin] → world : ok
id: 4
pipeline.save [write] → sandbox:4 : ok
proposals : 12
review.list [read] → sandbox:4 : ok
- id: b1.notes-baron.p1.1
- text: odon.title = 'baron'
- anomaly
value: régent
```

Le bac porte le numéro 4 : la répétition à blanc de la section 6 a créé puis jeté les bacs 2 et 3 (`worldkit sandbox list --all`). **Sans `--sandbox`, `run save` écrit dans le monde de travail.**

La file de revue présente chaque proposition avec sa qualification : `enrichment` (fait nouveau), `support` (confirme l'existant, compté à part), `anomaly` (contredit l'état en place), `batch_conflict` (deux passages du lot se contredisent)… La première proposition est une **anomalie** : les vieilles notes disent « baron », mais Odon est régent depuis la section 6. Le document est en mode `source` : il décrit, il ne décide pas ; l'état en place l'emporte tant que l'auteur ne tranche pas. On la refuse, avec une raison :

```powershell
worldkit --db valmont.db call review.refuse --param "proposals=[b1.notes-baron.p1.1]" --param "reason=notes antérieures à la régence" --sandbox 4
```

```text sortie
review.refuse [write] → sandbox:4 : ok
```

À l'écran : choisissez « bac 4 » dans la barre de contexte, puis **Revue** : chaque proposition montre ses changements, leur qualification et les boutons accepter, refuser, choisir, adapter ; les affirmations d'un document en jeu (une chronique) se qualifient vraie, fausse ou indéterminée. Chaque décision est tracée ; rien n'est écrit dans le monde de travail tant que le bac n'est pas rendu réel.

## 8. Faire un retcon : Aldren est mort de fièvre

Une **redéfinition rétroactive** change le passé : Aldren n'a pas été empoisonné, il est mort de fièvre. L'histoire ne s'efface jamais : l'outil crée une nouvelle branche, y applique la redéfinition après `e003`, puis rejoue les éditions postérieures une à une. D'abord l'**aperçu d'impact**, qui n'écrit rien :

```yaml fichier=fievre.yaml
changes:
  - {op: set_attribute, entity: aldren-ii, attribute: death_cause, value: fièvre, visibility: secret}
  - {op: remove_relation, from: mervin, relation: killed, to: aldren-ii}
```

```powershell
worldkit --db valmont.db redefine fievre.yaml --after e003
```

```text sortie
aperçu d'impact (R-RED-01) : reference, ancrage au rang 4
4 édition(s) postérieure(s), dont 0 concernée(s) :
```

Quatre éditions viennent après `e003` (dont `g2`, Odon régent) ; aucune ne touche les faits redéfinis, le rejeu passera sans conflit.

Puis le rejeu :

```powershell
worldkit --db valmont.db redefine fievre.yaml --after e003 --mode retroactive
worldkit --db valmont.db wiki page aldren-ii
```

```text sortie
rejeu r1 : nouvelle branche reference-r1 depuis le rang 4
g2 : rejouée → g2@reference-r1
rejeu r1 terminé : reference-r1 remplace reference, archivée (consultable)
branche de référence : reference-r1 (R-MON-02)
- death_cause : fièvre _[secret · r1.redefinition]_
```

La nouvelle branche devient la **référence** ; l'ancienne est archivée, lisible, jamais modifiée. À l'écran : **Branches** montre la lignée ; **Comparer** met la page d'Aldren sur les deux branches côte à côte ; le **Graphe** en mode comparaison marque l'arête `killed` comme retirée. Si une édition rejouée entre en conflit, le rejeu s'arrête et la **Revue** (section « Rejeux ouverts ») demande de garder, adapter ou écarter.

## 9. Tester un mécanisme seul

Le **Banc de mécanismes** exécute une seule opération sur une entrée choisie. Exemple : quelles **clés de fait** un changement lit et écrit ?

```powershell
worldkit --db valmont.db call change.keys --param "change={op: add_relation, from: mervin, relation: rules, to: brume}"
```

```text sortie
change.keys [compute] → world : ok
occupied : 1
occupied_by:
```

Le changement écrit une clé, `(rules, brume)`, déjà occupée par la relation d'Odon : c'est ce qui a fait refuser l'édition de la section 5. `change.keys` le montre sans juger ; c'est `edit.check` qui en fait une collision.

À l'écran : **Banc**, opération `change.keys` ; un exemple sur Valmont est proposé pour chaque opération. « Rejouer » relance la même entrée et signale toute différence : le noyau doit toujours rendre la même sortie pour la même entrée. `worldkit ops` (ou l'écran **Opérations**) liste toutes les opérations et leurs paramètres.

## 10. Mesurer un extracteur

La **mesure T2** compare ce qu'un extracteur produit à ce qu'attend le gold : **précision** (ce qu'il produit est-il juste ?) et **rappel** (trouve-t-il tout ?). On mesure d'abord l'oracle contre lui-même : il doit être parfait, sinon c'est la mesure qui est fausse.

```powershell
worldkit --db valmont.db call eval.run --param "batch=[b4]"
```

```text sortie
eval.run [compute] → world : ok
precision : 1.0
recall : 1.0
```

Avec un modèle (profils dans `worldkit-llm.yaml`, à copier depuis `worldkit-llm.example.yaml`), la même commande **n'appelle rien** : elle rend `pending` avec l'estimation exacte du nombre d'appels ; il faut ajouter `confirm=true` pour lancer. Au-delà du plafond (`max_calls_per_run`, 30), la mesure est refusée. **Une mesure réelle consomme du quota.**

```powershell sans-test
worldkit --db valmont.db call eval.run --param "batch=[b4]" --param profile=sonnet
worldkit --db valmont.db call eval.run --param "batch=[b4]" --param profile=sonnet --param confirm=true
```

À l'écran : **Mesures** — historique, détail par opération et par passage (manqués, en trop, pièges), et comparaison de deux mesures jusqu'au passage, pour choisir entre deux modèles.

## 11. Vérifier après un changement de code

Les **parcours d'acceptation** W00 à W17 du corpus rejouent des scénarios d'usage complets, chacun dans un monde neuf, avec leurs prérequis :

```powershell
worldkit --db valmont.db walkthrough run W15
```

```text sortie
W15 : ok
chaîne W01 → W02
[réussi ] Vues antérieures de la nouvelle branche : Aldren mort de fièvre depuis l'ancrage.
```

W15 (le retcon d'Aldren) suppose W13, qui suppose W12… : toute la chaîne est rejouée dans un **monde d'acceptation** neuf, jamais dans le vôtre.

Chaque attendu est `passed`, `failed` (valeur obtenue et attendue montrées) ou `unstructured` (écrit en prose : à lire). À l'écran : **Acceptation**. Et toujours, avant de commiter :

```powershell sans-test
.venv\Scripts\python -m pytest -q
```

## 12. Pour aller plus loin

- `worldkit explain <code ou mot>` et l'écran **Aide** : toute règle, décision, étape, opération, statut ou code de signalement.
- `worldkit --help`, `worldkit ops` : toutes les commandes et opérations.
- **Exécutions** : tout ce qui a été enregistré, relisible (`worldkit runs list`, `worldkit runs show N`).
- Les cadres (`docs/cadre-*.md`) pour les règles, *outils.md* pour la carte des écrans.
