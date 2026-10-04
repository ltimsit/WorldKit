# Corpus Corbelle — notes brouillon (v1)

**Sorte :** corpus **ciblé**, écrit par Claude (voir [axes-corpus.md](../../docs/recherche-ingestion/axes-corpus.md)). Il imite des notes prises à la va-vite ; ce n'est pas un vrai corpus d'auteur. Ses mesures servent à **construire et éprouver les couches** (C1, C2, C5, question ciblée), **pas à choisir un modèle** (T-TST-01) : un texte écrit par un modèle est plus facile à lire pour un modèle de la même famille, et son désordre est plus régulier que celui de vraies notes.
**Date :** 4 octobre 2026.

## Le monde en bref

**Corbelle** est une petite ville au bord de **la Sorgue**, une rivière hantée, dit-on, par **la Vouivre**. Le bourgmestre **Jehan Marcastel** est mou ; sa sœur **Ysolde**, apothicaire près du **Pont-aux-Ânes**, décide à sa place. La **Guilde des Bateliers** tient le port ; **Jehan Leblond**, ancien passeur, y travaille depuis **la Grande Crue**. **Mère Agathe** dirige **l'abbaye Saint-Fiacre**. L'ingestion fait apparaître **Bertrand Ostrel**, maître de la guilde (et, en secret, fils de Mère Agathe), et **Clémence**, épouse du bourgmestre.

## Contenu

```
corbelle-v1/
├── README.md
└── corbelle/
    ├── world.yaml          déclaration du monde (aucun système de règles)
    ├── schema.yaml         copie du schéma par défaut, plus lives_in ; hates volontairement absent
    ├── edits/base.yaml     état de base (e001 à e003)
    ├── docs/c1/            3 documents, 13 passages, lot c1
    ├── docs/batches.yaml
    └── gold/               mentions et changements attendus, passage par passage
```

## Axes couverts

| Document | Passages | Axes |
|---|---|---|
| `brouillon-corbelle` | 9 | AX-S1 à S5, S7, S8 ; AX-T2 ; AX-E1 à E5, E9 ; AX-R1, R2, R4, R10 ; AX-D1, D2, D4 ; AX-M3 |
| `la-sorgue` | 3 | AX-S4, S6, S7 ; AX-E1, E7, E8 ; AX-R1, R5, R6 ; AX-C3 |
| `persos` | 1 (liste) | AX-T1, T2 ; AX-S1, S2, S5 ; AX-R1, R3 ; AX-D2 ; AX-E1 ; AX-C3 |

Pièges notables :
- « Marcastell » (faute sur un nom connu) ;
- « Bertrand Ostrell » (faute sur une entité **nouvelle**, créée dans un autre document) ;
- deux « Jehan » ;
- « ~~la vouivre~~ » (correction barrée) ;
- un passage « TODO », un passage hors sujet, une idée d'intrigue, qui ne doivent rien produire ;
- « mère agathe c la mère d'Ostrel » (titre, puis lien de parenté secret) ;
- `hates` hors schéma.

## Format du gold

Celui de Valmont (README de `valmont-v1`, §3), avec trois différences :

- **pas d'`outcome`** sur les changements : ce corpus mesure les couches (`worldkit eval mentions`, `worldkit eval facts`, et `worldkit eval extraction` pour l'extracteur actuel), pas la qualification du noyau ;
- **`test_axes`** : les axes éprouvés par le passage ;
- **`silent`** : le passage ne doit produire ni fait ni entité nouvelle (`author_note`, `off_topic`, `plot_idea`). C'est une extension demandée par AX-E1 et AX-E2 ; le cadre n'a pas encore de nature pour une note de travail de l'auteur (chantier §14).

## Mesurer

```powershell
worldkit --db corbelle.db world init corpus/corbelle-v1/corbelle/world.yaml
worldkit --db corbelle.db edit apply corpus/corbelle-v1/corbelle/edits/base.yaml
worldkit --db corbelle.db eval mentions --batches corpus/corbelle-v1/corbelle/docs/batches.yaml --oracle corpus/corbelle-v1/corbelle/gold --batch c1 --no-model
```

La cohérence du corpus est vérifiée par `tests/test_corpus_corbelle.py` (identifiants, types, attributs et relations du schéma, hors schéma déclaré).
