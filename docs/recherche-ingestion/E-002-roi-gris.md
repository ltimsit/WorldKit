# E-002 — « le Roi Gris » créé au lieu d'un alias d'Aldren II

- **Statut** : ouverte
- **Classe** : R (résolution) ; T sous Haiku (« régnait autrefois » pris pour un fait actuel)
- **Où** : b1, `lieux-de-valmont`, passage 4 ; extraction monolithique (futures couches C1 et C2)
- **Observé avec** : Claude Sonnet 5, `claude-code`, prompt version 3, 28 septembre 2026 ; Claude Haiku 4.5, `api-haiku`, 4 octobre 2026, 1 passe ([X-001](X-001-b1-haiku-reference.md)), aggravé : en plus de la création, `roi-gris rules hautval` et `title = roi`, alors que la règle 5 (« régnait autrefois » n'est pas un fait actuel) cite ce cas
- **Coût en revue** : une fausse création (entité « Roi Gris »), et le doublon qui s'ensuit si elle est acceptée

## Observation

Passage : « Le Roi Gris régnait autrefois depuis Hautval, avant la Chute. »

Sortie : `create_entity` « Roi Gris » (Character).

Attendu (gold) : mentions `{ "Le Roi Gris": aldren-ii, "Hautval": hautval, "la Chute": la-chute }` ; `add_value aldren-ii.aliases = "le Roi Gris"` (enrichissement). Le piège est voulu : `edits/base.yaml` ne donne **aucun** alias « le Roi Gris » à Aldren II.

## Explication

1. **L'information n'est ni dans le texte ni dans l'état.** Rien dans le passage ne relie « le Roi Gris » à Aldren II. L'état de base (`edits/base.yaml`) donne à Aldren II le titre de roi, un frère (Mervin) et un fils (Corvin), mais aucun lien avec Hautval ni avec la Chute ; et Mervin porte aussi le titre de roi. Le seul indice, « régnait autrefois » (Mervin règne aujourd'hui), demande une inférence temporelle fragile.
2. Le modèle reçoit toutes les entités connues, mais sous forme de noms et d'identifiants, sans **fiche** (titre, relations) : même l'indice faible n'est pas à sa portée.
3. Créer une entité nouvelle est le choix prudent quand on ne sait pas. L'erreur est donc raisonnable ; ce qui manque, c'est le **doute exprimé** : « peut-être Aldren II ou Mervin (rois) ».

## Remèdes envisagés

1. *Mesure* : aucun ; c'est un vrai piège.
2. *Déterministe* : rien de sûr. Un index des titres (« roi ») propose Aldren II et Mervin comme candidats, sans pouvoir trancher.
3. *Consigne* : fiches verbalisées des candidats (chantier §10.3 : « Aldren II, roi, frère de Mervin » ; « Mervin, roi, règne sur Valmont »). À mesurer : le modèle propose-t-il les deux rois en doute plutôt que de trancher, et avec quel taux de faux rapprochements ?
4. *Humain* : l'auteur annote « le Roi Gris → aldren-ii » (portion ou source entière) ; la proposition d'alias part vers le journal ; acceptée, toute résolution suivante est exacte sans appel. **Remède attendu pour ce cas** : l'information est dans la tête de l'auteur.
5. *Couche* : C2 avec liste courte et fiches, qui **marque un doute** au lieu de créer en silence. Indicateur : la fausse création devient-elle une annotation douteuse avec Aldren II et Mervin en candidats ? Ce serait déjà un gain de revue (un geste « choisir » au lieu de « refuser, puis fusionner »).

## Essais

Aucun pour l'instant. Premier essai prévu : remède 5 sous sa forme minimale (doute exprimé, candidat proposé), puis remède 4 pour mesurer le rendement de l'annotation.

## Conclusion

À venir.
