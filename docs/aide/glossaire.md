# Glossaire complémentaire de l'outil

**Objet :** définir ce que l'outil affiche et que les glossaires des cadres ne définissent pas : statuts, sortes d'opérations, codes de signalement, valeurs d'énumérations, marques du graphe, vocabulaire des exécutions, des bacs, des parcours et des mesures. Une ligne par terme ; un même nom technique n'est défini qu'une fois, ici ou dans un cadre.
**Version :** 1.0 — 27 septembre 2026. Complète les glossaires de *cadre-fondation.md* (§3), *cadre-technique.md* (§10) et *cadre-interface.md* (§12), sans les répéter.
**Lecture :** ces tableaux alimentent l'aide de l'interface (`/aide`) et `worldkit explain` (I-AID-01). Corriger une définition ici la corrige partout. Un test vérifie que tout statut, code ou valeur affichable a sa ligne.

---

## 1. Résultat d'une opération

Toute opération du service rend un résultat de même forme (cadre d'interface §7).

| Terme | Nom technique | Définition |
|---|---|---|
| Réussi | `ok` | L'opération a fait ce qui était demandé. Des avertissements peuvent l'accompagner. |
| Refusé | `refused` | L'opération n'a rien fait : au moins un signalement de sévérité `error` l'en empêche (changement hors schéma, collision, plafond dépassé…). Les signalements disent pourquoi et citent la règle. |
| En attente | `pending` | Deux sens. **Résultat** : l'opération attend une confirmation avant d'agir (appel à un modèle, écriture dans le monde de travail). **Édition** : proposition soumise, ni confirmée ni abandonnée (R-CYC-04). |
| Erreur | `error` | Deux sens. **Résultat** : l'opération a échoué sur une exception (bogue, fichier illisible) ; la trace est dans le JSON brut. **Sévérité** d'un signalement : bloquant. |
| Avertissement | `warning` | Sévérité d'un signalement non bloquant : signalé, rien n'est refusé (non-conformité, fait masqué…). |
| Sorte d'opération | `kind` | `read`, `compute`, `write` ou `admin` : dit si l'opération écrit et si elle est enregistrée. |
| Consultation | `read` | Sorte d'opération qui lit sans rien écrire ; non enregistrée (elle se recalcule depuis l'état), sauf épinglée. Accessible en GET (`/api/call/…`). |
| Calcul | `compute` | Sorte d'opération qui calcule sans écrire dans le monde (vérifier, qualifier, exécuter des étapes, mesurer) ; enregistrée, pour comparer deux exécutions. |
| Écriture | `write` | Sorte d'opération qui écrit dans un monde ou un bac ; enregistrée et rejouable (c'est ce que rejoue « rendre réel »). |
| Administration | `admin` | Sorte d'opération qui gère bacs et exécutions (créer, jeter, purger) ; enregistrée, jamais rejouée. |
| Cible | `target` | Le fichier sur lequel porte un appel : `world` (monde de travail) ou `sandbox:<n>` (bac n). Choisie dans la barre de contexte. |
| Rang | `seq` | Position d'une édition dans le journal d'une branche (1, 2, 3…). Un état « au rang 12 » est la projection des 12 premières éditions ; un point nommé désigne un rang. |
| Indicateurs | `indicators` | Nombres clés d'un résultat (faits, propositions, précision, appels…), affichés et comparables d'une exécution à l'autre. |
| Trace | `trace` | Ce qui varie d'une exécution à l'autre sans dépendre de l'entrée : durée, version du code, appels au modèle, numéro d'exécution. |
| JSON brut | `raw` | Le résultat complet tel que le service le rend, en JSON canonique ; lien sous chaque résultat. |

## 2. Codes de signalement

Un signalement (`Issue`) porte un code, une sévérité, un message et la règle qui le fonde.

