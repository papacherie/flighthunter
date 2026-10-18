"""FlightHunter AI v2 — flight discovery through SerpApi Google Flights.

No ticket booking or payment. API key is server side only.
Results are indicative and are ALWAYS rechecked with the seller.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
app = FastAPI(title='FlightHunter AI', version='5.0.0', docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

API_KEY = os.environ.get('SERPAPI_API_KEY', '').strip()
ACCESS_CODE = os.environ.get('APP_ACCESS_CODE', '').strip()
SERPAPI_URL = 'https://serpapi.com/search.json'
RATE_LOCK = threading.Lock()
RATE: dict[str, float] = {}
CACHE_LOCK = threading.RLock()
CACHE: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 15 * 60
AIRPORT_CACHE: dict[str, tuple[float, list[dict]]] = {}
AIRPORT_LOCK = threading.RLock()
AUTOCOMPLETE_RATE: dict[str, float] = {}



def is_ready() -> bool:
    # Require private access code to protect shared free API quota on a public website.
    return bool(API_KEY and ACCESS_CODE)


def normalize_location(value: object) -> str:
    """Google Flights accepts IATA airport lists or Google location knowledge IDs."""
    location = str(value or '').strip().upper() if not str(value or '').startswith(('/m/', '/g/')) else str(value).strip()
    if re.fullmatch(r'[A-Z]{3}(?:,[A-Z]{3}){0,5}', location):
        return location
    if re.fullmatch(r'/(?:m|g)/[A-Za-z0-9_\-]{2,70}', location):
        return location
    raise ValueError('Sélectionne une ville/aéroport dans les suggestions, ou indique un code IATA (ex. CDG).')


def validate(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError('Paramètres invalides.')
    origin = normalize_location(body.get('origin', 'CDG,ORY'))
    dest = normalize_location(body.get('destination', 'PVG,SHA'))
    if origin == dest or (len(origin) == len(dest) == 3 and origin == dest):
        raise ValueError('Le départ et l’arrivée doivent être différents.')
    start, end = str(body.get('departure', '')).strip(), str(body.get('return', '')).strip()
    try:
        ds, dr = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise ValueError('Dates incorrectes.') from exc
    if ds < dt.date.today() or dr <= ds:
        raise ValueError('Le départ doit être à venir, et le retour après le départ.')
    if dr > dt.date.today() + dt.timedelta(days=365):
        raise ValueError('La date dépasse le calendrier de réservation habituel de 365 jours.')
    try:
        adults = int(body.get('adults', 2))
    except (ValueError, TypeError) as exc:
        raise ValueError('Nombre d’adultes incorrect.') from exc
    children = body.get('children_ages', [{'age': 8}])
    if not isinstance(children, list) or len(children) > 7:
        raise ValueError('Liste des enfants incorrecte (7 maximum).')
    normalized_children = []
    for child in children:
        if not isinstance(child, dict) or type(child.get('age')) is not int:
            raise ValueError('Indique un âge entier pour chaque enfant.')
        age = child['age']
        if not (0 <= age <= 17):
            raise ValueError('L’âge d’un enfant doit être entre 0 et 17 ans au départ.')
        seat = bool(child.get('seat', False)) if age < 2 else True
        if age < 2 and type(child.get('seat', False)) is not bool:
            raise ValueError('Indique si le bébé occupe un siège.')
        normalized_children.append({'age': age, 'seat': seat})
    total = adults + len(normalized_children)
    infants_lap = sum(x['age'] < 2 and not x['seat'] for x in normalized_children)
    infants_seat = sum(x['age'] < 2 and x['seat'] for x in normalized_children)
    children_count = sum(2 <= x['age'] <= 11 for x in normalized_children)
    teens = sum(12 <= x['age'] <= 17 for x in normalized_children)
    if not 1 <= adults <= 8 or total > 8:
        raise ValueError('Il faut au moins un adulte majeur, et 8 voyageurs maximum.')
    if infants_lap > adults:
        raise ValueError('Un adulte ne peut accompagner qu’un bébé sans siège sur cette recherche.')
    stops = str(body.get('stops', 'any'))
    if stops not in ('any', '0', '1', '2'):
        raise ValueError('Nombre d’escales incorrect.')
    return {'origin': origin, 'destination': dest, 'departure': start, 'return': end,
            'adults': adults, 'children_ages': normalized_children,
            'children': children_count, 'infants_in_seat': infants_seat,
            'infants_on_lap': infants_lap, 'serpapi_adults': adults + teens,
            'travelers_count': total, 'stops': stops}


def flight_google_link(origin: str, dest: str, outbound: str, inbound: str, adults: int, children: int) -> str:
    """Observed Google Flights URL structure. Format is undocumented and may break."""
    def leg(date: str, frm: str, to: str) -> bytes:
        return b'\x1a\x1a\x12\x0a' + date.encode() + b'j\x05\x12\x03' + frm.encode() + b'r\x05\x12\x03' + to.encode()
    blob = leg(outbound, origin, dest) + leg(inbound, dest, origin) + b'\x40\x01' * adults + b'\x40\x02' * children + b'\x48\x01\x98\x01\x01'
    return 'https://www.google.com/travel/flights?' + urlencode({'hl': 'fr', 'curr': 'EUR', 'tfs': base64.urlsafe_b64encode(blob).decode().rstrip('=')})


def search_links(c: dict) -> list[dict]:
    a, b = c['departure'], c['return']
    origin, dest = c['origin'], c['destination']
    google = 'https://www.google.com/travel/flights?' + urlencode({
        'hl': 'fr', 'curr': 'EUR', 'q': f'Flights from {origin} to {dest} on {a} through {b}'})
    links = {'origin': origin, 'destination': dest, 'google': google,
             'note': 'Les âges, les bébés et les voyageurs sont à revérifier sur les comparateurs.'}
    if re.fullmatch('[A-Z]{3}', origin) and re.fullmatch('[A-Z]{3}', dest):
        links['kayak'] = ('https://www.kayak.fr/flights/' + origin + '-' + dest + '/' + a + '/' + b + '?' + urlencode({
            'sort': 'price_a', 'adults': c['adults'], 'children': len(c['children_ages']),
            'childages': ','.join(str(x['age']) for x in c['children_ages'])}))
        links['skyscanner'] = ('https://www.skyscanner.fr/transport/vols/' + origin.lower() + '/' + dest.lower() + '/' + a[2:].replace('-', '') + '/' + b[2:].replace('-', '') + '/?' + urlencode({
            'adultsv2': c['adults'], 'childrenv2': ','.join(str(x['age']) for x in c['children_ages']),
            'cabinclass': 'economy', 'rtn': 1}))
    return [links]


def serpapi_parameters(c: dict, departure_token: str | None = None) -> dict:
    # Stops are different from FlightHunter's filter: 0=any, 1=nonstop, 2=<=1, 3=<=2.
    stops = {'any': 0, '0': 1, '1': 2, '2': 3}[c['stops']]
    params = {'engine': 'google_flights', 'api_key': API_KEY, 'type': 1,
              'departure_id': c['origin'], 'arrival_id': c['destination'],
              'outbound_date': c['departure'], 'return_date': c['return'],
              'adults': c['serpapi_adults'], 'children': c['children'],
              'infants_in_seat': c['infants_in_seat'], 'infants_on_lap': c['infants_on_lap'], 'travel_class': 1,
              'currency': 'EUR', 'gl': 'fr', 'hl': 'fr', 'sort_by': 2,
              'stops': stops, 'no_cache': 'false'}
    if departure_token:
        params['departure_token'] = departure_token
    return params


def serpapi_query(c: dict, departure_token: str | None = None) -> dict:
    response = requests.get(SERPAPI_URL, params=serpapi_parameters(c, departure_token), timeout=35)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError('Réponse fournisseur invalide.')
    if data.get('error'):
        raise RuntimeError('SerpApi a signalé une erreur : consulte ton solde ou les paramètres dans SerpApi.')
    return data


def rows(data: dict) -> list[dict]:
    return [f for section in ('best_flights', 'other_flights') for f in (data.get(section) or []) if isinstance(f, dict)]


def parsed_price(f: dict) -> float | None:
    try:
        price = float(f.get('price'))
        if not 0 < price < 1_000_000:
            return None
        return price
    except (ValueError, TypeError):
        return None


def safe_airline_logo(value: object) -> str:
    """Only expose the documented Google Flights airline-logo image URLs."""
    if not isinstance(value, str):
        return ''
    parsed = urlparse(value)
    if parsed.scheme != 'https' or parsed.hostname != 'www.gstatic.com':
        return ''
    if not parsed.path.startswith('/flights/airline_logos/') or not parsed.path.lower().endswith('.png'):
        return ''
    return value


def logo_entries(offer: dict) -> list[dict]:
    flights = offer.get('flights') or []
    entries: list[dict] = []
    used: set[str] = set()
    for flight in flights:
        name = str(flight.get('airline') or '').strip()
        flight_number = str(flight.get('flight_number') or '')
        match = re.match(r'^([A-Z0-9]{2})\s*\d', flight_number, re.I)
        code = match.group(1).upper() if match else ''
        logo = safe_airline_logo(flight.get('airline_logo'))
        if not logo and flight is flights[0]:
            logo = safe_airline_logo(offer.get('airline_logo'))
        if not logo and code:
            logo = safe_airline_logo(f'https://www.gstatic.com/flights/airline_logos/70px/{code}.png')
        identifier = code or name or logo
        if identifier and identifier not in used:
            entries.append({'airline': name, 'code': code, 'url': logo})
            used.add(identifier)
    if not entries:
        main_logo = safe_airline_logo(offer.get('airline_logo'))
        if main_logo:
            entries.append({'airline': '', 'code': '', 'url': main_logo})
    return entries[:4]


def leg_info(offer: dict) -> dict:
    flights = offer.get('flights') or []
    if not flights or not isinstance(flights, list):
        return {}
    first, last = flights[0], flights[-1]
    depart, arrive = first.get('departure_airport') or {}, last.get('arrival_airport') or {}
    airlines = list(dict.fromkeys(str(f.get('airline') or '') for f in flights if f.get('airline')))
    minutes = offer.get('total_duration')
    try:
        mins = int(minutes)
        duration = f'PT{mins // 60}H{mins % 60}M' if mins >= 0 else ''
    except (TypeError, ValueError):
        duration = ''
    segments = []
    for f in flights:
        src = f.get('departure_airport') or {}
        dst = f.get('arrival_airport') or {}
        segments.append({'from': src.get('id') or '', 'to': dst.get('id') or '',
                         'departure': str(src.get('time') or '').replace(' ', 'T'),
                         'arrival': str(dst.get('time') or '').replace(' ', 'T'),
                         'airline': str(f.get('airline') or ''),
                         'flight_number': str(f.get('flight_number') or ''),
                         'airplane': str(f.get('airplane') or '')})
    layovers = []
    for layover in offer.get('layovers') or []:
        try:
            duration_min = max(0, int(layover.get('duration') or 0))
        except (TypeError, ValueError):
            duration_min = 0
        layovers.append({'id': str(layover.get('id') or ''), 'duration': duration_min})
    return {'stops': len(flights) - 1, 'from': depart.get('id') or '', 'to': arrive.get('id') or '',
            'departure': str(depart.get('time') or '').replace(' ', 'T'),
            'arrival': str(arrive.get('time') or '').replace(' ', 'T'),
            'via': [str(x.get('id')) for x in (offer.get('layovers') or []) if x.get('id')],
            'carriers': airlines, 'duration': duration, 'segments': segments,
            'layovers': layovers, 'airline_logos': logo_entries(offer)}


def trip_matches_leg(leg: dict, c: dict, outbound: bool) -> bool:
    """For a city KGMID, SerpApi does the filtering; validate date and direction.

    For IATA lists check the actual segments' airports against the chosen choices.
    """
    if not leg:
        return False
    src = c['origin'] if outbound else c['destination']
    dest = c['destination'] if outbound else c['origin']
    date = c['departure'] if outbound else c['return']
    if not str(leg.get('departure', '')).startswith(date):
        return False
    return all((x.startswith(('/m/', '/g/')) or leg.get(key) in x.split(','))
               for x, key in ((src, 'from'), (dest, 'to')))


def price_offers(data: dict, c: dict) -> list[dict]:
    """Only return flights verified by a second SerpApi request are considered complete."""
    available = []
    seen = set()
    for outbound_item in sorted(rows(data), key=lambda o: parsed_price(o) or 1e8):
        token = outbound_item.get('departure_token')
        out = leg_info(outbound_item)
        if not token or not trip_matches_leg(out, c, True):
            continue
        if c['stops'] != 'any' and out['stops'] > int(c['stops']):
            continue
        flight_numbers = tuple(str(f.get('flight_number') or '') for f in outbound_item.get('flights') or [])
        if flight_numbers in seen:
            continue
        seen.add(flight_numbers)
        available.append((outbound_item, token, out))
        if len(available) >= 3:
            break
    result = []
    # Max 1 outbound search + 3 return searches: manageable free-tier usage.
    for outbound_item, token, out in available:
        try:
            returning = serpapi_query(c, token)
        except (requests.RequestException, RuntimeError, ValueError):
            continue
        cheapest = sorted(rows(returning), key=lambda o: parsed_price(o) or 1e8)
        for back_item in cheapest:
            price = parsed_price(back_item)
            back = leg_info(back_item)
            if not price or not trip_matches_leg(back, c, False):
                continue
            if c['stops'] != 'any' and back['stops'] > int(c['stops']):
                continue
            carriers = list(dict.fromkeys(out['carriers'] + back['carriers']))
            dest = out['to']
            fingerprint = hashlib.sha256(repr((out['departure'], back['departure'], carriers, price)).encode()).hexdigest()[:15]
            result.append({'id': fingerprint, 'source': 'Google Flights via SerpApi', 'price': price,
                           'carrier': ' / '.join(carriers) or 'Compagnie non précisée',
                           'outbound': out, 'inbound': back, 'destination': dest,
                           'baggage': 'À vérifier lors de la réservation',
                           'price_status': 'Prix affiché, non garanti chez le vendeur',
                           'booking_link': search_links(c)[0]['google']})
            break  # cheapest valid return for this specific outbound itinerary
    return sorted(result, key=lambda offer: offer['price'])


@app.middleware('http')
async def security_headers(request: Request, call_next):
    res = await call_next(request)
    res.headers['X-Content-Type-Options'] = 'nosniff'
    res.headers['X-Frame-Options'] = 'DENY'
    res.headers['Cache-Control'] = 'no-store'
    res.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    res.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data: https://www.gstatic.com; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    return res


@app.get('/')
def home():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/health')
def health():
    return {'ok': True, 'product': 'FlightHunter AI'}


@app.get('/api/status')
def status():
    return {'product': 'FlightHunter AI', 'ready': is_ready(),
            'api_mode': 'production' if is_ready() else 'links_only',
            'provider': 'SerpApi' if API_KEY else 'none',
            'needs_access_code': bool(API_KEY and not ACCESS_CODE),
            'private_search': bool(ACCESS_CODE)}


@app.post('/api/links')
def public_links(body: dict):
    # Generates URL templates without any supplier API call or consumption of credits.
    try:
        criteria = validate(body)
    except (ValueError, TypeError, OverflowError) as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)
    return {'criteria': criteria, 'links': search_links(criteria)}


@app.get('/api/airports')
def airport_suggestions(q: str, request: Request):
    # Avoid spending API credits unless there is a deliberate, authenticated query.
    if not is_ready() or not secrets.compare_digest(request.headers.get('X-Access-Code', ''), ACCESS_CODE):
        return JSONResponse({'error': 'Saisis ton code privé avant d’afficher les suggestions.'}, status_code=401)
    query = q.strip()
    if not (3 <= len(query) <= 70) or not re.fullmatch(r"[\w\s\-À-ÿ']{3,70}", query, re.UNICODE):
        return JSONResponse({'error': 'Saisis au moins 3 caractères pour rechercher un aéroport.'}, status_code=400)
    key = query.casefold()
    now = time.monotonic()
    with AIRPORT_LOCK:
        cached = AIRPORT_CACHE.get(key)
        if cached and cached[0] > now:
            return {'suggestions': cached[1], 'from_cache': True}
        ip = request.client.host if request.client else 'unknown'
        if now - AUTOCOMPLETE_RATE.get(ip, -1e10) < 2:
            return JSONResponse({'error': 'Attends 2 secondes avant une autre recherche.'}, status_code=429)
        AUTOCOMPLETE_RATE[ip] = now
    try:
        r = requests.get(SERPAPI_URL, params={'engine': 'google_flights_autocomplete',
                         'q': query, 'gl': 'fr', 'hl': 'fr', 'api_key': API_KEY,
                         'exclude_regions': 'true'}, timeout=18)
        r.raise_for_status()
        result = r.json()
        if not isinstance(result, dict) or result.get('error'):
            raise ValueError('Recherche d’aéroports indisponible.')
    except (requests.RequestException, ValueError):
        return JSONResponse({'error': 'Suggestions indisponibles : utilise un code IATA (ex. CDG).'}, status_code=502)
    suggestions = []
    seen = set()
    for entry in (result.get('suggestions') or [])[:12]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get('name') or '').strip()[:110]
        city_id = str(entry.get('id') or '')
        if re.fullmatch(r'/(?:m|g)/[A-Za-z0-9_\-]{2,70}', city_id) and city_id not in seen:
            suggestions.append({'label': name + ' · tous aéroports', 'id': city_id, 'type': 'city'})
            seen.add(city_id)
        for airport in (entry.get('airports') or [])[:9]:
            code = str(airport.get('id') or '').upper()
            if re.fullmatch('[A-Z]{3}', code) and code not in seen:
                label = str(airport.get('name') or name)[:95] + ' · ' + code
                suggestions.append({'label': label, 'id': code, 'type': 'airport'})
                seen.add(code)
        if len(suggestions) >= 15:
            break
    with AIRPORT_LOCK:
        if len(AIRPORT_CACHE) > 400:
            AIRPORT_CACHE.clear()
        AIRPORT_CACHE[key] = (now + 12 * 3600, suggestions[:15])
    return {'suggestions': suggestions[:15], 'from_cache': False}


@app.post('/api/search')
def search(body: dict, request: Request):
    try:
        criteria = validate(body)
    except (ValueError, TypeError, OverflowError) as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)
    response = {'criteria': criteria, 'links': search_links(criteria), 'offers': [],
                'checked_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'warning': 'Prix issus de Google Flights, non garantis. Vérifie tarifs, passagers, bagages et disponibilité chez le vendeur.'}
    if not is_ready():
        response.update(status='not_configured', mode='links_only',
                        message=('Clé SerpApi détectée. Configure aussi APP_ACCESS_CODE dans Render pour protéger ton quota gratuit.'
                                 if API_KEY else 'Comparateurs disponibles. SerpApi n’est pas encore configuré.'))
        return response
    supplied = request.headers.get('X-Access-Code', '')
    if not secrets.compare_digest(supplied, ACCESS_CODE):
        return JSONResponse({'error': 'Code privé de recherche incorrect.'}, status_code=401)
    stamp = time.monotonic()
    addr = request.client.host if request.client else 'unknown'
    cache_key = json.dumps(criteria, sort_keys=True)
    with CACHE_LOCK:
        cache = CACHE.get(cache_key)
        if cache and cache[0] > stamp:
            value = {**cache[1], 'from_cache': True}
            return value
        if len(CACHE) > 60:
            CACHE.clear()
    with RATE_LOCK:
        if stamp - RATE.get(addr, -1e20) < 25:
            return JSONResponse({'error': 'Recherche trop rapprochée. Réessaie dans 25 secondes.'}, status_code=429)
        RATE[addr] = stamp
        if len(RATE) > 1000:
            RATE.clear()
    try:
        data = serpapi_query(criteria)
        offers = price_offers(data, criteria)
    except (requests.RequestException, RuntimeError, ValueError) as exc:
        response.update(status='provider_error', message='Le fournisseur de vols ne répond pas. Vérifie l’état du compte SerpApi et réessaie.')
        return JSONResponse(response, status_code=502)
    response.update(offers=offers, count=len(offers), status='ok' if offers else 'empty',
                    provider='SerpApi / Google Flights', from_cache=False,
                    message=('Offres aller-retour avec vol retour vérifié pour trois voyageurs. Les trois départs les moins chers ont été contrôlés.'
                             if offers else 'Aucun tarif aller-retour complet vérifiable pour ces dates. Consulte les liens de recherche.'),
                    searched_departures=3, possible_api_requests=4)
    with CACHE_LOCK:
        CACHE[cache_key] = (stamp + CACHE_SECONDS, response)
    return response
