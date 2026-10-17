# FlightHunter AI — v2.0 (SerpApi)

FlightHunter est un outil **de recherche et de comparaison**, jamais de réservation, de paiement ou de collecte de données bancaires.

- Recherche initiale préremplie : Paris → Shanghai (PVG et SHA), 29/07/2027 — 20/08/2027, 2 adultes et 1 enfant de 8 ans.
- SerpApi Google Flights : une requête de recherche des **allers** en AR, suivie d'une requête avec `departure_token` pour chacune des trois meilleures options de départ afin de récupérer un **retour réel**. Cette v2 ne prétend pas parcourir tous les itinéraires ni tous les revendeurs.
- Les prix fournis par SerpApi pour les voyageurs sélectionnés sont **indicatifs** et doivent toujours être confirmés sur le site du vendeur. Bagages et suppléments à vérifier.
- Liens de recherches préremplies vers Google Flights, KAYAK et Skyscanner, soumis à changement de formats ou filtrage anti-bot.
- Pas d'intégration Amadeus en v2.

## Mise à jour du dépôt GitHub existant

Dans `https://github.com/papacherie/flighthunter`, sélectionne **Add file → Upload files**, puis dépose le **contenu décompressé** du dossier v2, pas le ZIP. GitHub peut demander de confirmer le remplacement des fichiers du même nom. La structure attendue est `app.py`, `static/app.js`, `static/index.html` et les autres fichiers à la racine du dépôt. Clique sur **Commit changes**. Render est connecté à `main` avec déploiement automatique.

## Configuration Render

Service Render : https://dashboard.render.com/web/srv-db9svh8m7kps73eki300

Dans **Environment** :

- `SERPAPI_API_KEY` : ta clé SerpApi privée, **uniquement sur Render**.
- `APP_ACCESS_CODE` : un code d'accès long et difficile à deviner, choisi par toi. Ce n'est **pas** la clé SerpApi. Tu le saisis ensuite dans « Configurer l'accès » sur le site FlightHunter afin de protéger les 250 appels gratuits mensuels.
- Les anciennes variables `AMADEUS_*` ne sont pas utilisées par ce code et peuvent être retirées plus tard.

**Ne mets jamais ces valeurs sur GitHub, dans un PDF partagé, ou sur une capture d'écran.** Si tu as exposé ta clé SerpApi, révoque-la sur SerpApi et mets la nouvelle dans Render.

Tant que `SERPAPI_API_KEY` **et** `APP_ACCESS_CODE` ne sont pas définis, le service refuse d'interroger SerpApi pour éviter qu'un visiteur épuise ton quota. Les liens des comparateurs restent disponibles.

## Tester

```
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
uvicorn app:app --reload
```

Vérifications :
- `/health` -> `{"ok":true}`
- `/api/status` -> `ready:true`, `provider:"SerpApi"` seulement si les deux variables sont présentes.
- Site -> « Configurer l'accès » -> saisir `APP_ACCESS_CODE` -> « Comparer les vols ».
- Tarifs AR triés pour **3 voyageurs** avec allers **et retours** vérifiés séparément.

## Quota et limites

Chaque recherche peut utiliser jusqu'à **4 requêtes SerpApi** : recherche des allers + recherche des retours pour 3 départs. Cache en mémoire 15 min. Ne pas utiliser de surveillance intensive sur le plan gratuit. Une recherche AR avec tous les retours n'est pas nécessairement équivalente à une disponibilité finale chez la compagnie. Il n'existe aucun mécanisme pour réserver ou bloquer les prix ici.

Documentation fournisseur : https://serpapi.com/google-flights-api.
