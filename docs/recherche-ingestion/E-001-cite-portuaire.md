# E-001 — « la cité portuaire » prise pour une catégorie

- **Statut** : ouverte
- **Classe** : S (forme de surface : une désignation prise pour une valeur)
- **Où** : b1, `notes-baron` v1, passage 1 ; extraction monolithique (future couche C5, avec C3 en amont)
- **Observé avec** : Claude Sonnet 5, `claude-code`, prompt version 3, 28 septembre 2026 ; 6 appels sur 6 (systématique). **Non reproduit** sous Claude Haiku 4.5, `api-haiku`, 4 octobre 2026, 0 passe sur 2 ([X-001](X-001-b1-haiku-reference.md)) : Haiku ne tire rien de « la cité portuaire »
- **Coût en revue** : une fausse anomalie (collision avec `brume.category = port`, donné par `lieux-de-valmont`)

## Observation

Passage : « Odon de Brume est le baron de Brume. Il gouverne la cité portuaire depuis la Chute. »

Sortie : `set_attribute brume.category = "cité portuaire"`, en plus des faits attendus.

Attendu : rien sur `brume.category` dans ce passage. La catégorie `port` est déjà dans l'état, et `lieux-de-valmont` p1 la corrobore (support).

## Explication

1. **« la cité portuaire » est une désignation de Brume**, pas une affirmation sur sa catégorie : c'est une coréférence par épithète (« le baron », « la cité portuaire »). Le modèle la résout correctement vers Brume, puis en tire une valeur.
2. **`Place.category` est un texte libre** (`schemas/`, `category: { type: text }`) : rien ne dit au modèle que les valeurs attendues sont courtes (`port`, `capitale`, `taverne`), ni que « cité portuaire » et « port » sont la même valeur.
3. Le fait est **vrai mais inféré** (Brume est bien un port) : la frontière avec la classe I est mince. Le dommage vient de la forme, qui crée une collision.

## Remèdes envisagés

1. *Mesure* : aucun ; l'écart coûte réellement un geste.
2. *Déterministe* :
   - indication de schéma sur `Place.category` : vocabulaire attendu et forme courte (chantier §10.5) ;
   - table de normalisation (« cité portuaire » → `port`), qui transforme la collision en support.

   Aucun appel en plus.
3. *Consigne* : règle « une désignation (épithète) n'est pas une valeur d'attribut ». À mesurer : une règle de plus pèse sur un petit modèle.
4. *Humain* : l'auteur pose « référence → brume » sur « la cité portuaire » (C3), ou « ignorer » sur le fait proposé ; si la couche C5 respecte les références données, l'écart disparaît à la relance.
5. *Couche* : avec C3 (coréférence) séparée, C5 reçoit « Il [odon] gouverne la cité portuaire [brume] » : la désignation est déjà consommée par la référence. Hypothèse à tester : cela suffit-il à supprimer l'écart ?

## Essais

Sous Haiku 4.5, l'écart n'apparaît pas (X-001) : le petit modèle en fait moins, y compris moins d'inférences de ce genre. Confirmé sur deux passes identiques (stabilité 1,0 sur ce passage). Premier essai prévu : remède 2 (vocabulaire de `category`), mesuré sous Haiku 4.5 en substitut.

## Conclusion

À venir.
