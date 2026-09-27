# Fiche de démarrage — Jalon I6 : graphe, mesures T2 et leur historique

**Cadre :** *cadre-interface.md* v0.7 — I-OBJ-04, I-OBJ-07 ; I-GRA-01 (graphe : voisinage, couches, style d'état, comparaison, table) ; I-VUE-06 (graphe), I-VUE-09 (mesures) ; I-LLM-01 et I-PPL-02 (coût, tâches de fond) ; I-TEC-01 (Cytoscape.js, copié dans le projet).
**Règles concernées :** R-NOT-03, R-NOT-04, R-NOT-07 (notoriété, faits masqués), R-VUE-03 (redéfini plus tard), R-FAI-06 (orphelins), R-IDT-04 (doublons), R-MET-02, R-MET-04 (fiches, contreparties), R-DOC-06 (affirmations) ; T-ING-19, T-TST-01 (mesure T2).
**Test humain :** choix du modèle sur le second jet du corpus (à venir) ; d'ici là, lire le graphe de Valmont et comparer `reference` et `reference-r1` après le retcon.

---

## 1. Ce que dit le cadre

- **Graphe** (I-GRA-01) : voisinage d'une entité par défaut (profondeur réglable), vue complète à un clic ; couches (monde, éléments de système, fiches avec `has_sheet` et `conforms_to` calculées, contreparties, identités, affirmations, documents) ; style qui encode notoriété, fait masqué, redéfini plus tard, orphelin, entité close ; survol : identifiant, clé, provenance ; mode comparaison de deux états ; table des éléments affichés. Les données viennent du service (branche, point, filtre) : l'interface dispose le dessin, rien d'autre (I-PRI-02).
- **Mesures** (I-VUE-09) : mesures T2 par lot, par opération, pièges, stabilité ; historique ; comparaison de modèles ou de prompts. Une mesure avec un modèle obéit au contrôle du coût (I-LLM-01) et tourne en tâche de fond (I-PPL-02).

## 2. Ce qui existe et se réutilise

- Vues : `View`, `export_graph` (entités, relations, fiches, identités, affirmations filtrées), `wiki.compare` (diff au niveau des faits), notoriété effective, faits masqués, `redefined_after`, orphelins.
- Mesure T2 : `worldkit/periphery/evaluation.py` (`evaluate`, rapport par passage, `summary`), commande `worldkit eval extraction` ; extracteurs oracle et LLM, cache, `CachedExtractor`.
- Service : exécutions enregistrées, tâches de fond, estimation et plafond d'appels.

## 3. Points à trancher avec l'auteur (une question à la fois)

1. **Ce qu'est un nœud** : les attributs restent-ils dans un panneau (clic, survol) ou deviennent-ils des nœuds satellites ?
2. **Mesures T2 dans l'interface** : tableaux seulement, ou aussi de petits graphiques d'évolution ; et ce qu'on compare (deux mesures quelconques, ou par extracteur et version de prompt).

## 4. Définition de « fini »

- Opérations `graph.view` (voisinage ou complet, couches, style d'état, filtre) et `graph.compare` (deux états, ajouts, retraits, changements) ; écran Graphe avec Cytoscape.js, panneau de détail, table des éléments affichés.
- Opérations `eval.run` (tâche de fond, coût contrôlé) et `eval.history` / `eval.compare` ; écran Mesures ; `worldkit eval extraction` passe par le service.
- Tests : aucun secret dans le graphe joueur (T1), comparaison du retcon, mesure oracle contre oracle parfaite, historique ; aucun vrai modèle.
- Guide PowerShell ; documents (cadre d'interface, analyse, CLAUDE.md).