| Terme | Nom technique | Définition |
|---|---|---|
| Schéma mal formé | `malformed_schema` | Le fichier de schéma n'a pas la forme attendue (pas un dictionnaire, champ inconnu, type de valeur faux) (T-SCH-01). |
| Type noyau redéclaré | `core_type_declared` | Le schéma déclare un type ou une relation que la plateforme fournit déjà (`Document`, `derived_from`…) (R-NOY-01). |
| Référence non déclarée | `undeclared_reference` | Le schéma cite un type, une relation ou un type parent qu'il ne déclare pas (R-SCH-01). |
| Cycle d'héritage | `inheritance_cycle` | Des types héritent les uns des autres en boucle (R-SCH-01). |
| Attribut hérité redéfini | `inherited_attribute_redefined` | Un type redéclare un attribut qu'il hérite déjà de son parent (T-SCH-01). |
| Bornes invalides | `invalid_bounds` | Bornes d'un attribut incohérentes (minimum au-dessus du maximum). Prévu, pas encore émis. |
| Relation symétrique asymétrique | `asymmetric_symmetric_relation` | Une relation déclarée symétrique relie des types différents en `from` et en `to` (R-SCH-01). |
| Identifiant non anglais | `non_english_identifier` | Un identifiant technique n'est pas en ASCII anglais ; les libellés en français vont dans `labels` (R-SCH-07). |
| Changement mal formé | `malformed_change` | Un changement est hors du catalogue d'opérations ou mal écrit (champ manquant, opération inconnue) (R-EDI-06). |
| Attribut requis manquant | `missing_required` | Une entité est créée sans un attribut que son type rend obligatoire (R-SCH-06). |
| Entité inconnue | `unknown_entity` | Le changement vise une entité absente de l'état visé (branche, point) ; ou la page demandée n'existe pas dans cette vue (R-EDI-04). |
| Fiche manquante | `missing_sheet` | Une entité d'un type couvert par un système n'a pas de fiche dans ce système (conformité, avertissement). |
| Fait public masqué | `masked_public_fact` | Un fait déclaré public est caché en vue joueur parce qu'il mentionne une entité non publique (R-NOT-07). Exemple : « Mervin a empoisonné Aldren » public, mais Mervin secret. |
| Règle d'édition | `edit_rule` | Une règle sur la forme ou le cycle de vie d'une édition est violée (origine manquante, `delete_entity` hors correction, branche archivée, édition déjà confirmée…). Le message et la règle citée précisent laquelle. |
| Collision de clé | `key_collision` | Le changement écrit une clé de fait déjà occupée par une autre valeur : c'est la contradiction détectée par le noyau (R-FAI-05). Exemple : ajouter « Mervin gouverne Brume » alors qu'Odon la gouverne déjà (`rules` est `one_to_many` : un lieu n'a qu'un gouvernant) ; il faut retirer la relation d'Odon dans la même édition. Autre cas : créer une entité qui existe déjà. Modifier un attribut par `set_attribute` n'est pas une collision : c'est un changement voulu. |
| Contradiction interne | `internal_contradiction` | Une même édition écrit deux fois la même clé avec des valeurs différentes (R-FAI-05). |
| Fait absent | `missing_fact` | Le changement retire ou modifie un fait qui n'existe pas dans l'état visé (R-EDI-04). |
| Édition périmée | `stale_edit` | L'édition a été écrite contre un état qui a changé depuis (autre branche, rebase, transposition non automatique) ; elle doit être revue (R-HIS-05). |
| Document obsolète | `document_obsolete` | La proposition vient d'un document déclaré obsolète : bloquée, réactivée si le statut est levé (R-DOC-05). |
| Dépendance de scénario | `scenario_dependency` | Un scénario suppose un autre scénario qui n'a pas été joué dans cette branche ; signalé, non imposé (R-SCN-07). |

## 3. Valeurs affichées

