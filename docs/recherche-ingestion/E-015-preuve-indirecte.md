# E-015 — Un fait est rattaché à un passage qui ne nomme pas ses deux entités (preuve indirecte)

- **Statut** : ouverte
- **Classe** : R (résolution : coréférence au-delà du passage) ; provenance (T-ING-11)
- **Où** : Corbelle c1, `brouillon-corbelle` p2, p4, p5 ; couche C5 (fenêtre au document entier)
- **Observé avec** : Claude Haiku 4.5 par l'API, atelier (couche « faits », I9), 6 octobre 2026, observé par l'auteur à l'écran ; déjà vu dans les mesures d'X-013 (« sœur » relevé en p4 au lieu de p5, 7 passes sur 7)
- **Coût en revue** : une provenance trompeuse (le fait renvoie à un passage qui ne le dit pas) ; dans la mesure, un fait compté deux fois (en trop au mauvais passage, manqué au bon)

## Observation

| Passage | Texte | Ce que C5 en tire |
|---|---|---|
| p2 | « le bourgmestre c Jehan Marcastell, un type mou, tout le monde sait que c sa soeur qui decide » | `ysolde-marcastel sibling_of jehan-marcastel`, preuve « tout le monde sait que c sa soeur qui decide » (atelier) |
| p4 | « Ysolde (la soeur) elle tient l'apothicairerie pres du pont-aux-anes. » | le même fait (X-013, toutes les passes) |
| p5 | « Ysolde = soeur de jehan (le bourgmestre pas le passeur!!) » | (attendu par le gold : c'est le seul passage qui nomme les deux) |

L'auteur : « c'est techniquement sur p5 que je devrais savoir que Ysolde est sa sœur ; p2 devrait plutôt servir à décrire Jehan Marcastel ».

Le fait étant déjà dans l'état (un support), le critique ne l'a pas jugé. Un défaut de l'atelier aggravait le cas : la couche ne gardait qu'une occurrence d'un même fait (la première, p2), et aurait jeté une preuve en p5 si C5 en avait donné une. Corrigé le 6 octobre (une annotation par fait et par passage).

## Explication

C5 lit le document entier (« une fenêtre large, une question étroite », chantier §6.5) : il sait, par p4 et p5, que « sa soeur » en p2 désigne Ysolde, et cite la première phrase qui en parle. La preuve est **indirecte** : elle ne tient que par une coréférence (« sa soeur », « la soeur ») que rien ne résout explicitement (C3 n'existe pas). La fenêtre large aide à trouver le fait ; elle brouille le choix de sa preuve.

## Remèdes envisagés

1. *Mesure* : le gold place le fait en p5 ; rien à corriger.
2. *Déterministe* (candidat) : une relation doit avoir une preuve qui **nomme ses deux entités** (par leurs formes dans la source : noms, alias, mentions de la couche « mentions »). Si le passage de la preuve n'en nomme qu'une (p2 : « Jehan Marcastell » seulement), chercher dans le document un passage qui nomme les deux (p5 : « Ysolde », « jehan ») et y **déplacer** le fait ; s'il n'y en a pas, le garder avec une pastille « preuve indirecte », et le soumettre au critique même s'il est déjà connu. Sans modèle, mesurable gratuitement par rejeu des traces d'X-013 à X-016.
3. *Consigne* : « evidence : la phrase qui nomme les deux entités ». Coûte des tokens, effet incertain sur un petit modèle (X-008 : les consignes d'écriture rendent peu).
4. *Humain* : corriger le passage d'un fait dans l'atelier (geste à ajouter).
5. *Couche* : C3 (coréférence), plus tard.

## Essais

Aucun.
