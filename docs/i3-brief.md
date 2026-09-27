# Fiche de démarrage — Jalon I3 : saisie, banc de mécanismes, rendre réel un essai

**Cadre :** *cadre-interface.md* v0.4 — I-OBJ-02, I-OBJ-05, I-OBJ-08 ; I-PRI-04 (essai avant écriture) ; I-SAI-01 (éditeur YAML vérifié en direct) ; I-SBX-01 (rendre réel = rejouer les actions enregistrées) ; I-VUE-02 (saisie et imports), I-VUE-04 (banc de mécanismes) ; catalogue des mécanismes (§3).
**Couche de service :** I-SVC-01 à I-SVC-04 ; application web I-WEB-01 à I-WEB-03.
**Test humain :** refaire le retcon d'Aldren dans un bac à sable depuis l'interface, le vérifier, puis le rendre réel.

---

## 1. Ce que dit le cadre

- **Saisie** (I-SAI-01) : éditeur YAML, vérifié en direct par le service sans écrire (clés, lectures, écritures, collisions, signalements rattachés à `changes[i]`, diff de l'état) ; gabarits par opération, panneau des entités connues ; destination choisie : appliquer, soumettre, bac à sable.
- **Banc de mécanismes** (I-VUE-04) : un mécanisme du catalogue, une entrée, la sortie commentée avec la règle en cause.
- **Rendre réel** (I-SBX-01) : rejouer sur le monde de travail les écritures enregistrées d'un bac (et de ses bacs parents), jamais copier le fichier ; toute divergence est signalée **avant** d'appliquer.
- **Essai avant écriture** (I-PRI-04) : rien ne s'écrit dans le monde de travail sans action explicite.

## 2. Ce qui existe et se réutilise

- `edit.check` (calcul : clés, lectures, écritures, signalements, diff), `edit.apply`, `edit.submit`, `review.*`, `ingest.batch` ; bacs à sable et exécutions enregistrées avec leurs paramètres (I-SVC-04) ; `Result.stable()` pour comparer deux résultats.
- Application web en lecture ; l'API refuse aujourd'hui toute écriture.
- Mécanismes déjà exposés par le code métier mais pas encore comme opérations : validation de schéma, clés d'un changement, analyse d'une transposition, aperçu d'impact d'une redéfinition, conformité d'un état, déclaration et passages d'un document.

## 3. Points à trancher avec l'auteur (une question à la fois)

1. **Destination par défaut d'une écriture depuis l'interface** : un bac à sable, ou le monde de travail ?
2. **Rendre réel** : essai à blanc sur une copie fraîche du monde puis application, ou application directe arrêtée à la première divergence ; tout ou partie des écritures du bac.
3. **Forme du banc de mécanismes** : une console générique (toute opération du registre, paramètres en YAML pré-remplis) complétée d'opérations de calcul nouvelles, ou des écrans dédiés par mécanisme.

## 4. Définition de « fini »

- Éditeur d'édition YAML vérifié en direct ; appliquer ou soumettre vers la destination choisie ; gabarits et entités connues.
- Banc de mécanismes : au moins validation de schéma, clés, vérification d'une édition, analyse de transposition, aperçu d'impact, conformité, déclaration d'un document.
- `sandbox.promote` : rejouer les écritures d'un bac sur le monde de travail, divergences signalées avant d'appliquer ; accessible en ligne de commande et dans l'interface.
- Tests : T1 (une promotion refusée n'écrit rien ; une promotion acceptée donne dans le monde le même état que dans le bac quand rien n'a divergé) ; pages et API d'écriture ; guide PowerShell et test humain ; documents mis à jour.
