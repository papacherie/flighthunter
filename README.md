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


## FlightHunter AI V6 : thèmes, filtres automatiques, offres et choix compagnie

- Mode clair ou sombre avec préférence locale persistante, aucune recherche préchargée : départ, arrivée et dates à saisir.
- Changer **escales/direct** relance automatiquement la recherche si les dates et aéroports sont valides et si le code privé est présent. Une temporisation évite de déclencher plusieurs recherches pour des clics rapides.
- Le serveur vise **au moins 6 itinéraires vérifiés lorsqu'ils existent**, sans inventer de vols. Il vérifie plusieurs retours et plafonne l'exploration à 1 recherche initiale + 8 recherches de retours (9 appels SerpApi maximum par recherche sans autres clics). Chaque changement de filtre peut consommer de nouveaux crédits ; cache de 15 min pour les paramètres identiques.
- Sur une offre possédant un `booking_token` SerpApi, « Choisir · voir la compagnie » demande **à la demande** les `booking_options`. Si Google Flights indique une option auprès de la compagnie, le service tente de résoudre son lien de réservation. Si le fournisseur ne retourne pas un lien vérifiable, un lien de recherche Google Flights est ouvert à la place. **Aucune garantie de préremplissage auprès de toutes les compagnies**, car les vendeurs ne publient pas tous un lien profond stable. Aucun achat, aucun formulaire de paiement.
- Toutes les requêtes payantes et les liens compagnies nécessitent `APP_ACCESS_CODE` ; SerpApi demeure configuré via `SERPAPI_API_KEY` sur Render. Ne placez aucune clé dans GitHub. 
- **Connexion depuis une conversation ChatGPT** : l'API reste protégée par `APP_ACCESS_CODE`. Un connecteur/outil authentifié (ou un profil navigateur qui conserve un accès) doit être lié avant qu'un assistant puisse rechercher directement dans FlightHunter sans saisie manuelle répétée. Le simple déploiement d'une API publique n'accorde pas d'accès automatique à ChatGPT ; ne jamais publier le code dans un chat pour contourner cette étape.


### Accès sans ressaisie depuis un navigateur lié à ChatGPT

La V6 inclut `POST /api/session/login` pour convertir le code privé en **cookie HttpOnly Secure SameSite=Lax**, valable 30 jours et automatiquement invalidé si les secrets Render changent. Les appels SerpApi acceptent le cookie ou l'en-tête privé. L'assistant ChatGPT ne connaît aucun secret ; un **profil navigateur TinyFish** créé puis autorisé une fois par l'utilisateur peut conserver cette session et lancer des recherches à sa place. Sans connexion initiale, l'assistant ne peut pas accéder à l'API privée ; il ne faut pas rendre l'endpoint public ou introduire des clés dans les messages.

## V7 — Mes recherches (octobre 2026)

Cette version ajoute un **historique privé côté serveur**, consultable depuis l'onglet « Mes recherches » et le lien « Mes recherches » du formulaire. Les recherches **effectuées à partir de V7** sont automatiquement archivées après réception des résultats, y compris si aucun billet n'est trouvé. Les anciens résultats V6 ne peuvent pas être reconstitués sans une nouvelle recherche.

### Fonctionnement

