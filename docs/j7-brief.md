# Fiche de démarrage — Jalon J7 : redéfinition rétroactive (rejeu)

**Modules :** M2 (branches), M4 (conflits, transposition), M5 (pistes), M9 (propositions en attente).
**Règles :** R-RED-01 à R-RED-05, R-HIS-01, R-HIS-03, R-HIS-04, R-HIS-05, R-MON-02, R-VUE-03, R-CYC-01, T-ING-16 ; cadre de la fondation §6.4 (diagramme du rejeu).
**Test d'acceptation :** parcours W15 de `corpus/valmont-v1/valmont/walkthroughs/walkthroughs.yaml` (« Aldren est mort de fièvre »).
**Test humain (cadre technique §7) :** « Retcon de la mort d'Aldren ».

---

## 1. Ce que dit le cadre

| | Ponctuelle (fait en J5) | Rétroactive (J7) |
|---|---|---|
| Sens | « À partir de maintenant » | « Depuis toujours » (ou depuis un état choisi) |
| Mécanisme | Édition étiquetée ajoutée à la branche | **Nouvelle branche + rejeu** |
| Vues antérieures | Signalent « redéfini plus tard » | Reflètent la redéfinition |

- R-RED-01 : le mode est choisi explicitement, après un **aperçu d'impact** (nombre d'éditions ultérieures concernées).
- R-RED-02 : le rejeu est **suspendable, reprenable et abandonnable**.
- R-RED-03 : après rejeu, les pistes en attente concernées passent **à revérifier**.
- R-RED-04 : les variantes dérivées de l'ancienne branche sont **notifiées**, pas modifiées.
- R-RED-05 : mêmes modes pour les modifications de schéma et de systèmes.
- §6.4 : la nouvelle branche devient la branche de référence, l'ancienne est archivée (consultable, R-HIS-04). L'historique ne fait que s'allonger (R-HIS-01) : rien n'est réécrit, on bifurque.

## 2. Ce qui existe déjà et se réutilise

- **Branches** (`World.create_branch`, lignée dans `Store.segments`) : la nouvelle branche part de l'ancrage (`anchor_after: e003` → rang de e003).
- **Transposition** (`worldkit/core/conflicts/transposition.py`, `World.transpose`) : rejouer = transposer, **dans l'ordre**, chaque édition postérieure à l'ancrage sur la nouvelle branche. L'analyse (indépendante / dépendante / contradictoire) et les décisions (garder, adapter, écarter) sont déjà là.
- **Éditions en attente** : `needs_recheck`, `World.rebase` ; propositions et pistes : file de revue (`worldkit/ingest/queue.py`), déplacement `decide.move` (T-ING-16) ; pistes d'auteur `worldkit/core/workflows/scenarios.py`.
- **Branche de référence** : aujourd'hui dans la déclaration du monde (`WorldDeclaration.reference_branch`, table `world`), non versionnée ; `branches.status` existe (`active`).

## 3. Points à trancher avec l'auteur (une question à la fois)

1. **Persistance du rejeu (R-RED-02)** : une « session de rejeu » stockée (branche en cours, prochaine édition, décisions prises), reprise par `worldkit replay resume` ; ou un rejeu non interactif qui s'arrête au premier conflit et se relance.
2. **Ce que lit une qualification d'affirmation.** W15 attend que la qualification « mort au combat : fausse » (W06) soit comptée dans l'aperçu d'impact et présentée à l'humain. Aujourd'hui `qualify_claim` n'écrit que `(qualification, claim)` et ne lit rien : il faudrait qu'elle **lise la clé du changement revendiqué** (`(aldren-ii, death_cause)`), puisque la qualification en dépend. Touche T-ING-02 / T-ING-12.
3. **Basculer la branche de référence (R-MON-02)** : édition du monde, ou simple changement de déclaration tracé ? Que deviennent les points nommés (`@base`…), les propositions en attente (déplacées vers la nouvelle branche comme T-ING-16 ?) et les déroulés ?
4. **Notifier une variante (R-RED-04)** : un signalement dans `worldkit check` sur la variante (« sa parente a été archivée »), sans rien modifier.

## 4. Attendus de W15

- Aperçu d'impact avant confirmation : les éditions ultérieures qui lisent `(aldren-ii, death_cause)` ou `(killed, aldren-ii)` sont comptées (dont la qualification de W06).
- Rejeu : les autres éditions passent sans intervention ; la qualification de W06 est présentée à l'humain, qui la garde.
- La piste ad-2 (retirer le meurtre) passe à revérifier ; ad-1 non concernée.
- La nouvelle branche devient la branche de référence ; l'ancienne est archivée et consultable.
- La variante `variante-mj` est notifiée, pas modifiée.
- Vues antérieures de la nouvelle branche : Aldren mort de fièvre depuis l'ancrage.

## 5. Définition de « fini »

- `pytest` vert (T1 : rejeu déterministe ; ancienne branche identique avant et après ; éditions indépendantes rejouées sans intervention) ; W15 passe.
- Documents mis à jour selon CLAUDE.md (cadre technique, analyse 00.xx + question, CLAUDE.md), choix non validés listés dans la réponse.
