# Fiche de démarrage — Jalon I2 : application web, lecture

**Cadre :** *cadre-interface.md* v0.3 — I-OBJ-06, I-OBJ-07 ; I-PRI-01 à I-PRI-03 ; I-TEC-01 (FastAPI, HTML rendu par le serveur, htmx, Mermaid) ; I-INC-01 (service et lecture d'abord) ; espaces I-VUE-01 (tableau de bord), I-VUE-07 (wiki), I-VUE-08 (branches et historique) ; forme commune d'un retour (§7).
**Couche de service :** I-SVC-01 à I-SVC-04 — l'application appelle `Session.call`, rien d'autre.
**Test humain :** relire le retcon d'Aldren entre `reference` (archivée) et `reference-r1`, dans le wiki et l'historique.

---

## 1. Ce que dit le cadre

- **Web local** : une API FastAPI qui expose le registre d'opérations en JSON ; des pages HTML rendues par le serveur, rendues interactives par htmx ; Mermaid pour dessiner les branches ; bibliothèques JS copiées dans le projet, pas de Node, fonctionne hors ligne (I-TEC-01).
- **Clarté avant beauté** : tables denses, identifiants visibles, texte brut accessible, le maximum de réponse rendue (I-PRI-01).
- **Aucune logique métier dans l'interface** : chaque écran est le rendu d'un ou plusieurs `Result` du service ; les filtres de vue (auteur ou joueur, branche, point) sont des paramètres d'opération, jamais des filtres JavaScript (I-PRI-02).
- **Traçable** : chaque écran peut montrer l'appel qui l'a produit et le résultat JSON brut (I-PRI-03, I-OBJ-06).
- I2 est en **lecture seule** : aucune écriture depuis l'interface avant I3.

## 2. Ce qui existe et se réutilise

- Opérations de consultation d'I1 : `world.summary`, `branch.list`, `journal.list`, `edit.show`, `wiki.page`, `wiki.index`, `state.check`, `export.graph`, `review.list`, `sandbox.list`, `runs.list`, `runs.show`, `ops.list`.
- Rendu Markdown d'une page (`render_page`), historique des références, statuts des branches, points nommés, signalements de lignée (R-RED-04).

## 3. Points à trancher avec l'auteur (une question à la fois)

1. **Contexte de lecture** : où vivent la cible (monde ou bac), la branche, le point et le filtre — dans l'adresse de chaque page (partageable, reproductible) ou dans une préférence de session ?
2. **Comparaison** : comment comparer deux lectures (auteur et joueur ; `reference` et `reference-r1` ; deux points) — deux colonnes à contextes indépendants, ou un mode « diff » calculé ?
3. **Lancement** : commande `worldkit serve` (port, ouverture du navigateur, écoute locale seulement) et arrêt.
4. **Mise en forme** : feuille de style écrite pour le projet, ou petite feuille « sans classes » copiée ; rendu du Markdown des pages (HTML ou texte brut à côté).

## 4. Définition de « fini »

- `worldkit serve --db monde.db` ouvre une application locale : tableau de bord (compteurs, branches, signalements, bacs, dernières exécutions), wiki (index et pages, auteur et joueur), branches et historique (lignée dessinée, journal, points, historique des références, éditions), exécutions (liste et résultat brut).
- Chaque écran montre l'opération appelée, ses paramètres et un lien vers le JSON brut ; l'API JSON répond pour toute opération de consultation.
- Tests automatiques : toutes les pages répondent sur Valmont (client de test FastAPI), aucune écriture possible, le contenu joueur ne montre aucun secret.
- Guide PowerShell vérifié ; test humain du retcon d'Aldren ; documents mis à jour.
