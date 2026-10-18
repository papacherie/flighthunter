# FlightHunter AI — Version 3.0 « Dark Flights »

Nouvelle interface inspirée de la **lisibilité** de Google Flights (sans copier son identité) : fond anthracite, cartes d’itinéraires aller/retour, horaires, correspondances, prix totaux et détails dépliables.

## Ce qui change

- **Logos réels des compagnies**, automatiquement lus dans le champ `flights[].airline_logo` renvoyé par SerpApi (Google Flights). En l'absence du lien, recherche du logo par code de compagnie dans la bibliothèque publique Google Flights (`https://www.gstatic.com/flights/airline_logos/70px/<IATA>.png`). Si inaccessible, affichage automatique des initiales.
- Affichage des compagnies présentes à l’aller et au retour, au maximum trois logos sur la carte.
- Détail des segments de vol, numéros de vol, correspondances, horaires et appareils lorsque l’API les fournit.
- Cards premium sombres, couleur spécifique pour la meilleure offre, indication du budget cible de 2 500 € pour l’ensemble des voyageurs, liens vers les recherches Google Flights.
- Responsive Mac / iPhone, pas de débordement horizontal sur écran mobile.
- **Aucune recherche automatique au chargement** : la saisie du code privé précède l'appel SerpApi. Les liens simples sont générés via `/api/links`, sans consommer aucun crédit SerpApi.
- Protection : seuls les liens logos HTTPS `www.gstatic.com/flights/airline_logos/*.png` sont exposés au navigateur, qui affiche une alternative lorsque l'image est absente.

## Installation (GitHub → Render)

1. Décompresser l’archive livrée et envoyer **le contenu de ce dossier** (pas le ZIP) à la racine du dépôt GitHub `papacherie/flighthunter`. Remplacer les fichiers `app.py`, `static/index.html`, `static/style.css`, `static/app.js`, `tests/test_app.py`, `README.md`. Aucun secret ne doit être commité.
2. Valider avec **Commit changes**. Le service Render `flighthunter-ai` est déjà configuré en déploiement automatique depuis la branche `main` et doit redéployer sans nouvelle intervention.
3. Après le statut **Live**, ouvrir `https://flighthunter-ai.onrender.com/` puis rafraîchir la page. Les fichiers CSS/JS ont des URL versionnées pour éviter de conserver le mauvais style en cache.
4. Saisir dans le volet **Code privé** la valeur de `APP_ACCESS_CODE` déjà stockée sur Render, puis cliquer sur **Comparer les vols**.

Configuration inchangée sur Render : `SERPAPI_API_KEY` et `APP_ACCESS_CODE`. Conserver ces valeurs uniquement côté serveur, jamais dans GitHub ou dans une capture. Mode Render Python avec `pip install -r requirements.txt` puis `uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1`.

## Tests

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -v
node --check static/app.js
```

Le projet a été testé avec **12 tests backend** et une vérification en navigateur Chromium sur formats ordinateur et mobile (données de démonstration seulement pour les captures de prévisualisation). Aucune recherche réelle n'a été déclenchée pendant les tests visuels, donc aucun crédit SerpApi dépensé.

## Limites importantes

- Les logos proviennent d’une source externe et ne sont affichés que lorsque disponibles. L’intégration ne garantit pas une identité visuelle pour chaque compagnie ni la pérennité du lien.
- Les prix viennent des recherches Google Flights via SerpApi ; **ils ne sont pas garantis** au stade du paiement et peuvent varier selon le vendeur, les bagages, la disponibilité et les voyageurs.
- Le moteur conserve la politique de version 2 : au maximum 3 départs sont inspectés par requêtes de retour (environ 4 appels SerpApi par recherche non mise en cache).
- Le bouton vers Google Flights ouvre une **recherche préremplie**, pas l’option de réservation exacte déjà sélectionnée. Afficher les logos des agences/vendeurs et leurs prix de réservation exigerait des appels supplémentaires à l'API de réservation lorsque celle-ci expose les options.
- Aucun achat, paiement, carte bancaire ou réservation automatique.
- Les prix présentés dans **les captures de prévisualisation** sont des valeurs de démonstration, non des offres fraîchement vérifiées.
