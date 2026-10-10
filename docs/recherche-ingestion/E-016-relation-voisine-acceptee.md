# E-016 — Une relation voisine prise faute de mieux, et acceptée par le critique (« tient » lu comme « gouverne »)

- **Statut** : ouverte — **à traiter bien plus tard** (décision de l'auteur, 10 octobre 2026)
- **Classe** : H (le fait affirmé n'est pas celui du texte : relation voisine) ; critique : faux accord
- **Où** : Corbelle, notes de l'auteur importées dans l'atelier (`corbelle-notes-en-vrac`, reprise de `brouillon-corbelle.md`), passage 4 ; couche C5, puis le critique (C6)
- **Observé avec** : Claude Haiku 4.5 par l'API (profil `api-haiku`, substitut), prompt `facts-1`, critique v2, couche « faits » de l'atelier dans le monde de Corbelle (`corbelle.db`), 10 octobre 2026 ; observé par l'auteur à l'écran (test humain, T3) ; une passe
- **Coût en revue** : une correction, si l'auteur la voit ; sinon un **fait faux qui part** (« soutenu » ne demande aucun geste) : la page d'Ysolde dirait qu'elle gouverne l'apothicairerie, et le modèle qui lit le graphe en conclurait un pouvoir sur un lieu

## Observation

Passage : « Ysolde (la soeur) elle tient l'apothicairerie pres du pont-aux-anes. elle deteste les bateliers »

| Fait proposé | Verdict du critique | Juste ? |
|---|---|---|
| Ysolde Marcastel — **gouverne** (`rules`) — l'apothicairerie | **soutenu** | non : « tenir » une boutique n'est pas gouverner un lieu (`rules` : le bourgmestre et Corbelle, l'abbesse et Saint-Fiacre) |
| Ysolde Marcastel — habite (`lives_in`) — l'apothicairerie | mis de côté (« tenir un commerce n'implique pas y résider ») | à raison |

Attendu : aucune relation du schéma ne dit « tenir » ; soit un fait **hors schéma** (« tient », signalé à l'auteur), soit rien ; le titre « apothicaire » d'Ysolde, déjà dans l'état, porte l'essentiel. Le gold de Corbelle ne crée pas l'apothicairerie (« faute, titre seulement inféré ») : il ne mesure pas ce cas (classe G en plus).

## Explication

1. **C5 choisit dans une liste fermée** : le schéma réduit aux types présents (Character, Place) ne propose que `rules`, `lives_in`, `located_in`… Pour « tient », la plus proche est prise, plutôt que de laisser le fait de côté. Même famille qu'E-010 (relations de proximité devinées) et que le hors schéma omis d'E-007, sous une autre forme : ici le hors schéma n'est pas omis, il est **déguisé** en relation existante.
2. **Le critique juge la ressemblance, pas le sens de la relation** : ses consignes listent les motifs de `not_supported` (proximité, temps, rumeur, opinion) ; un **changement de relation** n'y est pas. Il a pourtant écarté « habite » pour le même passage : il refuse une inférence (résider), il accepte une paraphrase (diriger ≈ gouverner).
3. Les libellés passés au critique (« gouverne ») ne disent pas le domaine de la relation (pouvoir sur un lieu) : « gouverner une boutique » paraît plausible en français.

## Remèdes envisagés

1. *Mesure* : ajouter au corpus des cas « relation voisine » (tenir, diriger, s'occuper de, fréquenter) avec l'attendu hors schéma ; compter les faux accords du critique, pas seulement ses faux rejets (E-013).
2. *Déterministe* : rien de sûr sans modèle ; au mieux un signal quand le verbe de la preuve ne figure pas parmi les tournures connues de la relation (indications d'ingestion du schéma, chantier §10.5 : `rules` ← « gouverne », « règne sur », « dirige la ville »).
3. *Consigne* : au critique, un motif de plus : « la relation proposée n'est pas celle du texte (une relation voisine) » ; et une définition d'une ligne par relation (son domaine) à côté du libellé. À mesurer contre E-013 : chaque motif de rejet ajouté risque des faux rejets (X-015).
4. *Humain* : l'auteur corrige ou retire ; et, si la relation compte dans son monde, il l'ajoute au schéma (fait ici par édition de schéma : `runs`, « tient », Character, Faction → Place) — le geste « ajouter au schéma » du chantier (§6.6) le rendrait direct.
5. *Couche* : la question ciblée sans liste (« quelle relation cette phrase affirme-t-elle ? ») avant C5 sur les verbes non couverts ; coûteuse.

## Essais

Aucun (à traiter plus tard).

## Conclusion

À venir. Rapproche E-007, E-010 et E-013 : la liste fermée de C5 et un critique qui ne juge pas le sens de la relation laissent passer un fait faux marqué « soutenu », le cas le plus coûteux puisqu'il ne demande aucun geste.
