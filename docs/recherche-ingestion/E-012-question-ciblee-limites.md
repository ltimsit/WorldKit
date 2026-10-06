# E-012 — Limites de la question ciblée : synonymes, phrases non muettes

- **Statut** : en grande partie résolue (X-008, X-010) ; reste le jugement vague (`conspires_with`)
- **Classe** : conception (hors schéma)
- **Où** : Corbelle c1, `la-sorgue` p3, `brouillon-corbelle` p4 et p6 ; question ciblée (X-005)
- **Observé avec** : Claude Haiku 4.5, 4 octobre 2026 ([X-006](X-006-corbelle-chaine.md)) ; une passe
- **Coût en revue** : une fausse proposition d'extension de schéma (`mother_of`) ; un hors schéma perdu (`hates`)

## Observation

1. **Synonyme d'une relation existante** : « mère agathe c la mère d'Ostrel » donne `agathe mother_of ostrel` (« est la mère de »), alors que `parent_of` existe. Sans liste, la question invente un nom pour une relation que le schéma connaît.
2. **Hors schéma perdu dans une phrase non muette** : « elle tient l'apothicairerie pres du pont-aux-anes. elle deteste les bateliers » a produit `lives_in` (E-010), donc la phrase n'est pas muette et `hates` n'est jamais demandé.
3. **Jugement vague proposé comme relation** : « il magouille avec l'abbesse » donne `schemes_with` (le gold n'attend rien).

## Remèdes envisagés

2. *Déterministe* : le signal par **paire d'entités** plutôt que par phrase (une phrase qui cite deux entités sans fait **entre elles**) ; une relation proposée dont la tournure ressemble au libellé d'une relation existante (« mère de » / « parent de ») est rattachée à celle-ci (indications d'ingestion, §10.5).
3. *Consigne* : donner à la question la liste des relations compatibles **comme préférence** (« si l'une convient, utilise-la ; sinon propose un identifiant »). Risque : retrouver le cadrage d'E-007 ; à mesurer sur Valmont et Corbelle.
4. *Humain* : les trois issues du §6.6 (rattacher `mother_of` à `parent_of` une fois ; la tournure guide ensuite).

## Essais

- **4 octobre 2026, [X-008](X-008-consignes-et-question.md)** : relations connues données comme préférence et signal par paire d'entités non reliées, à l'échelle du passage. `mother_of` devient `parent_of` ; « elle deteste les bateliers » est trouvé ; rappel des faits de Corbelle 0,50 → 0,92, sans régression sur les questions de Valmont. Reste : la question ignore l'attribution (`vouivre haunts corbelle` tiré d'une rumeur) et propose des jugements vagues (`conspires_with`).
- **4 octobre 2026, [X-009](X-009-critique.md)** : la rumeur `vouivre haunts corbelle` est mise de côté par le critique (« ouï-dire ») ; `conspires_with` reste (incertain).
- **4 octobre 2026, [X-010](X-010-enonciation.md)** : l'énonciation sans modèle retient les faits de la phrase de rumeur avant le critique (`vouivre haunts corbelle`).
