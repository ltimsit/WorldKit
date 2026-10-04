# Contre-corpus de pièges (v1)

**Sorte :** corpus **ciblé**, écrit par Claude ([axes-corpus.md](../../docs/recherche-ingestion/axes-corpus.md)), pour chiffrer les **faux positifs** du repérage et du recoupement : des homographes de noms connus de Valmont (axe AX-R11).
**Monde :** celui de Valmont à l'état de base (`corpus/valmont-v1/valmont/world.yaml`, `edits/base.yaml`).
**Date :** 4 octobre 2026.

Un document, `p1/homographes.md`, six passages : « une brume épaisse » (brouillard) à côté des quais de Brume (la ville), « une petite brune », « une chute », « les veilleurs de nuit » (pas l'ordre des Veilleurs), « la cendre », « un loup », « une morsure » (pas la capacité Morsure), « le cercle des anciens » (pas le Cercle des Cendres), « la flamme » (pas la Flamme d'azur).

Gold : mentions seulement (aucun changement attendu), au format de Corbelle.

```powershell
worldkit --db valmont.db eval mentions --batches corpus/pieges-v1/docs/batches.yaml --oracle corpus/pieges-v1/gold --batch p1 --no-model
```

Mesuré en [X-012](../../docs/recherche-ingestion/X-012-signaler-et-pieges.md).
