# X-002 — Repérer puis recouper : C1 et C2 sur une fenêtre au document (b1)

- **Statut** : conclue (première itération)
- **Hypothèse** : avec le document entier pour contexte et une seule question (« quelles entités sont mentionnées ? »), sans la liste des entités connues, un petit modèle repère les entités mieux que l'extracteur actuel, en particulier celles qu'il prenait pour des valeurs (E-003) ; et le recoupement avec l'état se fait sans modèle pour presque toutes les mentions.
- **Couches et modèles** : C1a (noms connus, déterministe), C1b (mentions nouvelles, Claude Haiku 4.5 par l'API, `api-haiku`, substitut), C2 (recoupement déterministe, sans liste courte au modèle dans cette première version). Fenêtre : le document entier (les deux documents de b1 tiennent largement dans le budget).
- **Écarts liés** : E-003 (premier témoin), E-002 (le Roi Gris : doit sortir comme entité nouvelle ou doute, jamais résolu à tort).

## Protocole

- Entrées : lot b1 (`notes-baron` v1, `lieux-de-valmont`), état de base.
- C1b : un appel par document, **2 appels** en tout ; sortie : liste de mentions (texte exact, type parmi les types du schéma, niveau de confiance, doute éventuel). Prompt court, sans liste des entités connues. Coût estimé : moins d'un centime ; accord de l'auteur avant l'appel.
- C1a et C2 : sans modèle. Recherche exacte des noms et alias de l'état ; recoupement par nom normalisé, variante de surface compatible avec le type, index des titres.
- Référence : les `mentions` du gold de b1 (texte → identifiant ou `new:`), par passage. Une mention trouvée est rattachée à son passage par son texte exact.
- Indicateurs (chantier §9) :
  - C1 : rappel et précision des mentions (texte), exactitude du type ;
  - C2 : part des mentions recoupées sans modèle, exactitude de l'identifiant ou du « nouveau » ;
  - gestes simulés pour amener les entités à l'état du gold (garder 1, retirer 1, changer 2, ajouter 3) ;
  - coût et tokens par appel ; stabilité sur deux extractions.
- Comparaison : les entités que l'extracteur actuel (X-001) a repérées ou créées sur les mêmes passages.

## Résultats

4 octobre 2026, `api-haiku`, `--repeat 2` : 4 appels, 0,0094 $, au plus 951 tokens en entrée par appel (le quart de l'extracteur actuel), 1 142 en sortie. Appels tracés et rejouables (`--replay`).

| | Sans modèle (C1a + C2) | Avec Haiku, fusion d'origine | Avec Haiku, fusion corrigée (rejeu) |
|---|---|---|---|
| Mentions du gold trouvées (rappel C1) | 17 / 28 (0,61) | 23 / 28 (0,82) | 23 / 28 (0,82) |
| En trop | 1 | 1 | 4 |
| dont trouvées sans modèle | 17 | 12 | 16 |
| Bien recoupées (C2) | 17 / 17 | 19 / 23 | **22 / 23** |
| Gestes simulés (pondérés) | 51 | 43 | **43** |
| Stabilité (deux extractions) | — | 1,0 et 1,0 | — |

Réponses du modèle (traces) : il relève le conseil des marchands, la taverne du Héron, le Roi Gris, Brume-sur-Mer, « roi Mervin », le Cercle des Cendres, le Loup de cendre, et des désignations plus longues (« baron de Brume », « régent de Brume », « royaume de Valmont », « plaines de Cendrelande »). Il ne relève **ni « Odon » seul ni « le baron »** : une seule forme par entité, malgré la règle 1.

**Correction faite en cours d'expérience** (défaut de conception de C1, pas du modèle) : la fusion gardait la portion la plus longue, si bien que « baron de Brume » effaçait le « Brume » connu qu'il contient (3 recoupements faux). Désormais les noms connus sont toujours gardés et les mentions s'imbriquent ; la mesure ne compte pas comme « en trop » une portion qui chevauche une mention trouvée et désigne la même entité (« Mervin » dans « roi Mervin »). Remesuré par rejeu des traces, sans appel.

Écarts restants :

| Écart | Nombre | Classe | Remède envisagé |
|---|---|---|---|
| « Odon » seul non relevé | 4 | N | forme courte : consigne de C1b, ou règle déterministe |
| « le baron » non relevé | 1 | N | déterministe : un titre porté par une seule entité devient un nom cherché par C1a |
| « Roi Gris » recoupé comme entité nouvelle | 1 | R | l'auteur (E-002) ; attendu |
| désignations en trop (« baron de Brume », « régent de Brume », « royaume de Valmont », « la Chute » en p7) | 4 | G ou N | vraies mentions absentes du gold ; « royaume de Valmont » typé Faction au lieu de Place |

## Lecture

1. **E-003 disparaît au niveau des entités.** Le conseil des marchands est repéré dans les trois passages, comme une seule entité nouvelle pour tout le lot (T-ING-07). L'extracteur actuel ne l'avait créé dans aucun (X-001). Une question étroite sur le document entier suffit ; reste à vérifier que les faits suivent (C5).
2. **Le recoupement sans modèle tient** : 22 mentions sur 23 rattachées correctement par des règles déterministes (nom exact 16, nom contenu 2, entité nouvelle 5). La seule erreur est le Roi Gris, qu'aucun traitement ne peut résoudre sans l'auteur.
3. **Le modèle n'est plus nécessaire pour ce qu'on connaît déjà** : la moitié des mentions (16) sont trouvées sans lui. Son rôle se réduit aux entités nouvelles et aux désignations.
4. **Le prompt est 4 fois plus petit** (951 tokens au plus contre 3 538) et la sortie parfaitement stable sur deux extractions.
5. **Le modèle relève les entités, pas toutes leurs mentions** : une forme par entité. Pour la provenance (quels passages parlent d'Odon ?), il faut aussi les formes courtes ; c'est le prochain écart à traiter.
6. **Le Roi Gris est classé `sure`** : aucun doute exprimé. Le niveau de confiance ne signale pas ce cas ; c'est C2 (aucun candidat) qui le laisse à l'auteur.
7. Limites : 2 documents, 28 mentions, substitut plus capable qu'un vrai petit modèle.
