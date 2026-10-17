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
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
app = FastAPI(title='FlightHunter AI', version='2.0.0', docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

API_KEY = os.environ.get('SERPAPI_API_KEY', '').strip()
ACCESS_CODE = os.environ.get('APP_ACCESS_CODE', '').strip()
SERPAPI_URL = 'https://serpapi.com/search.json'
RATE_LOCK = threading.Lock()
RATE: dict[str, float] = {}
CACHE_LOCK = threading.RLock()
CACHE: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 15 * 60


def is_ready() -> bool:
    # Require private access code to protect shared free API quota on a public website.
    return bool(API_KEY and ACCESS_CODE)


def validate(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError('Paramètres de recherche invalides.')
    origin = str(body.get('origin', 'PAR')).strip().upper()
    dest = str(body.get('destination', 'ALL')).strip().upper()
    start, end = str(body.get('departure', '')).strip(), str(body.get('return', '')).strip()
    try:
        adults = int(body.get('adults', 2))
        children = int(body.get('children', 1))
    except (ValueError, TypeError) as exc:
        raise ValueError('Nombre de voyageurs invalide.') from exc
    stops = str(body.get('stops', 'any')).strip()
    if not re.fullmatch(r'[A-Z]{3}', origin):
        raise ValueError('Le départ doit être un code IATA à trois lettres.')
    if dest not in ('ALL', 'PVG', 'SHA'):
        raise ValueError('Aéroport de Shanghai invalide.')
    try:
        departure = dt.date.fromisoformat(start)
        arrival = dt.date.fromisoformat(end)
    except ValueError as exc:
        raise ValueError('Dates invalides.') from exc
    if departure < dt.date.today() or arrival <= departure:
        raise ValueError('Le départ doit être futur et le retour après le départ.')
    if arrival > dt.date.today() + dt.timedelta(days=365):
        raise ValueError('Les dates sont au-delà des calendriers courants (365 jours).')
    if not (1 <= adults <= 6 and 0 <= children <= 3 and adults + children <= 8):
        raise ValueError('Voyageurs incorrects : 1 à 8, avec au moins un adulte.')
    if stops not in ('any', '0', '1', '2'):
        raise ValueError('Nombre d’escales invalide.')
    return {'origin': origin, 'destination': dest, 'departure': start, 'return': end,
            'adults': adults, 'children': children, 'stops': stops}


def flight_google_link(origin: str, dest: str, outbound: str, inbound: str, adults: int, children: int) -> str:
    """Observed Google Flights URL structure. Format is undocumented and may break."""
    def leg(date: str, frm: str, to: str) -> bytes:
        return b'\x1a\x1a\x12\x0a' + date.encode() + b'j\x05\x12\x03' + frm.encode() + b'r\x05\x12\x03' + to.encode()
    blob = leg(outbound, origin, dest) + leg(inbound, dest, origin) + b'\x40\x01' * adults + b'\x40\x02' * children + b'\x48\x01\x98\x01\x01'
    return 'https://www.google.com/travel/flights?' + urlencode({'hl': 'fr', 'curr': 'EUR', 'tfs': base64.urlsafe_b64encode(blob).decode().rstrip('=')})


def search_links(c: dict) -> list[dict]:
    result = []
    for dest in (('PVG', 'SHA') if c['destination'] == 'ALL' else (c['destination'],)):
        a, b = c['departure'], c['return']
        result.append({
            'destination': dest,
            'google': flight_google_link(c['origin'], dest, a, b, c['adults'], c['children']),
            'kayak': 'https://www.kayak.fr/flights/' + c['origin'] + '-' + dest + '/' + a + '/' + b + '?' + urlencode({
                'sort': 'price_a', 'adults': c['adults'], 'children': c['children'], 'childages': ','.join('8' for _ in range(c['children']))}),
            'skyscanner': 'https://www.skyscanner.fr/transport/vols/' + c['origin'].lower() + '/' + dest.lower() + '/' + a[2:].replace('-', '') + '/' + b[2:].replace('-', '') + '/?' + urlencode({
                'adultsv2': c['adults'], 'childrenv2': ','.join('8' for _ in range(c['children'])), 'cabinclass': 'economy', 'rtn': 1})
        })
    return result


def serpapi_parameters(c: dict, departure_token: str | None = None) -> dict:
    # Stops are different from FlightHunter's filter: 0=any, 1=nonstop, 2=<=1, 3=<=2.
    stops = {'any': 0, '0': 1, '1': 2, '2': 3}[c['stops']]
    params = {'engine': 'google_flights', 'api_key': API_KEY, 'type': 1,
              'departure_id': 'CDG,ORY' if c['origin'] == 'PAR' else c['origin'],
              'arrival_id': 'PVG,SHA' if c['destination'] == 'ALL' else c['destination'],
              'outbound_date': c['departure'], 'return_date': c['return'],
              'adults': c['adults'], 'children': c['children'], 'travel_class': 1,
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
    return {'stops': len(flights) - 1, 'from': depart.get('id') or '', 'to': arrive.get('id') or '',
            'departure': (depart.get('time') or '').replace(' ', 'T'),
            'arrival': (arrive.get('time') or '').replace(' ', 'T'),
            'via': [str(x.get('id')) for x in (offer.get('layovers') or []) if x.get('id')],
            'carriers': airlines, 'duration': duration}


def trip_matches_leg(leg: dict, c: dict, outbound: bool) -> bool:
    if not leg:
        return False
    if outbound:
        airport = ('CDG', 'ORY') if c['origin'] == 'PAR' else (c['origin'],)
        dest = ('PVG', 'SHA') if c['destination'] == 'ALL' else (c['destination'],)
        return leg.get('from') in airport and leg.get('to') in dest and str(leg.get('departure', '')).startswith(c['departure'])
    airport = ('CDG', 'ORY') if c['origin'] == 'PAR' else (c['origin'],)
    dest = ('PVG', 'SHA') if c['destination'] == 'ALL' else (c['destination'],)
    return leg.get('from') in dest and leg.get('to') in airport and str(leg.get('departure', '')).startswith(c['return'])


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
                           'booking_link': flight_google_link(c['origin'], dest, c['departure'], c['return'], c['adults'], c['children'])})
            break  # cheapest valid return for this specific outbound itinerary
    return sorted(result, key=lambda offer: offer['price'])


@app.middleware('http')
async def security_headers(request: Request, call_next):
    res = await call_next(request)
    res.headers['X-Content-Type-Options'] = 'nosniff'
    res.headers['X-Frame-Options'] = 'DENY'
    res.headers['Cache-Control'] = 'no-store'
    res.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    res.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
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
