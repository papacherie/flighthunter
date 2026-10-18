# FlightHunter AI 5.0 — Design clair inspiré de Google Flights

Application personnelle de **recherche et comparaison** de vols aller-retour, sans réservation et sans paiement. Interface Material Design (palette claire et bleu `#1A73E8`) adaptée au Mac et à l'iPhone, sans usurper l'identité de Google Flights. Fournisseur de résultats : Google Flights via **SerpApi**.

## Nouveautés de l'interface

- Barre supérieure, formulaire de recherche compact avec départ/arrivée libres dans le monde entier, dates aller-retour et compteur de voyageurs.
- **Voyageurs** : 1 à 8 adultes et/ou enfants (8 personnes au total maximum), âge exact de chaque enfant, bébés sur les genoux ou avec siège. Les mineurs de 12–17 ans sont facturés dans la catégorie tarifaire « adulte » que reçoit l'API. La tarification exacte de chaque mineur reste à confirmer auprès de la compagnie.
- **Filtres** : escales (nouvelle recherche nécessaire), prix maximum, compagnies disponibles et durée. **Tri** par prix, durée ou heure de départ.
- **Cartes de résultats** : logos réellement fournis par SerpApi (si disponibles), itinéraires aller/retour, correspondances et heures, prix total pour le groupe, moyenne *indicative* par personne, détail déroulant et recherche chez Google Flights.
- **Calendrier** : sélection du jour d'aller et mémorisation locale des tarifs effectivement recherchés durant l'onglet actif. Les autres dates sont volontairement notées « — » : aucune estimation inventée et **aucune exploration exhaustive des dates**.
- **Carte** : *schéma d'itinéraire non géographique*, présentant les deux points sélectionnés et le prix minimum de la recherche. Aucune carte de prix par destination n'est inventée en l'absence de données géographiques et tarifaires dédiées.
- **Code privé** : nécessaire pour lancer une recherche de vols et pour les suggestions d'aéroports (qui consomment des crédits API). Ne pas coller `SERPAPI_API_KEY` dans le formulaire : utiliser la valeur privée de `APP_ACCESS_CODE`.
- **Liens de comparateurs** obtenus depuis l'API existante, sans réservation ou modification de billets.

L'application n'utilise pas les marques, icônes ou polices propriétaires de Google pour se faire passer pour son produit. Le style emprunte uniquement des principes d'interface et une palette Material Design.

## Installation / mise à jour de FlightHunter existant

La mise à jour conserve le backend de la v4 et les routes publiques. **Les variables de Render restent inchangées**.

1. Décompressez l'archive de FlightHunter 5.0.
2. Dans [GitHub `papacherie/flighthunter`](https://github.com/papacherie/flighthunter), remplacez **à la racine** les fichiers `app.py`, `static/index.html`, `static/style.css`, `static/app.js`, `README.md`, `tests/test_app.py` et éventuellement les autres fichiers conservés. Veillez à ne pas ajouter un dossier parent `FlightHunter_v5_Material`.
3. Validez le commit. Le service Render existant est configuré en **Auto Deploy**, donc un nouveau déploiement se lance automatiquement.
4. Attendez **Live**, puis visitez [FlightHunter AI](https://flighthunter-ai.onrender.com/) et rechargez le site si nécessaire. Les assets sont versionnés `v=5.0.0` pour éviter un ancien cache.

### Secrets Render

- `SERPAPI_API_KEY` : clé privée SerpApi, jamais dans GitHub ni dans les liens.
- `APP_ACCESS_CODE` : code de protection du quota, secret côté Render. Le code est utilisé par le navigateur pour autoriser une recherche et peut être conservé **dans la session du navigateur uniquement**.

Aucune clé ni carte bancaire n'est contenue dans les sources. Cette mise à jour ne change pas les variables.

## Fonctionnement / limites

1. Configurer une fois le code privé dans l'en-tête.
2. Entrer une ville et choisir une suggestion d'autocomplétion, ou taper un code aéroport IATA à trois lettres (`CDG`, `JFK`, `PVG`...). Les villes et codes sont validés côté serveur.
3. Renseigner les dates et la composition précise du groupe.
4. Cliquer **Rechercher les vols** ; le moteur interroge SerpApi une première fois et vérifie jusqu'à trois itinéraires retour, soit généralement jusqu'à **quatre requêtes**. Les recherches en cache coûtent moins de crédits.
5. Filtrer, trier, regarder les détails, puis ouvrir le comparateur ou le vendeur choisi. **Aucun prix n'est garanti avant le paiement chez le vendeur.**

Le tri et le filtrage s'appliquent **uniquement aux offres renvoyées et vérifiées par cette recherche**, pas à tous les vols disponibles dans le monde. Les jours calendaires sans recherche n'affichent aucun prix. La « carte » n'affiche pas de géographie exacte, et aucune étiquette « écologique » n'est utilisée sans données d'émissions vérifiées. Les liens externes peuvent ne pas préserver tous les âges de voyageurs : vérifier sur le site vendeur.

## Tests

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check static/app.js
```

Les tests intégrés couvrent les paramètres SerpApi, les âges des enfants, les bébés, la tarification catégorie adulte des adolescents, la validation des aéroports et des retours, la protection du quota, les logos autorisés et les URL. Le front a été testé dans Chromium sur **1440 px et 390 px**, sans erreur JavaScript ni débordement horizontal. Un test complet SerpApi avec une vraie clé doit être réalisé sur Render après mise en ligne. Nous ne revendiquons pas un score Lighthouse non mesuré.
