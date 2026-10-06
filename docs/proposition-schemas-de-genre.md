# Proposition : des schémas de genre et de style pour les mondes

**Statut :** proposition, version 0.1 — 6 octobre 2026. Ce n'est pas un cadre : rien de ce qui suit n'est acté. Une fois les questions du §6 tranchées par l'auteur, les choix passent dans *cadre-fondation.md* (§4.3, règles `R-SCH`), dans *cadre-technique.md* (méta-schéma, T-SCH-01) et dans l'analyse (section 00.xx), et ce document est retiré.

## 1. Le besoin

L'auteur veut que mettre en place un monde soit **rapide**. Aujourd'hui, la plateforme fournit un schéma de monde par défaut (fantasy), à copier et à adapter (R-SCH-05). Ce schéma est court (13 relations) : chaque monde le complète à la main, et deux mondes du même genre divergent sans raison.

Vision de l'auteur : un schéma vise **un genre et un style**, pas un univers. Valmont prendrait un schéma « fantasy jdr » ; d'autres mondes, un schéma « science-fiction » ; et des couches de **style** (« littéraire », par exemple) ajouteraient d'autres familles de relations. Les schémas doivent être **complets dès le départ**.

## 2. Ce que les mesures ont montré (X-016)

- **Le coût n'est pas un obstacle** : un schéma complet placé tel quel dans le prompt système est relu en cache par l'API (92 à 96 % de l'entrée, à un dixième du prix) ; un prompt huit fois plus long ne coûte que ~40 % de plus.
- **Montrer tout le schéma au modèle nuit à la qualité** : imposé comme vocabulaire de l'extraction, le schéma « fantasy jdr » (59 relations) fait plus de faits faux que le schéma du monde filtré par types (22 et 11 contre 6, sur 10 lots non vus). Un petit modèle s'en sort mieux avec peu de choix.

Conséquence : un schéma de genre complet est bon **pour le monde** (l'auteur a tout de suite le bon vocabulaire), à condition que l'extraction continue de ne montrer au modèle **que la part utile** (les relations compatibles avec les types des entités de la fenêtre, comme aujourd'hui).

## 3. Proposition

### 3.1 Une bibliothèque de schémas, composables

| Couche | Exemple | Contenu |
|---|---|---|
| **socle** | `socle` | ce que partage toute fiction : personnes, groupes, lieux, objets, événements ; famille, appartenance, localisation, possession, participation |
| **genre** | `fantasy-jdr`, plus tard `science-fiction` | ce que le genre ajoute : créatures, divinités, cultes, malédictions, magie, quêtes ; ou vaisseaux, planètes, IA |
| **style** | `litteraire`, plus tard `intrigue` | des familles de relations propres à une manière de raconter : rivalités, amours, mentors, inspirations ; ou complots, dettes, chantages |

Un monde **choisit** un genre et zéro ou plusieurs styles ; le socle vient avec le genre. Il ajoute ensuite ce qui lui est propre (le « Loup de cendre » de Valmont n'appartient à aucun genre).

Le schéma « fantasy jdr » d'X-016 (`worldkit/periphery/pivot/fantasy-jdr.yaml`) sert de **premier brouillon** : il serait découpé en socle et genre, ses relations littéraires (rivalité, amour, mentor) passant au style `litteraire`.

### 3.2 La copie, pas la référence vivante (recommandé)

À la création du monde, la composition choisie est **résolue et copiée** dans l'état, par l'édition initiale `e000`, comme aujourd'hui. Le schéma copié garde sa **provenance** (`based_on: [fantasy-jdr@1, litteraire@1]`).

- Le schéma reste dans l'état (R-SCH-03) : même entrée, même sortie, sans dépendre d'un fichier extérieur qui changerait.
- Une nouvelle version de la bibliothèque n'est **jamais** appliquée d'office (R-SCH-04) : la plateforme peut la **proposer** comme une édition de schéma (un diff), que l'auteur accepte, adapte ou refuse.

*Voie écartée* : le monde **référence** la bibliothèque (`schema: fantasy-jdr@1`) sans la copier. Plus léger, mais le schéma sortirait de l'état, et une correction de la bibliothèque changerait l'interprétation des faits passés.

### 3.3 Deux ajouts au méta-schéma

1. **Hiérarchie des relations** : `broader: parent_of` sur `mother_of`. Usage proposé, minimal : la hiérarchie est **déclarative**. L'extraction s'en sert pour généraliser sans modèle (si le monde n'a pas `mother_of`, le fait devient `parent_of`, X-016), et les vues pourront s'en servir plus tard (une recherche « famille » trouve les mères). Le noyau n'en tire **aucune inférence** : `mother_of(catelyn, robb)` ne crée pas `parent_of(catelyn, robb)`, et les clés de fait (R-FAI-05) ne changent pas.
2. **Composition** : un fichier de schéma peut déclarer `extends: [socle]` ; le chargeur fait l'union. Un même identifiant défini deux fois est une **erreur** de schéma (pas de surcharge silencieuse). Le résultat est un schéma ordinaire, validé par le validateur unique (R-SCH-02, T-SCH-01).

### 3.4 Ce qui ne change pas

- Les identifiants restent en anglais, les libellés en français par `labels` (R-SCH-07, R-SCH-08).
- Hors schéma reste hors schéma (R-SCH-06) : l'auteur décide de chaque ajout.
- L'extraction continue de filtrer par types ce qu'elle montre au modèle.

## 4. Règles touchées

| Règle | Évolution proposée |
|---|---|
| R-SCH-01 | une relation **peut** déclarer une relation plus générale (`broader`), sans inférence par le noyau |
| R-SCH-03 | inchangée ; la provenance (`based_on`) fait partie du schéma copié |
| R-SCH-04 | inchangée ; une nouvelle version de la bibliothèque est une édition de schéma proposée |
| R-SCH-05 | **remplacée** : « la plateforme fournit une bibliothèque de schémas (socle, genres, styles) ; un monde en choisit une composition, copiée à sa création et adaptable » |
| nouvelle | la composition (`extends`) : union, identifiant en double = erreur |

## 5. Mesure à faire avant d'acter

**X-017, schéma riche filtré** : le monde reçoit le schéma « fantasy jdr » complet comme schéma **de monde** (plus de pivot ni de correspondance) ; l'extraction montre au modèle les relations compatibles avec les types, comme aujourd'hui. Lots non vus, critère posé d'avance comme en X-015 et X-016. Elle dit si un monde riche dès le départ se paie en qualité d'extraction. Coût estimé : 0,15 à 0,25 $.

## 6. Questions pour l'auteur (une à la fois)

1. **Copie ou référence vivante** (§3.2) ? Recommandation : la copie, avec provenance.
2. **Hiérarchie déclarative** (§3.3) : suffit-elle, ou voulez-vous que les vues suivent la hiérarchie dès maintenant ?
3. **Découpage** : socle + genre + styles, ou un seul schéma par genre pour commencer (plus simple) ?
4. **Styles** : lesquels vous serviraient en premier (littéraire, intrigue, autre) ?
5. **Valmont** : garder son schéma tel quel (le corpus de test reste stable), ou le refonder sur « fantasy jdr » ?
