# E-011 — Faits de C5 que des contrôles sans modèle écarteraient

- **Statut** : ouverte
- **Classe** : S (forme) et types
- **Où** : Corbelle c1 ; couche C5
- **Observé avec** : Claude Haiku 4.5, 4 octobre 2026 ([X-006](X-006-corbelle-chaine.md))
- **Coût en revue** : un refus ou une adaptation par fait

## Observation

| Fait | Défaut | Contrôle déterministe |
|---|---|---|
| `bertrand-ostrel rules bateliers` (« maître de la guilde ») | `rules` va vers un lieu ; la Guilde est une Faction | types de la relation (schéma) : écarté ou signalé ; le noyau le signale déjà (validation M1), mais après coup |
| `la-sorgue aliases « la sorgue »`, `vieux-de-l-ecluse aliases « le vieux de l'écluse »` | alias égal au nom | alias dont le nom normalisé égale un nom ou alias existant : écarté |
| `jehan-marcastel title = « bourgmèstre »` | faute sur une valeur connue (« bourgmestre ») | valeur rapprochée de la valeur existante (pliage des accents, distance faible) : support, pas une collision |

## Remèdes envisagés

2. *Déterministe* : les trois contrôles ci-dessus, après C5 et avant la qualification. Le premier rend tôt ce que le noyau dirait (T-ING-17) ; les deux autres évitent une fausse question.

## Essais

Aucun.
