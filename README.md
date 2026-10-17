# FlightHunter AI — v1.0 (à publier sur Render)

**Statut :** code et tests prêts. Aucun site public n'a encore été créé. Les prix en direct requièrent des identifiants API de production.

## Utilité

Une application de recherche et de comparaison de vols pour usage personnel :
- Par défaut : Paris → Shanghai (PVG et SHA), 29 juillet → 20 août 2027, 2 adultes et 1 enfant (8 ans), économie.
- Dates, voyageurs, destination et escales modifiables.
- Tri des **totaux aller-retour pour tous les passagers** réellement fournis par l'API (sans prix imaginaires).
- Liens vers les recherches Google Flights, KAYAK et Skyscanner, avec les dates préremplies. Les sites peuvent modifier les liens et bloquer l'accès ; revérifier les paramètres à l'ouverture.
- **Aucune réservation, aucun paiement ni enregistrement de coordonnées bancaires**.

## Déployer en ligne sur Render (environ 4 étapes d'installation)

**Option privilégiée :** utiliser le plugin Render connecté à ChatGPT pour déployer les sources. Si l'outil ne peut pas déposer le code automatiquement, le projet est prêt pour un dépôt GitHub.

1. Créer un dépôt GitHub privé `flighthunter-ai` et y déposer les fichiers de ce dossier (PAS le dossier lui-même, les fichiers à la racine). Ne jamais y inclure de clés API.
2. Render > **New** > **Web Service** : connecter le dépôt. Laisser Render lire `render.yaml` ou utiliser ces commandes :
   - Build : `pip install -r requirements.txt`
   - Start : `uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1`
   - Python 3.12 / plan **Free** (pour essais, lorsque disponible).
3. Render te donnera une adresse `https://…onrender.com`. Tu auras immédiatement accès à l'application et à ses **liens comparateurs**.
4. Pour activer les **vrais prix en direct** et les classer automatiquement, obtenir des identifiants **Amadeus Self-Service en production** sur https://developers.amadeus.com , puis remplir dans Render > Environment :

   - `AMADEUS_CLIENT_ID` : identifiant de production (SECRET)
   - `AMADEUS_CLIENT_SECRET` : secret de production (SECRET)
   - `AMADEUS_ENV` : `production`
   - `APP_ACCESS_CODE` : code privé de ton choix, à saisir dans le volet « Configurer l'accès » de l'application.

   **Ne communique jamais les secrets en message ChatGPT.**

Si Amadeus ne valide pas encore l'accès production, laisser le service en mode **liens comparateurs**. En mode `AMADEUS_ENV=test`, les tarifs retournés par Amadeus sont **des données de bac à sable, non commercialisables** ; l'application les étiquette explicitement comme telles.

**Limites :** Amadeus ne couvre pas nécessairement tous les vols de Google Flights. Les prix peuvent encore évoluer chez le vendeur. Les liens fournis ouvrent une **recherche**, pas un billet sélectionné. La recherche API et les liens comparateurs ne sont donc pas équivalents.

## Tester sur Mac ou Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Puis ouvrir http://127.0.0.1:8000

Tests : `python -m unittest discover -s tests -v`

## Architecture

- `app.py` : serveur FastAPI, endpoints `GET /health`, `GET /api/status`, `POST /api/search`.
- `static/index.html`, `static/style.css`, `static/app.js` : interface responsive sans bibliothèque externe.
- `render.yaml` : configuration de déploiement Render.
- `tests/` : tests d'API, sécurité, filtrage des prix et liens.

## Confidentialité / limites de sécurité

Le code privé de recherche est conservé en mémoire temporaire de l'onglet, pas sur le serveur. La clé Amadeus n'est utilisée que côté serveur. Un contrôle basique de fréquence (20 secondes par adresse IP) empêchent des sollicitations répétées, mais cette v1 **n'est pas adaptée à une publication commerciale ouverte** sans authentification forte, limitation persistante, monitoring et politique de confidentialité. Un service Render Free peut s'endormir après 15 minutes d'inactivité (https://render.com/docs/free).

## Utilisation directement depuis ChatGPT (optionnelle, pas encore configurée)

Une fois ton site Render publié, le fichier `openapi-chatgpt.yaml` décrit une **Action de GPT**. Remplacer `REMPLACER-PAR-VOTRE-SITE` par le domaine obtenu, et configurer `X-Access-Code` comme clé API privée. Ne pas inclure les clés Amadeus dans la configuration du GPT. Cela permet à un GPT personnalisé d'interroger FlightHunter, mais cette connexion **n'existe pas encore** tant que le GPT n'est pas configuré.
