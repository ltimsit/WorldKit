# E-015 — Un fait est rattaché à un passage qui ne nomme pas ses deux entités (preuve indirecte)

- **Statut** : en cours (signalement sans décision retenu, 6 octobre 2026)
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
2. *Déterministe* :
   - ~~déplacer le fait vers un passage qui nomme ses deux entités~~ : **écarté** (remarque de l'auteur). Nommer les deux n'est pas affirmer le fait ; avec des pronoms, l'inverse est courant : « Ysolde et Jehan se croisent au marché. » (nomme les deux, n'affirme rien) / « Elle est sa sœur, mais personne ne le sait. » (affirme, par pronoms). La règle déplacerait le fait au mauvais passage, avec assurance. Savoir quel passage affirme un fait est une question de sens.
   - **signaler sans décider** (retenu) : si le passage d'une relation ne nomme pas l'une de ses entités (par leurs formes dans la source : noms, alias, mentions), pastille « preuve indirecte », et le critique juge le fait même s'il est déjà connu. Rien n'est déplacé ; l'auteur tranche.
3. *Consigne* : demander à C5, pour chaque relation, comment la preuve désigne chaque entité (« sa soeur », « Jehan Marcastell ») ; l'écran montrerait « sa soeur = Ysolde ? », que l'auteur confirme en annotant la mention. Traite la coréférence elle-même ; change le prompt de C5 : expérience payante, sur lots non vus, plus tard.
4. *Humain* : corriger le passage d'un fait dans l'atelier (geste à ajouter).
5. *Couche* : C3 (coréférence), plus tard.

## Essais

- **6 octobre 2026, signaler sans décider, rejeu sans appel** (configuration adoptée, traces d'X-013 à X-015 ; 9 lots non vus, b1 et Corbelle c1) : **6 faits gardés signalés sur 106, tous à raison** (le passage ne nomme vraiment pas l'entité) :

| Lot | Fait | Passage | Lecture |
|---|---|---|---|
| b2 | `mervin sibling_of aldren-ii` | « Son frère Mervin fut couronné… » | juste ; preuve par « son » |
| b7 | `odon rules brume` | « Odon n'est plus baron : il a perdu son titre. » | **faux** ; déjà connu, donc jamais jugé par le critique jusqu'ici |
| b1, l2 | `cendrelande located_in valmont` | « …les plaines de Cendrelande… » | juste ; Valmont non nommé |
| Corbelle | `jehan-marcastel rules corbelle` | « le bourgmestre c Jehan Marcastell… » | juste ; Corbelle non nommée |
| Corbelle | `ysolde sibling_of jehan-marcastel` | « Ysolde (la soeur)… » | le cas d'X-013 |

  Le signal ne dit pas que le fait est faux (5 sur 6 sont justes) : il dit que sa preuve tient par une coréférence ou par le contexte. Il fait juger par le critique un fait déjà connu qui ne l'était jamais (b7). Rappel inconnu par construction : un pronom dans un passage qui nomme aussi l'entité ailleurs n'est pas signalé.
- Fait dans l'atelier (couche « faits ») : pastille « preuve indirecte », entités non nommées au survol et dans le panneau, jugement du critique même pour un fait déjà connu.
