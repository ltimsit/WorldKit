# X-005 — Question ciblée sur les phrases muettes (hors schéma, E-007)

- **Statut** : conclue (première itération)
- **Hypothèse** : une phrase qui cite deux entités confirmées sans produire de fait signale une relation que C5 n'a pas su exprimer, typiquement hors schéma ; une question étroite **sans liste de relations** (« quelle relation cette phrase affirme-t-elle entre ces entités ? ») la retrouve, et s'abstient sur un fait révolu.
- **Couches et modèles** : signal sans modèle (phrases muettes) ; question ciblée, Claude Haiku 4.5 par l'API (`api-haiku`, substitut). C5 rejoué depuis X-004.
- **Écarts liés** : [E-007](E-007-hors-schema-omis.md) ; piège du Roi Gris (« régnait autrefois », E-002).

**Limite** : un seul corpus (Valmont, b1), deux phrases muettes. Exemples du prompt pris hors de Valmont.

## Protocole

- Signal, sans modèle : découper chaque passage en phrases ; garder celles qui citent au moins deux entités confirmées (par leurs formes dans le texte) et dont aucun fait de C5 ne cite la phrase en preuve.
- Question, une par phrase muette : les entités de la phrase (identifiant, type, nom), la phrase, quatre consignes ; sortie : relations proposées (sujet, identifiant anglais, objet, tournure française), ou liste vide. Un sujet ou un objet hors de la phrase est écarté.
- Mesure : celle de C5 (X-004), faits de la question ajoutés. Entités du gold et de la chaîne.
- 2 appels par variante, 0,0027 $ en tout, au plus 553 tokens par appel. Traces : `llm-log/x005-gold/`, `llm-log/x005-chain/`.

## Résultats

| Phrase muette | Réponse |
|---|---|
| notes p2 « Odon est le vassal du roi Mervin, à qui il a prêté serment à Hautval. » | `odon vassal_of mervin`, tournure « est le vassal de » |
| lieux p4 « Le Roi Gris régnait autrefois depuis Hautval, avant la Chute. » | aucune relation (fait révolu) |

| | C5 seul (X-004) | C5 et question ciblée |
|---|---|---|
| Faits : rappel (gold / chaîne) | 0,77 / 0,77 | **0,82 / 0,82** |
| Faits : précision (gold / chaîne) | 0,87 / 0,93 | 0,88 / 0,93 |
| Questions : précision / rappel | 0,88 / 0,70 | 0,89 / **0,80** |

Identique avec les entités du gold et de la chaîne (le Roi Gris y est une entité nouvelle : la phrase est muette de même, la réponse vide de même).

## Lecture

1. **E-007 est résolu sur b1** par une question étroite déclenchée sur signal, sans toucher au prompt de C5 : la liste réduite de C5 garde sa précision, la question sans liste garde la liberté du hors schéma.
2. **La tournure est rendue** (« est le vassal de ») : c'est elle qu'une décision de l'auteur gardera (ajouter au schéma, rattacher à une relation existante, ignorer ; chantier §6.6).
3. **Le piège tient** : la consigne « un fait révolu n'est pas une relation » est respectée dans une question courte, alors que l'extracteur actuel y tombait (E-002, `rules hautval`).
4. Coût marginal : deux petits appels, seulement là où le signal le demande.
5. Limites : deux phrases, une passe ; le découpage en phrases est naïf (ponctuation) ; les formes des entités viennent du gold ou de C1.
