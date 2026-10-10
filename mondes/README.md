# Mondes de l'auteur

Les mondes sur lesquels l'auteur travaille, distincts des corpus (`corpus/`) : un corpus est un **instrument de
mesure** (son schéma, son gold et ses tests ne changent pas au fil du travail), un monde d'auteur évolue.

## Corbelle (`corbelle/`)

Tiré du corpus `corpus/corbelle-v1/corbelle/` (même état de base), avec un schéma complété par l'auteur : `on_river`
(« au bord de »), `runs` (« tient »), `near` (« près de », symétrique), `hates` (« déteste »). Le corpus, lui, garde
`hates` hors schéma : c'est le cas qui éprouve la question ciblée (E-007).

Repartir de zéro (PowerShell, depuis la racine du projet) :

```powershell
Remove-Item corbelle.db, corbelle.runs.db, corbelle.sandbox-*.db -ErrorAction SilentlyContinue
worldkit --db corbelle.db world init mondes/corbelle/world.yaml
worldkit --db corbelle.db edit apply mondes/corbelle/edits/base.yaml
worldkit --db corbelle.db point set '@base'
worldkit --db corbelle.db schema show
```

Une relation ajoutée plus tard par une édition de schéma (écran Saisie) vit dans le journal de `corbelle.db` ;
pour la garder au prochain départ, l'ajouter aussi ici, dans `corbelle/schema.yaml`.