- Chaque recherche sauvegardée contient les critères, la date/heure de collecte, 0 à 12 offres, leurs vols aller/retour et le prix **total** indicatif du groupe. Le code privé, la clé SerpApi, les cookies et tokens de réservation ne sont **jamais** enregistrés dans l'historique.
- La liste des **40 recherches récentes** est consultable via `GET /api/history` après authentification. Le stockage est borné aux **80 instantanés les plus récents** pour limiter les coûts (les plus anciens sont supprimés).
- Chaque recherche possède un identifiant aléatoire et un lien du type `https://flighthunter-ai.onrender.com/r/<identifiant>`. La page ne contient **aucune donnée publique** ; la récupération des résultats nécessite une **session privée FlightHunter** valide. La personne à qui tu envoies le lien doit être autorisée sur FlightHunter.
- **Actualiser les prix** relance explicitement une recherche SerpApi (jusqu'à 9 appels), et crée un **nouvel instantané daté**, sans écraser l'ancien. La liste des résultats enregistrés n'appelle jamais SerpApi ; ouvrir un lien archivé ne consomme **aucun** crédit.
- Les **anciens tarifs** sont étiquetés comme archivés/non actuels ; les boutons de réservation directe périmés sont désactivés, les liens Google Flights restent présents si disponibles. Aucun tarif ni accès compagnie n'est garanti.
- **Supprimer** efface immédiatement l'enregistrement côté serveur. L'interface utilise des cookies `HttpOnly` déjà mis en place dans V6 ou le code privé via un en-tête, sans exposer les données dans la page HTML.

### Stockage : Render et les limites du gratuit

**Important : le système fonctionne en stockage local transitoire même sans PostgreSQL, mais ce stockage n'est pas durable sur un service Web Render gratuit.** Il peut être perdu à chaque redéploiement ou redémarrage. La présence d'un lien `/r/...` ne garantit donc pas, à elle seule, qu'il fonctionnera durablement.

Pour la persistance entre déploiements, configurer la variable d'environnement Render `DATABASE_URL` avec **l'Internal Database URL** d'une base PostgreSQL placée dans la même région que le service (`Frankfurt`). Ne collez **jamais** cette URL dans GitHub ou dans une conversation ; elle contient un mot de passe. Le service V7 possède `psycopg2-binary` pour supporter directement PostgreSQL. La base et les tables sont créées automatiquement au premier usage.

**Render Postgres Free expire 30 jours après sa création** et les données finissent par être supprimées sans passage à un plan payant ou migration ; aucune sauvegarde automatique n'est incluse. Une base gratuite `flighthunter-history` a été créée le **18 octobre 2026**, avec expiration annoncée **17 novembre 2026**. Pour une conservation réellement longue durée, migrer vers une base persistante non éphémère avant l'expiration (ou exporter le contenu du datastore). Ne passez pas à une formule payante sans décision explicite.

### Déploiement de V7 sur GitHub et Render

1. Copier **le contenu** de ce dossier (pas le dossier parent) dans la racine du dépôt `papacherie/flighthunter`, en remplaçant les fichiers V6. Notamment `app.py`, `history_store.py`, `static/index.html`, `static/app.js`, `static/style.css`, `requirements.txt`, `tests/`.
2. Valider dans GitHub ; Render redéploie normalement automatiquement avec la V7.
3. Dans le tableau de bord Render, accéder à la base `flighthunter-history` > **Connect** > copier la **Internal Database URL** dans la nouvelle variable d'environnement du service web `flighthunter-ai` appelée **`DATABASE_URL`**. Ne pas remplacer `SERPAPI_API_KEY` ni `APP_ACCESS_CODE`. Cette étape est nécessaire pour rendre l'historique résistant aux redéploiements.
4. Au besoin, redéployer après la modification d'environnement. Connectez-vous puis ouvrez `/api/status` (affiche `history_storage: postgres` après branchement) ; l'onglet « Mes recherches » précisera « Stockage serveur activé ».
5. Une recherche de billets depuis FlightHunter ou depuis le navigateur TinyFish lié à ChatGPT créera alors un instantané et renverra dans la réponse privée les propriétés `history_id` et `history_url`. ChatGPT peut fournir le lien durable de cette recherche tant que la base demeure active.

**Tests V7** : `python -m unittest discover -s tests -v` inclut 33 tests (dont 7 tests d'historique) ; `node --check static/app.js` contrôle la syntaxe de l'interface. La recherche SerpApi réelle et la connexion à Render Postgres restent à vérifier après déploiement.
