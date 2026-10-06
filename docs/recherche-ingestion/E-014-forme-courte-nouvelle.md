# E-014 — La forme courte d'une entité nouvelle n'est pas repérée, et l'auteur ne peut pas l'y rattacher

- **Statut** : en cours (le geste de l'auteur est fait ; le repérage reste à trancher, X-003)
- **Classe** : R (résolution : une forme courte qui désigne une entité nouvelle de la même source)
- **Où** : Corbelle c1, `brouillon-corbelle.md`, passage 6 ; couche « mentions » de l'atelier (C1b, C2), gestes de l'atelier
- **Observé avec** : Claude Haiku 4.5 par l'API (profil `api-haiku`, substitut), un lancement de la couche avec le modèle dans l'atelier, 6 octobre 2026 ; observé par l'auteur à l'écran (test humain, T3)
- **Coût en revue** : un ajout à la main, puis **aucun geste juste possible** : « nouvelle entité » crée un doublon (`new:ostrel`) à refuser en revue ; et un ajout à la portée de la source écrasait « Bertrand Ostrel »

## Observation

Passage 6 : « le maitre de la guilde c Bertrand Ostrel. Ostrel est pas fiable, il magouille avec ~~la vouivre~~ non avec l'abbesse en fait ».

| Mention | Couche (lancement 1) | Attendu (gold `c1-brouillon-corbelle.yaml`) |
|---|---|---|
| « la guilde » | nouvelle (`new:guilde`) | `bateliers` |
| « Bertrand Ostrel » | nouvelle (`new:bertrand ostrel`) | `new:bertrand-ostrel` |
| « Ostrel » | **absente** | `new:bertrand-ostrel` |
| « l'abbesse » | **absente** | `agathe` |

« la guilde » et « l'abbesse » relèvent d'un autre écart : la source a été importée dans le monde **Valmont**, où la Guilde des Bateliers et mère Agathe n'existent pas. Le monde de Corbelle (`corpus/corbelle-v1/corbelle/world.yaml`) est le bon cadre de ce test. Reste « Ostrel » seul, qui manque aussi dans le monde de Corbelle.

Deux défauts en découlent à l'écran :

1. **Pas de geste pour rattacher.** Les menus « Corriger » et « Ajouter » ne proposaient que « nouvelle entité », qui crée une entité par forme, et les entités du monde. Une entité nouvelle repérée dans la source n'était pas désignable.
2. **Un ajout écrasait la mention longue.** À la portée « toute la source », ajouter « Ostrel » couvrait aussi le mot « Ostrel » de « Bertrand Ostrel », et la nouvelle annotation remplaçait la mention plus longue qui le contenait. La couche, elle, garde toujours la portion la plus longue.

## Explication

1. **Repérage** : la couche « mentions » de l'atelier n'applique **aucun des deux remèdes** de [X-003](X-003-formes-courtes.md) aux formes courtes : ni la consigne A (`MentionFinder.short_forms`, désactivée par défaut), ni la règle B sans modèle (`short_forms`, appelée seulement par la mesure). X-003 avait laissé le choix ouvert, et l'atelier n'a hérité d'aucun des deux. La règle B aurait trouvé « Ostrel » : elle cherche les mots du nom d'une personne repérée, nouvelle comprise.
2. **Rattachement** : le premier incrément de l'atelier (I8) pensait le rattachement vers une entité **connue**. Les entités nouvelles de la source n'étaient pas exposées par `atelier.view`, et « Proposer » ne savait faire un alias que pour une entité connue.
3. **Écrasement** : le geste « ajouter » prenait toute annotation chevauchante comme celle qu'il remplace, sans la règle de la portion la plus longue de la couche.

## Remèdes envisagés

1. *Mesure* : le gold de Corbelle a déjà « Ostrel » ; rien à corriger.
2. *Déterministe* : brancher dans la couche de l'atelier la règle B de X-003 (formes courtes des personnes repérées, nouvelles comprises) ; et, dans le geste, ne pas remplacer une mention plus longue qui contient la portion ajoutée.
3. *Consigne* : activer la variante A dans C1b de l'atelier (une centaine de tokens de plus par appel).
4. *Humain* : un geste pour rattacher une forme à une entité nouvelle de la source (« Ostrel » → Bertrand Ostrel, nouvelle), qui devient un alias s'il est retenu pour le monde.
5. *Couche* : aucune.

## Essais

- **6 octobre 2026, remède 4 et correctif du geste** (branche `atelier-rattacher-nouvelle`) : les menus de l'atelier listent les **entités nouvelles de la source** (`new:<étiquette>`, sous « nouvelles de cette source ») ; « Proposer » crée l'entité une fois, sous le nom de son groupe (« Bertrand Ostrel »), au passage où ce nom apparaît, et envoie une forme rattachée et **retenue pour le monde** en `add_value aliases` de l'entité nouvelle (résolue au niveau du lot, T-ING-07) ; à la portée de la source, la forme rattachée confirme l'entité sans alias (même règle que pour une entité connue, Q4). Un ajout ne remplace plus une mention plus longue qui le contient. Tests : `tests/test_atelier.py` (`…_E_014`). Pas de mesure T2 : c'est un geste, pas une couche.
- Remèdes 2 (règle B dans l'atelier) et 3 (consigne A) : **non essayés**, à trancher avec X-003 (les deux faisaient jeu égal sur b1 ; Corbelle a des noms de famille employés seuls, où A et B peuvent diverger).

## Conclusion

Le geste manquait : il est fait. Le repérage de la forme courte reste ouvert : il dépend du choix entre A et B de X-003, que Corbelle peut départager.
