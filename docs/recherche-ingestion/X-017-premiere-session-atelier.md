# X-017 — Première session réelle de l'atelier : l'auteur sur ses notes de Corbelle

- **Statut** : conclue (bilan d'une session ; à refaire sur d'autres sources)
- **Hypothèse** : les gestes réels de l'auteur ne sont pas ceux que l'auteur simulé (gold) prévoit ; ils disent quels écarts coûtent vraiment (chantier §9, « gestes jusqu'à satisfaction » ; étapes 8 et 9 du §16).
- **Couches et modèles** : couche « mentions » avec modèle (C1a, C1b, C2, formes courtes et signal de casse), couche « faits » (C5, question ciblée, énonciation, critique v2) ; Claude Haiku 4.5 par l'API (`api-haiku`).
- **Données** : `corbelle.db` (monde du corpus Corbelle), source `corbelle-notes-en-vrac` (texte de `brouillon-corbelle.md` collé par l'auteur, 9 passages alignés sur le gold) ; exécutions enregistrées (`corbelle.runs.db`) ; 10 octobre 2026, 17 h 20 à 19 h 35.

**Limites** : une source, un auteur, une session ; la durée mêle le travail et la conversation avec Claude (corrections de bugs, questions) : ce n'est pas une mesure chronométrée (T3). Le monde Corbelle de base contient déjà une partie des faits (« déjà connu »).

## Coût

| | Appels | Tokens (entrée / sortie) | Coût |
|---|---|---|---|
| Mentions avec modèle (1 lancement) | 1 | 1 044 / 501 | 0,0035 $ |
| Faits (1 lancement) | 17 | 11 264 / 1 824 | 0,0204 $ |

## Mentions : gestes réels contre gestes simulés

L'auteur simulé corrige les **propositions réelles** du premier lancement jusqu'au gold :

| | Garder | Retirer | Changer | Ajouter | Pondéré (1-1-2-3) |
|---|---|---|---|---|---|
| Simulé (gold) | 22 | 2 | 0 | 1 | 27 |
| Réel (clics) | 16 | 0 | 0 | 0 (1 refusé : bug) | 16 |

- **Aucune correction, aucun retrait** : sur ce document, la couche avec modèle est juste aux yeux de l'auteur. Les « écarts » du simulé sont des **désaccords avec le gold**, pas des erreurs : « l'apothicairerie » est une entité pour l'auteur (le gold la tient pour une faute) ; « abbesse » est une vraie mention qu'il manquait au gold (classe G, corrigé le 11 octobre) ; « jehan » (§5, homonyme) n'a pas été ajouté, sans dommage pour les faits.
- **Un clic vaut souvent plusieurs occurrences** (portée « source ») : 16 clics pour 25 annotations ; le simulé compte par occurrence. Le poids « garder 1 par occurrence » surestime le coût réel.
- **Ce que « garder » a apporté** (relu après coup ; la première version de cette fiche le disait à tort inutile sur 11 clics) : 13 clics confirment une mention **à vérifier** (7 en casse différente, 5 rattachées par ressemblance par le modèle, « abbesse » de confiance moyenne), qui devient sûre dans l'atelier et dans « Ce que disent les documents » ; 2 clics (« le bourgmestre », « le passeur », titres sûrs) ne font que **figer** la décision contre une relance ; 2 sont indispensables (entités nouvelles). « Garder » ne change rien pour la couche « faits », qu'une mention connue alimente sans accord. Conclusion de l'auteur : les gestes étaient justes ; le coût réel est la **lecture**, que les clics ne mesurent pas (il faudra le temps, T3). Le geste de lot « garder toutes les connues » est laissé de côté.
- **Signal « à vérifier » de casse** : 7 mentions signalées, 7 justes (aucun homographe dans des notes en minuscules). Sans coût ici (l'auteur gardait de toute façon), mais tout bruit : à suivre sur une source qui contient des homographes.

## Faits : le schéma est le premier coût

15 faits proposés : 5 déjà connus, 4 mis de côté par le critique, 6 soutenus ou douteux.

| Geste | Fait | Cause |
|---|---|---|
| garder | Ysolde — frère ou sœur de — Jehan Marcastel | — |
| corriger | Corbelle — situé dans → **au bord de** — la Sorgue | relation absente du schéma (E-010) |
| corriger | Ysolde — habite → **tient** — l'apothicairerie | relation absente du schéma |
| corriger | l'apothicairerie — situé dans → **près de** — le Pont-aux-Ânes | relation absente du schéma (E-010) |
| corriger | Ysolde — detests (hors schéma) → **déteste** (`hates`) — la Guilde des Bateliers | relation hors schéma |
| retirer | Ysolde — **gouverne** — l'apothicairerie (question ciblée, soutenu) | relation voisine acceptée ([E-016](E-016-relation-voisine-acceptee.md)) |
| revue | Ostrel — conspires_with — Mère Agathe : acceptation refusée | relation hors schéma |

- **5 gestes sur 6 viennent du schéma**, et chacun a demandé une **édition de schéma à la main** : 5 relations (`on_river`, `runs`, `near`, `hates`, `conspires_with`), chacune par l'écran Saisie, un bac, « Rendre réel » (environ 8 opérations et une saisie YAML par relation), après une question à Claude sur la forme à écrire. C'est le coût dominant de la session.
- Les faits mis de côté l'étaient **à raison** (aucun faux rejet observé ; E-013 ne s'est pas présenté) ; le seul fait faux qui serait parti (« gouverne ») était **soutenu** : E-016.

## Incidents

Quatre défauts de l'atelier rencontrés et corrigés le jour même : mention retirée puis gardée sans entité ; ajout sans sélection (glisser sur un lien) ; liens morts après une erreur (405) ; menu des relations qui présélectionnait « siège à » sur un fait hors schéma. Ajouts nés de la session : contrôle du schéma à la correction d'un fait, étiquettes sous les mentions, écran Schéma, monde d'auteur `mondes/corbelle/`.

## Lecture

1. **Priorité : le geste « ajouter au schéma »** (chantier §6.6), depuis l'atelier et la revue, prérempli par le fait (types de ses entités, nom de la relation). C'est ce qui a coûté le plus, cinq fois.
2. **Les mentions coûtent peu en gestes** sur ce texte ; leur coût est la lecture, qui se mesure au temps (T3), pas aux clics.
3. **Le gold de Corbelle a un manque** (« abbesse », classe G) et une divergence de jugement avec l'auteur (« l'apothicairerie ») : un gold écrit par Claude n'est pas l'auteur ; ces mesures-là se calibrent sur les gestes réels.
4. À refaire sur une source avec homographes et sur un texte plus long, en chronométrant (T3).
