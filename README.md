# FlightHunter AI 4.0 — Aéroports mondiaux et âges des voyageurs

**Version à publier sur ton dépôt GitHub `papacherie/flighthunter`**. Elle prolonge le design sombre et les logos des compagnies de la v3. L'application n'effectue aucune réservation.

## Nouvelles fonctions

- Départ et arrivée **dans le monde entier** : entre directement un **code d'aéroport IATA à 3 lettres** (ex. `JFK`, `LHR`, `CDG`, `PVG`), ou saisis le nom d'une ville/aéroport et choisis une suggestion. Les suggestions sont obtenues avec **SerpApi Google Flights Autocomplete** (qui peut consommer un crédit). Un choix « ville, tous aéroports » passe un identifiant Google Knowledge Graph à Google Flights lorsque disponible.
- **Voyageurs personnalisables** : 1 à 8 adultes majeurs et 0 à 7 mineurs, **maximum 8 voyageurs au total**. Chaque enfant possède un champ **âge au départ (0 à 17 ans)**.
- Pour les **0–1 an**, choix entre *bébé sur les genoux* et *bébé avec siège*. Au maximum un bébé sur les genoux par adulte.
- Tarification transmise à SerpApi : **12–17 ans comptés comme adultes** (classification Google Flights), 2–11 ans enfants, 0–1 an `infants_in_seat` ou `infants_on_lap`. **SerpApi ne reçoit pas chaque âge séparément**, uniquement ces catégories et leurs nombres. Les tarifs/conditions détaillés propres à l'âge exact doivent être confirmés auprès de la compagnie.
- Conservation des cartes sombre aller/retour, escales, vrais logos s'ils sont disponibles, prix totaux par groupe et liens de comparaison. L'affichage des tarifs se limite aux retours réellement validés par une seconde recherche SerpApi. **Les prix ne sont pas garantis chez le vendeur.**
- Économies de crédits : suggestions uniquement **après saisie du code privé**, avec temporisation côté navigateur, limitation de fréquence et cache 12 h côté serveur. Les recherches de vols sont mises en cache pendant 15 minutes.

## Actualiser GitHub et Render

1. Décompresser cette archive, puis ouvrir le dépôt : <https://github.com/papacherie/flighthunter>.
2. Sur GitHub, remplacer les fichiers déjà présents par leurs nouveaux contenus : `app.py`, `static/index.html`, `static/style.css`, `static/app.js`, `tests/test_app.py`, `README.md`, `openapi-chatgpt.yaml`. Les fichiers doivent rester **dans les mêmes chemins**, pas à l'intérieur d'un dossier `FlightHunter_v4` supplémentaire. GitHub peut nécessiter de modifier les fichiers existants un à un via l'icône crayon ; l'interface de dépôt ne prend pas toujours en charge le remplacement par glisser-déposer.
3. Valider les modifications (**Commit changes**). Render redéploie automatiquement depuis la branche `main`. Attendre **Live**.
4. Ouvrir <https://flighthunter-ai.onrender.com/>. Les fichiers CSS/JS sont versionnés `v=4.0.0` pour éviter un vieux cache navigateur.

**Secrets :** conserver sur Render les variables existantes `SERPAPI_API_KEY` et `APP_ACCESS_CODE`. Aucun secret n'est inclus dans les fichiers. Ne pas les transmettre en conversation ni les publier sur GitHub.

## Utilisation

1. Entrer le **code privé** dans le volet 🔒 Code privé : ce n'est **pas** la clé SerpApi.
2. Écrire une ville ou un aéroport (ex. « Tokyo », « New York », « Heathrow »). Choisir un aéroport ou une ville dans le menu. Pour aller vite et ne pas consommer de crédit de suggestion, écrire directement le code IATA en lettres majuscules (`HND`, `JFK`...).
3. Choisir dates et escales, adultes majeurs et nombre d'enfants ; renseigner **l'âge de chaque enfant**. Pour les bébés de moins de 2 ans, choisir la place.
4. Lancer la recherche et vérifier les prix et âges chez le vendeur.

**Limites :** Google Flights/SerpApi ne garantissent pas tous les vols ni la disponibilité finale. Les options de réservation ne sont pas synchronisées avec le prix de la carte. Certaines villes ou aéroports peuvent ne pas être présents dans les suggestions du fournisseur ; un code IATA valide reste saisissable. Les liens vers KAYAK et Skyscanner sont proposés seulement lorsque départ et arrivée sont des aéroports IATA uniques, et doivent être revérifiés avant paiement ; le lien Google Flights demeure un lien de *recherche*.

## Tests

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check static/app.js
```

Résultats : **17 tests backend** réussis, JavaScript sans erreur de syntaxe, tests navigateur Chromium des formulaires desktop (1440 px) et mobile (390 px) sans débordement horizontal. Les tests d'interface ne consomment aucun crédit SerpApi et n'utilisent aucune donnée de prix fictive sur le site réel. L'endpoint d'autocomplétion a été testé avec une réponse simulée ; le service réel devra être validé sur Render après publication.
