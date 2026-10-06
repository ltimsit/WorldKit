# X-010 — Énonciation sans modèle (C4) : rumeur → attribution, note de travail → silence

- **Statut** : conclue (première itération)
- **Hypothèse** : des marqueurs généraux, sans modèle, suffisent à reconnaître une rumeur ou des paroles rapportées (« on dit que », « les vieux disent », guillemets) et une note de travail de l'auteur (« TODO : », « idée : », « et si … ? ») ; en retenir les faits et les entités nouvelles améliore la précision sans rien perdre.
- **Couches** : C4 (énonciation, déterministe), placée après la question ciblée et avant le critique ; et dans C2 (aucune entité nouvelle tirée d'une note). **Aucun appel** : tout est remesuré par rejeu.
- **Cadre** : voie choisie par l'auteur : **s'adapter au cadre**. Une rumeur donne une **attribution sans fait** (R-DEC-03) ; croyances et rumeurs restent **hors périmètre** (cadre de la fondation §1.4). La voie inverse (rumeurs en affirmations attribuées, qualifiables) est une question ouverte du chantier.
- **Écarts liés** : E-012 (rumeur prise pour un fait par la question ciblée), E-008 (« fête des lanternes »), question 10 du chantier (note de travail).

## Protocole

- `enunciation(texte)` : « note » si la phrase commence par un marqueur de note (`TODO`, `idée`, `note`, `NB`, `à voir`, `à creuser`, suivis de « : » ou « ! ») ou contient « et si … ? » ; « attribution » si elle contient un marqueur de ouï-dire ou des guillemets ; sinon rien.
- Faits (C5 et question ciblée) : la phrase qui porte la preuve est classée ; un fait d'une phrase « attribution » ou « note » est **retenu** (visible, pas proposé).
- Mentions (C2) : une entité **nouvelle** tirée d'un passage de note n'est pas proposée ; les entités connues restent mentionnées.
- Mesure : passages classés contre le gold (`outcome: attribution`, `silent`).

## Résultats (rejeu)

| | Attendu (gold) | Trouvé |
|---|---|---|
| Passages d'attribution | Valmont notes p6 ; Corbelle la-sorgue p1 | les mêmes, rien d'autre |
| Passages de note | Corbelle brouillon p3 (TODO), p8 (idée), p9 (hors sujet) | p3, p8 ; p9 (« acheter des dés ») non reconnu, sans effet (rien n'en est tiré) |

| Faits, entités du gold : précision / rappel | Corbelle | Corbelle, questions | Valmont |
|---|---|---|---|
| X-008 (sans énonciation, sans critique) | 0,44 / 0,92 | 0,43 / 1,0 | 0,82 / 0,82 |
| avec énonciation | 0,50 / 0,92 | 0,50 / 1,0 | 0,82 / 0,82 |
| avec énonciation et critique v2 | **0,59 / 0,83** | **0,71 / 0,83** | 0,82 / 0,82 |

Faits retenus sur Corbelle : `vouivre haunts corbelle`, `vouivre haunts la-sorgue` (support), `la-sorgue located_in corbelle`, tous tirés de la phrase de rumeur. Mentions : fausses créations de Corbelle 3 → **2** (« fête des lanternes » n'est plus proposée) ; Valmont inchangé.

## Lecture

1. **Sans modèle et sans perte** : les deux rumeurs du gold sont trouvées, aucun faux positif sur les deux corpus ; le rappel ne bouge pas.
2. **Énonciation et critique se complètent** : l'énonciation retient tôt et gratuitement ce que le critique attrapait au cas par cas (la rumeur), le critique garde ce qu'aucun marqueur ne signale (proximité, temps).
3. **Limites** : marqueurs français généraux, à éprouver sur d'autres façons d'écrire (« d'après X », dialogue, discours indirect sans marqueur) ; une phrase longue et sans ponctuation qui contient une rumeur retient tout ce qu'elle porte ; le hors sujet (« acheter des dés ») n'est pas reconnu (il n'a rien produit ici) ; deux corpus écrits par Claude.