| Terme | Nom technique | Définition |
|---|---|---|
| Secret | `secret` | Notoriété : connu de l'auteur seul ; absent de toute vue joueur (R-NOT-01). |
| Public | `public` | Notoriété : connu des joueurs ; visible en vue joueur, sauf s'il est masqué (R-NOT-01, R-NOT-07). |
| Non qualifié | `unqualified` | Notoriété pas encore décidée (valeur par défaut) ; traitée comme `secret` par tout filtre joueur (R-NOT-01, R-NOT-03). |
| Appliquée | `applied` | Statut d'une édition inscrite au journal : elle fait partie de l'histoire et ne sera jamais modifiée ni retirée (R-CYC-01). |
| Abandonnée | `abandoned` | Statut d'une édition en attente qu'on a renoncé à appliquer ; elle reste tracée (R-CYC-04). |
| Diégétique | `diegetic` | Nature d'un passage : il parle de l'univers (personnages, lieux, événements). |
| Méta : système | `meta_system` | Nature d'un passage : il décrit un système de règles (caractéristiques, catégories, contraintes) (T-ING-20). |
| Méta : fiche | `meta_sheet` | Nature d'un passage : il donne les valeurs de jeu d'une entité dans un système (T-ING-20). Exemple : « Système B : niveau 7, menace 8. » pour le Loup de cendre. |
| Mixte | `mixed` | Nature d'un passage qui mêle univers et méta ; le classement sépare ce qui relève de chacun. |
| En jeu | `in_world` | Voix d'un document écrit depuis l'univers (une chronique, une lettre) : ce qu'il dit devient des affirmations, pas des faits. |
| Source | `source` | Mode d'un document qui décrit l'univers tel qu'il est : une contradiction avec l'état y est une anomalie, qui donne une proposition en attente ; l'état en place l'emporte. En mode `edit`, elle est une intention de changement (cadre de la fondation §5.2). |
| Auteur | `author` | Deux sens. **Filtre** : vue complète, secrets compris. **Voix** : document écrit par l'auteur, qui énonce des faits. |
| Joueur | `player` | Filtre de vue : seulement ce qui est public et non masqué ; le non qualifié y est traité comme secret (R-NOT-03, R-NOT-07). |
| Couche du graphe | `layer` | Groupe d'éléments affichables dans le graphe : `world` (entités et relations), `system` (éléments de système), `sheet` (fiches), `identity` (identités), `claim` (affirmations), `document` (documents sources). |
| Masqué | `masked` | Marque du graphe : fait public caché en vue joueur par une entité non publique (R-NOT-07). |
| Redéfini plus tard | `redefined_later` | Marque d'un fait lu à un point antérieur alors qu'une redéfinition plus récente le change (R-VUE-03). Exemple : le règne d'Odon sur Brume lu à `@base` dans `variante-mj`. |
| Orphelin | `orphan` | Marque d'un fait d'origine documentaire qui a perdu son dernier support (passage supprimé à la ré-ingestion) ; signalé, jamais retiré d'office (R-FAI-06). |
| Ajouté | `added` | Comparaison : présent à droite seulement. |
| Retiré | `removed` | Comparaison : présent à gauche seulement. |
| Changé | `changed` | Comparaison : présent des deux côtés avec une valeur différente. |
| Identique | `same` | Deux sens. **Comparaison** : présent des deux côtés, à l'identique. **Verdict** de répétition à blanc : l'action rejouée donne exactement le même résultat que dans le bac. |

## 4. Exécutions, bacs et tâches de fond

| Terme | Nom technique | Définition |
|---|---|---|
| En cours | `running` | Exécution lancée en tâche de fond, pas encore terminée ; sa page se rafraîchit seule. |
| Interrompue | `interrupted` | Exécution qui tournait quand le serveur s'est arrêté ; marquée au redémarrage, sans résultat. Ce qui a été extrait reste en cache. |
| Tâche de fond | `job` | Exécution longue (pipeline, mesure, parcours) lancée dans un fil à part : on peut suivre sa progression et l'arrêter proprement. |
| Actif | `active` | Bac à sable utilisable. |
| Jeté | `dropped` | Bac à sable abandonné ; son fichier est supprimé, son historique d'exécutions reste. |
| Rendu réel | `promoted` | Bac à sable dont les actions ont été rejouées sur le monde de travail. |
| Rendre réel | `promote` | Rejouer sur le monde de travail les écritures enregistrées d'un bac, en tout ou rien, après une répétition à blanc (I-SBX-01). Jamais une copie de fichier (R-HIS-01). |
| Répétition à blanc | `dry_run` | Avant de rendre réel : rejouer les actions sur une copie fraîche du monde de travail et comparer chaque résultat à celui du bac. |
| Écart | `gap` | Verdict de répétition à blanc : l'action réussit mais sa sortie diffère (rang décalé…). Montré, n'empêche pas d'appliquer. |
| Divergence | `divergence` | Verdict de répétition à blanc : l'action serait refusée ou changerait de sens sur le monde actuel. Empêche d'appliquer. |
| Ignorée | `ignored` | Verdict de répétition à blanc : action refusée ou en erreur dans le bac, donc non rejouée. |
| Monde d'acceptation | `acceptance_world` | Fichier neuf (`monde.acceptance-<n>.db`) où s'exécute un parcours d'acceptation ; jamais promouvable. |
| Plafond d'appels | `max_calls_per_run` | Nombre maximal d'appels au modèle par exécution (30 par défaut, `worldkit-llm.yaml`). Un pipeline s'arrête proprement au plafond ; une mesure T2 qui le dépasserait est refusée (I-LLM-01, I-MES-01). |
| Estimation | `estimate` | Nombre exact d'appels au modèle qu'une exécution ferait : passages absents du cache pour ce profil et ce prompt. Montrée avant toute confirmation. |

