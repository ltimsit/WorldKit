# Corpus Valmont bruité (v1) — corpus dérivé

**Sorte :** corpus **dérivé** ([axes-corpus.md](../../docs/recherche-ingestion/axes-corpus.md)) : le lot b1 de Valmont, perturbé par un script reproductible (`corpus/tools/derive_noisy.py`, graine fixe). **Ne pas modifier à la main** : régénérer avec `.venv\Scripts\python corpus/tools/derive_noisy.py` ; `tests/test_corpus_bruite.py` vérifie que les fichiers sont exactement ceux du script.
**Objet :** éprouver le recoupement par score, les marqueurs d'énonciation et la chaîne en couches sur un texte **qu'ils n'ont pas vu** (les seuils ont été réglés sur Valmont propre et Corbelle). Le fond est celui de Valmont : mêmes entités, mêmes faits attendus ; seule la surface change.
**Date :** 4 octobre 2026.

## Perturbations (axes)

Mot par mot, avec un tirage par (niveau, document, passage) :

| Perturbation | Axe | Taux l1 | Taux l2 |
|---|---|---|---|
| faute de frappe sur un mot à majuscule d'au moins 5 lettres (lettre doublée, manquante, inversée) | AX-S1 | 0,15 | 0,35 |
| minuscule à la place de la majuscule | AX-S4 | 0,25 | 0,6 |
| accents retirés | AX-S3 | 0,3 | 0,8 |
| abréviations (pour → pr, dans → ds, depuis → dps, est → c…) | AX-S5 | 0,5 | 1,0 |
| sigles (conseil des marchands → CdM, Cercle des Cendres → CdC) | AX-S5 | 0,5 | 1,0 |
| ponctuation retirée (. , ; :) | AX-S6 | 0,3 | 0,8 |

Exemple (l2) : « hautvl la capitale domine la vallee Le CdM y tient ses séances ».

## Contenu

```
valmont-bruite-v1/
├── README.md
├── l1/  docs/b1/ (2 documents), docs/batches.yaml (lot l1-b1), gold/
└── l2/  docs/b1/ (2 documents), docs/batches.yaml (lot l2-b1), gold/
```

**Gold** : celui de Valmont b1, mentions recalées sur leur forme bruitée (« Brme » → brume, « CdM » → le conseil des marchands), début des passages recalé, `derived_from` (début d'origine) ; les changements attendus ne changent pas : une valeur bien écrite reste la valeur attendue.

## Mesurer

Monde : celui de Valmont à l'état de base (`corpus/valmont-v1/valmont/world.yaml`, `edits/base.yaml`).

```powershell
worldkit --db valmont.db eval mentions --batches corpus/valmont-bruite-v1/l1/docs/batches.yaml --oracle corpus/valmont-bruite-v1/l1/gold --batch l1-b1 --no-model
```

Au niveau l2, le conseil des marchands n'apparaît jamais en entier : seulement « CdM » (sigle d'une entité **nouvelle**).
