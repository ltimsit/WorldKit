# X-019 — Premier modèle local : qwen3:4b (Ollama) sur b1

- **Statut** : conclue (premier point de mesure d'un vrai petit modèle ; une passe)
- **Hypothèse** : le chantier vise de petits modèles et Haiku 4.5 n'en est qu'un substitut, plus capable (§8.2, point 5). Un modèle local réel dit ce que vaut l'orientation « fenêtre large, question étroite » : l'extracteur actuel (une seule grande question) devrait s'effondrer, la couche « faits » (C5, entités confirmées) devrait mieux tenir.
- **Couche et modèle** : extracteur actuel (`llm-3`) et couche « faits » (`facts-1`, entités du gold) ; **qwen3:4b** par Ollama sur la machine de l'auteur, sans carte graphique (profil d'exemple `qwen3-4b` : `num_ctx` 16 384, réflexion coupée, température 0, `concurrency: 1`).
- **Données** : lot b1 de Valmont v1 (12 passages : `notes-baron` v1, `lieux-de-valmont`), monde neuf ; 13 octobre 2026. Traces : `llm-log/x019-extraction/`, `llm-log/x019-facts/`.

**Limites** : une passe ; corpus synthétique et optimiste (T-TST-01) ; 4 milliards de paramètres, en dessous de la cible de 7 à 8 milliards (§8.1) ; la machine de l'auteur, pas un serveur.

## Indicateurs

| | qwen3:4b (local) | Haiku 4.5 (substitut) |
|---|---|---|
| **Extracteur actuel** : précision / rappel | **0,14 / 0,14** | 0,65 / 0,59 (X-001) |
| questions : précision / rappel | 0,11 / 0,13 | 0,50 / 0,47 (X-001) |
| créations d'entités trouvées | 0 sur 2 | 0 sur 2 (E-003) |
| appels, durée | 12, 896 s (75 s par appel) | 12, 21,6 s |
| tokens en entrée, au plus par appel | 1 766 | 3 538 |
| **Couche « faits »** (entités du gold) : précision / rappel | **0,56 / 0,29** (5 vp, 4 fp, 12 fn) | 0,93 / 0,82 (E-005, par rejeu) |
| questions : précision / rappel | 0,60 / 0,30 | 0,88 / 0,70 (X-004) |
| écartés par les contrôles de types | 3 | — |
| appels, durée | 2, 181 s | 2 |
| coût | 0 | quelques millièmes de dollar |

## Écarts observés

**Extracteur actuel.** Il s'effondre, comme attendu.

1. **Forme des changements.** Une liste traitée comme un champ simple : `set_attribute aliases` au lieu de `add_value`, trois fois. Le nom et les alias sont réécrits avec l'identifiant (`mervin.name = mervin`, `odon.aliases = odon-de-brume`).
2. **Titres avec leur complément** (E-005) : « baron de brume », « régent de brume », « roi gris ». La règle sans modèle du choix 42 n'est appliquée que dans la couche « faits ».
3. **Phrases recopiées comme valeurs.** `odon.condition = « gouverne la cité portuaire depuis la chute »`.
4. **Aucune entité créée** : E-003, au complet.
5. **Relations inventées ou mal orientées.** `swore_allegiance`, hors schéma ; `cendrelande located_in brume`.

**Couche « faits ».** Elle tient mieux : précision quatre fois plus haute. Le schéma de sortie réduit, les entités confirmées et les contrôles déterministes portent l'essentiel.

1. **Trois faits écartés par les contrôles de types**, dont `hautval rules valmont` : le garde-fou sans modèle fait son travail.
2. **Une relation voisine inventée** : « vassal du roi Mervin » devient `spouse_of`, dans les deux sens. La relation manque au schéma (le gold attend « hors schéma ») et le petit modèle prend la plus proche. C'est le cas d'E-016 (une relation voisine acceptée), en plus grossier.
3. **Rappel faible sur les attributs** : 7 des 12 manqués sont des attributs (`title`, `category`, `aliases`). Le modèle répond surtout par des relations.
4. **Deux faits déjà connus redits** (`odon rules brume`, `aldren-ii involved_in la-chute`) : ce sont des supports, sans dommage.

## Lecture

- **L'orientation du chantier est confirmée sur un vrai petit modèle.** La même machine donne 0,14 en précision avec la grande question et 0,56 avec la question étroite. L'écart entre Haiku et qwen3:4b est bien plus grand sur l'extracteur (0,51 point de précision) que sur la couche « faits » (0,37). Les couches font moins dépendre le résultat du modèle.
- **Le rappel est le point faible** (0,29). C'est ce qu'une couche par attribut, ou une question par entité, viserait (§10). La précision restante dépend des contrôles déterministes (types) et de la décision de l'auteur.
- **Le substitut est optimiste**, comme annoncé (§8.2, point 5). Aucune conclusion de faisabilité sur une passe d'un modèle de 4 milliards, plus petit que la cible.
- **Durée** : 75 à 90 s par appel sur cette machine, contre environ 17 s mesurés sur un passage court. La durée suit la longueur du prompt (1 766 tokens pour l'extracteur) et de la réponse. Un lot comme b1 reste faisable en tâche de fond ; la couche « mentions » (C1) n'a pas été mesurée.

## Suite possible

- Mesurer la couche « mentions » (C1, C2) et la chaîne complète de la couche « faits » (sonde, énonciation, critique) avec qwen3:4b, sur b1 puis sur Corbelle : c'est la chaîne que l'atelier emploie.
- Garder qwen3:4b comme **second point de mesure** à chaque remède : un remède qui n'aide que Haiku est suspect.