## 5. Parcours d'acceptation

| Terme | Nom technique | Définition |
|---|---|---|
| Parcours | `walkthrough` | Scénario d'usage W00 à W17 du corpus, rattaché à un jalon, avec ses étapes et ses attendus : les tests d'acceptation. |
| Prérequis | `requires` | Parcours à exécuter avant celui-ci pour partir du bon état (W15 suppose W05…). |
| Attendu vérifié | `passed` | Attendu structuré dont la vérification réussit. |
| Attendu échoué | `failed` | Attendu structuré dont la vérification échoue ; le détail montre la valeur obtenue et l'attendue. |
| Attendu à lire | `unstructured` | Attendu écrit en prose seulement : à vérifier par une personne (I-ACC-03). |

## 6. Mesures T2

| Terme | Nom technique | Définition |
|---|---|---|
| Gold | `gold` | Annotations de référence du corpus (`valmont/gold/`) : pour chaque passage, les changements et conclusions attendus. |
| Oracle | `oracle` | Extracteur qui lit le gold au lieu d'appeler un modèle (T-ING-19). Mesuré contre lui-même, il est parfait : sert de contrôle. |
| Précision | `precision` | Part de ce que l'extracteur a produit qui est attendu par le gold : vp / (vp + fp). Basse : il invente. |
| Rappel | `recall` | Part de ce qu'attend le gold que l'extracteur a trouvé : vp / (vp + fn). Bas : il oublie. |
| Vrai positif | `tp` | Changement produit et attendu. |
| Faux positif | `fp` | Changement produit mais non attendu (« en trop »). |
| Faux négatif | `fn` | Changement attendu mais non produit (« manqué »). |
| Piège | `trap` | Difficulté annotée dans le gold (faux homonyme, ironie, rumeur…) ; « tombé » : l'extracteur s'y est laissé prendre. Exemple : le « Roi Gris ». |
| Facultatifs | `optional` | Changements du gold marqués `optional: true` (vrais, mais qu'on ne reproche pas d'oublier) : neutres dans la mesure, ni manqués ni en trop. Décompte « trouvés / attendus » (`1/4`). |
| Supports | `supports` | Changements qui ne font que confirmer un fait déjà présent ; comptés à part : la précision « questions » les exclut. |
| Erreur d'attribution | `attribution_error` | Affirmation rattachée au mauvais énonciateur. |
| Usage | `usage` | Appels au modèle d'une mesure, au total et par passage : nombre d'appels, tokens en entrée (tout le prompt, cache compris) et en sortie, tokens lus du cache, coût en dollars (« — » si le profil n'a pas de prix). |
| Budget d'entrée | `budget` | Tokens d'entrée permis par appel pour simuler un petit modèle : 4 000 par défaut, réglable par `WORLDKIT_LLM_INPUT_BUDGET` (`off` : aucun). Un dépassement est signalé et mesuré, jamais refusé. |
| Au-delà du budget | `over_budget` | Nombre d'appels dont l'entrée dépasse le budget ; `excess_tokens` : tokens de trop au total ; `max_excess` : le plus grand dépassement d'un appel. |
| Mesure des mentions | `eval mentions` | Mesure des couches C1 (repérer les entités d'un document) et C2 (les recouper avec l'état) contre les mentions du gold (expérience X-002) ; `--no-model` : la part trouvée sans modèle. |
| C1 | `c1` | Repérage : mentions du gold trouvées (`tp`), manquées (`fn`), en trop (`fp`) ; `found_without_model` : trouvées par les seuls noms connus. |
| C2 | `c2` | Recoupement : mentions trouvées rattachées à la bonne entité (ou reconnues nouvelles), et règle qui a tranché : `exact` (nom ou alias, comparés sans casse, accents ni ponctuation), `title` (titre porté par une seule entité), `similar` (ressemblance au-dessus du seuil : faute, nom partiel, sigle, initiale), `designation` (« <titre> de <nom connu> » : l'entité seule qui porte le titre et est reliée au nom), `short` (forme courte d'un nom de personne, variante B), `doubt` (ressemblance moyenne, plusieurs candidats proches, ou désignation qu'on ne sait pas rattacher : à préciser par l'auteur, jamais créée), `ambiguous` (même nom pour plusieurs entités), `new` (aucun candidat). C1 sans modèle trouve aussi « le <titre> » quand ce titre est porté par une seule entité (règle `title`) et ignore le texte barré (`~~…~~`). `new_proposed` et `new_false` comptent les entités nouvelles proposées et celles que le gold n'attend pas (créations à refuser) ; `doubts` les mentions laissées à l'auteur. |
| Formes courtes | `--prompt-short-forms`, `--short-forms` | Deux variantes pour relever « Odon » quand « Odon de Brume » est repéré : A, une consigne de plus au modèle ; B, les mots d'un nom de personne cherchés sans modèle (expérience X-003). |
| Gestes simulés | `gestures` | Gestes pour amener les mentions à l'état du gold : garder (bonnes), retirer (en trop), changer (mal recoupées), ajouter (manquées) ; `weighted` : total pondéré 1-1-2-3. |
| Mesure des faits | `eval facts` | Mesure de la couche C5 (relations et attributs entre entités confirmées) contre les changements du gold, hors création, nom et notoriété ; entités du gold (`--entities gold`, qualité propre) ou de la chaîne C1 puis C2 (`--entities chain`) ; chaque fait cite sa preuve (expérience X-004). |
| Variantes de C5 et de la question ciblée | `--strict`, `--probe-relations`, `--probe-pairs` | `--strict` : consigne plus stricte pour C5 (écartée, X-008) ; `--probe-relations` : la question ciblée reçoit les relations connues comme préférence ; `--probe-pairs` : elle se déclenche pour toute paire d'entités du passage qu'aucune relation trouvée ne relie, même si le passage a produit d'autres faits. Une relation hors schéma se compare par sa paire d'entités, sans tenir compte de l'identifiant proposé. |
| Phrase muette | `silent_sentences` | Phrase qui cite au moins deux entités confirmées sans qu'aucun fait de C5 ne la cite en preuve ; avec `--probe`, elle reçoit une question ciblée, sans liste de relations, qui peut proposer une relation hors schéma avec sa tournure (expérience X-005). |
| Écartés | `rejected` | Faits de C5 écartés par les contrôles sans modèle : relation dont les types ne conviennent pas au schéma, alias égal au nom (une valeur proche de la valeur connue est, elle, ramenée à celle-ci). |
| Rejeu | `--replay` | Relit les réponses d'appels tracés (`WORLDKIT_LLM_LOG_DIR`) au lieu de rappeler le modèle : mêmes prompts, mêmes réponses, aucun coût. Un prompt qui n'a pas été tracé est une erreur. |
| Introuvable | `unplaced` | Mention rendue par le modèle dont le texte n'apparaît pas tel quel dans le document ; pour un fait (`eval facts`), phrase citée en preuve qui n'apparaît dans aucun passage : il n'est rattaché à rien. |
| Stabilité | `stability` | Accord entre plusieurs extractions répétées d'un même passage (0 à 1) ; mesure le hasard du modèle. Quand elle est inférieure à 1, le détail montre ce que chaque extraction a trouvé seule (« 1re seule », « 2e seule », `variant`). |
