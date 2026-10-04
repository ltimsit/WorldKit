# X-002 — Repérer puis recouper : C1 et C2 sur une fenêtre au document (b1)

- **Statut** : prévue
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

À venir.

## Lecture

À venir.
