# E-003 — « le conseil des marchands » pris pour une valeur, jamais créé comme entité

- **Statut** : résolue sur b1 (chaîne C1, C2, C5)
- **Classe** : N (granularité : une entité traitée comme une valeur)
- **Où** : b1, `notes-baron` v1 p3 et p4, `lieux-de-valmont` p2 ; extraction monolithique (futures couches C1 et C5)
- **Observé avec** : Claude Haiku 4.5, `api-haiku`, prompt version 3, 4 octobre 2026 ; première passe ([X-001](X-001-b1-haiku-reference.md)) ; même forme sur la troisième extraction (2 sur 3) ; la deuxième différait sur p3 et p4, sans que son contenu soit conservé. Non observé sous Sonnet 5.
- **Coût en revue** : fort. Deux fausses valeurs à refuser (`brume.ruler`, hors schéma ; `odon.title = membre du conseil des marchands`), puis l'entité, son nom et quatre relations à saisir à la main.

## Observation

| Passage | Texte | Sortie | Attendu |
|---|---|---|---|
| notes p3 | « Dans les faits, c'est le conseil des marchands qui gouverne Brume : le baron ne signe que ce qu'on lui tend. » | `brume.ruler = "conseil des marchands"` | créer `new:conseil-marchands` (Faction), son nom, `rules → brume` |
| notes p4 | « Odon siège lui-même au conseil des marchands, dont les séances se tiennent à Brume. » | `odon.title = "membre du conseil des marchands"` | `odon member_of conseil`, `conseil based_in brume` |
| lieux p2 | « Hautval, la capitale, domine la vallée. Le conseil des marchands y tient ses séances. » | `hautval.category = capitale` seulement | en plus : `conseil based_in hautval` |

Le même nom apparaît dans trois passages et n'est reconnu comme entité dans aucun.

## Explication

1. **Créer une entité est une tâche à plusieurs pas** (règle 3 : `create_entity` avec un type, `set_attribute name`, puis réutiliser l'étiquette `new:…` dans les relations). Plus court, le modèle écrit le nom comme valeur d'un attribut, qu'il invente au besoin (`ruler`).
2. **Rien ne signale au modèle que c'est une entité** : « conseil des marchands » n'est pas un nom propre (pas de majuscule), et il n'est pas dans la liste des entités connues (`base.yaml` ne le crée pas, à dessein).
3. **Chaque passage est extrait seul** : la décision « c'est une entité » n'est pas partagée entre les trois passages ; l'erreur se répète.

## Remèdes envisagés

1. *Mesure* : aucun ; l'écart coûte réellement.
2. *Déterministe* :
   - garde du noyau sur les attributs : `Place.ruler` est hors schéma et signalé (T-ING-13). Une valeur hors schéma dont le texte nomme une entité possible pourrait être marquée « entité probable » (à étudier : c'est une heuristique) ;
   - indication de schéma sur `Faction` : exemples (« conseil », « guilde », « ordre ») et relation typique « gouverne » → `rules` (chantier §10.5).
3. *Consigne* : exemple dans le prompt (« le conseil des marchands gouverne Brume » → création et relation). À mesurer : une règle de plus dans un prompt déjà trop long (voir E-004, E-005).
4. *Humain* : l'auteur annote « conseil des marchands » comme mention de Faction une fois (source ou passage) ; à la relance, C5 reçoit l'entité donnée. Une seule annotation corrigerait les trois passages.
5. *Couche* : **C1 mentions**, qui ne fait que repérer et typer les mentions (« conseil des marchands » : Faction, nouvelle), puis C5 à entités données. Hypothèse : séparer « qu'est-ce qui est une entité » de « que dit le passage » supprime l'écart. C'est le test naturel de la première couche.

## Essais

- **4 octobre 2026, X-002** : C1 sur le document entier, une seule question, sans liste des entités connues (Haiku 4.5). Le conseil des marchands est repéré dans les trois passages, typé Faction, et recoupé comme une seule entité nouvelle pour le lot. Stable sur deux extractions. L'écart disparaît **au niveau des entités** ; il reste à vérifier que C5, à entités données, produit les relations attendues (`rules`, `member_of`, `based_in`).
- **4 octobre 2026, X-004** : C5 à entités données extrait les quatre relations attendues : le conseil gouverne Brume (p3), Odon en est membre (p4), il siège à Brume (p4) et à Hautval (lieux p2). Même résultat avec les entités du gold et celles de la chaîne. Une passe.

## Conclusion

Résolu sur b1 par l'architecture (fenêtre au document, une question par couche), sans indication de schéma ni annotation. Limites : un seul corpus, une passe pour C5. Premier témoin de [X-002](X-002-c1-c2-fenetre.md) : C1 sur le document entier, sans liste connue, voit le conseil trois fois dans la même fenêtre. Ensuite, avec et sans pré-annotation (rendement d'une annotation, chantier §9).
