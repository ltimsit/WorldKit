# E-009 — Un texte barré est lu comme une mention

- **Statut** : résolue sur Corbelle (déterministe)
- **Classe** : énonciation (AX-E4, correction de l'auteur)
- **Où** : Corbelle c1, `brouillon-corbelle` p6 ; couche C1a (et C5, qui voit le texte)
- **Observé avec** : C1a déterministe, 4 octobre 2026 ([X-006](X-006-corbelle-chaine.md)) ; la question ciblée a, elle, ignoré la mention barrée
- **Coût en revue** : une mention en trop ; un fait faux si C5 s'y appuie

## Observation

« il magouille avec ~~la vouivre~~ non avec l'abbesse en fait » : C1a trouve « la vouivre » (nom connu) dans le passage barré.

## Remèdes envisagés

2. *Déterministe* : C0 marque les portions barrées (`~~…~~`) ; C1a ne cherche pas dedans ; le texte envoyé au modèle les garde (le contexte « non… en fait » aide) ou les retire (à mesurer). Le gold de Corbelle porte déjà `must_not` sur la Vouivre en p6.

## Essais

- **4 octobre 2026, [X-007](X-007-recoupement-par-score.md)** : la fenêtre repère `~~…~~` ; C1a n'y cherche pas ; une mention du modèle seulement barrée est écartée. « la vouivre » n'est plus trouvée en p6.
