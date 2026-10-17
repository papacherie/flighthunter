"""FlightHunter AI: flight search, pricing display, referral only. No booking/payments.

Amadeus test prices are not real. In production, offers still need final seller checks.
"""
from __future__ import annotations

import base64
import datetime as dt
import os
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

import requests
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent
app = FastAPI(title='FlightHunter AI', version='1.0.0', docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=ROOT/'static'), name='static')
ENV = os.getenv('AMADEUS_ENV', 'test').lower()
BASE = 'https://api.amadeus.com' if ENV == 'production' else 'https://test.api.amadeus.com'
CLIENT = os.getenv('AMADEUS_CLIENT_ID', '').strip()
SECRET = os.getenv('AMADEUS_CLIENT_SECRET', '').strip()
CODE = os.getenv('APP_ACCESS_CODE', '').strip()
_TOKEN: dict = {'value':'', 'expiration':0.0}
_TOKEN_LOCK = threading.Lock()
_RATE_LOCK = threading.Lock()
_RATE: dict[str,float] = {}


def is_ready() -> bool:
    return bool(CLIENT and SECRET and CODE)


def validate(d: dict) -> dict:
    origin = str(d.get('origin','PAR')).strip().upper()
    dest = str(d.get('destination','ALL')).strip().upper()
    start, end = str(d.get('departure','')).strip(), str(d.get('return','')).strip()
    adults, children = int(d.get('adults',2)), int(d.get('children',1))
    stops = str(d.get('stops','any'))
    if not re.fullmatch('[A-Z]{3}', origin):
        raise ValueError('Départ : code IATA à trois lettres requis.')
    if dest not in ('PVG','SHA','ALL'):
        raise ValueError('Choisir un aéroport de Shanghai valide.')
    try:
        ds,de = dt.date.fromisoformat(start),dt.date.fromisoformat(end)
    except ValueError as e:
        raise ValueError('Dates invalides.') from e
    if ds < dt.date.today() or de <= ds:
        raise ValueError('Le départ doit être à venir et le retour ultérieur.')
    if de > dt.date.today()+dt.timedelta(days=365):
        raise ValueError('Plus de 365 jours à l’avance : disponibilités généralement non ouvertes.')
    if adults not in range(1,7) or children not in range(0,4) or adults+children>8:
        raise ValueError('Voyageurs incorrects (1–8, dont un adulte).')
    if stops not in ('any','0','1','2'):
        raise ValueError('Nombre d’escales incorrect.')
    return {'origin':origin,'destination':dest,'departure':start,'return':end,'adults':adults,'children':children,'stops':stops}


def flight_google_link(origin:str,dest:str,outbound:str,inbound:str,adults:int,children:int) -> str:
    """Encode the observed Google Flights URL; format is undocumented and can change."""
    def leg(date, frm, to):
        return b'\x1a\x1a\x12\x0a'+date.encode('ascii')+b'j\x05\x12\x03'+frm.encode('ascii')+b'r\x05\x12\x03'+to.encode('ascii')
    blob=leg(outbound,origin,dest)+leg(inbound,dest,origin)+b'\x40\x01'*adults+b'\x40\x02'*children+b'\x48\x01\x98\x01\x01'
    return 'https://www.google.com/travel/flights?'+urlencode({'hl':'fr','curr':'EUR','tfs':base64.urlsafe_b64encode(blob).decode().rstrip('=')})


def search_links(criteria:dict) -> list[dict]:
    c=criteria
    result=[]
    for dest in (['PVG','SHA'] if c['destination']=='ALL' else [c['destination']]):
        dep,ret=c['departure'],c['return']
        result.append({
            'destination':dest,
            'google':flight_google_link(c['origin'],dest,dep,ret,c['adults'],c['children']),
            'kayak':'https://www.kayak.fr/flights/'+c['origin']+'-'+dest+'/'+dep+'/'+ret+'?'+urlencode({'sort':'price_a','adults':c['adults'],'children':c['children'],'childages':','.join('8' for _ in range(c['children']))}),
            'skyscanner':'https://www.skyscanner.fr/transport/vols/'+c['origin'].lower()+'/'+dest.lower()+'/'+dep[2:].replace('-','')+'/'+ret[2:].replace('-','')+'/?'+urlencode({'adultsv2':c['adults'],'childrenv2':','.join('8' for _ in range(c['children'])),'cabinclass':'economy','rtn':1})
        })
    return result


def token() -> str:
    now=time.monotonic()
    with _TOKEN_LOCK:
        if _TOKEN['value'] and _TOKEN['expiration']-60>now:
            return _TOKEN['value']
        r=requests.post(BASE+'/v1/security/oauth2/token',data={'grant_type':'client_credentials','client_id':CLIENT,'client_secret':SECRET},timeout=12)
        r.raise_for_status()
        obj=r.json()
        _TOKEN.update(value=obj['access_token'],expiration=now+int(obj.get('expires_in',1200)))
        return _TOKEN['value']


def query_airport(c:dict,dest:str,bearer:str) -> dict:
    params={'originLocationCode':c['origin'],'destinationLocationCode':dest,'departureDate':c['departure'],
            'returnDate':c['return'],'adults':c['adults'],'children':c['children'],
            'currencyCode':'EUR','travelClass':'ECONOMY','max':40}
    r=requests.get(BASE+'/v2/shopping/flight-offers',headers={'Authorization':'Bearer '+bearer,'Accept':'application/json'},params=params,timeout=24)
    if not r.ok:
        raise RuntimeError(f'{dest}: HTTP {r.status_code} (fournisseur indisponible)')
    return r.json()


def leg_info(item:dict, carriers:dict) -> dict:
    segments=item.get('segments') or []
    if not segments:
        return {}
    airlines=list(dict.fromkeys(carriers.get(s.get('carrierCode',''),s.get('carrierCode','')) for s in segments))
    return {'stops':len(segments)-1,'from':segments[0].get('departure',{}).get('iataCode',''),
            'to':segments[-1].get('arrival',{}).get('iataCode',''),
            'departure':segments[0].get('departure',{}).get('at',''),
            'arrival':segments[-1].get('arrival',{}).get('at',''),
            'via':[s.get('arrival',{}).get('iataCode','') for s in segments[:-1]],
            'carriers':airlines,'duration':item.get('duration','')}


def bag_details(offer:dict) -> str:
    values=set()
    for traveler in offer.get('travelerPricings') or []:
        for fare in traveler.get('fareDetailsBySegment') or []:
            bag=fare.get('includedCheckedBags') or {}
            if 'quantity' in bag:
                values.add(f"{bag['quantity']} pièce(s)")
            elif 'weight' in bag:
                values.add(f"{bag['weight']} {bag.get('weightUnit','kg')}")
    return (next(iter(values))+' en soute (sous réserve)') if len(values)==1 else 'À confirmer chez le vendeur'


def normalize(data:dict,dest:str,stops_filter:str,travelers_count:int) -> list[dict]:
    results=[]
    carriers=(data.get('dictionaries') or {}).get('carriers') or {}
    for o in data.get('data',[]):
        legs=o.get('itineraries') or []
        if len(legs)!=2:continue
        if len(o.get('travelerPricings') or [])!=travelers_count:continue
        outbound,inbound=leg_info(legs[0],carriers),leg_info(legs[1],carriers)
        if not outbound or not inbound:continue
        if stops_filter!='any' and any(l['stops']>int(stops_filter) for l in [outbound,inbound]):continue
        price_obj=o.get('price') or {}
        if price_obj.get('currency')!='EUR':continue
        try:
            price=Decimal(str(price_obj['grandTotal']))
            if not price.is_finite() or price<=0:continue
        except (InvalidOperation,KeyError,TypeError):continue
        airline=' / '.join(dict.fromkeys(outbound['carriers']+inbound['carriers']))
        results.append({'id':f'{dest}:{o.get("id","")}', 'source':'Amadeus', 'price':float(price),
                        'carrier':airline,'outbound':outbound,'inbound':inbound,
                        'destination':dest,'baggage':bag_details(o),
                        'price_status':'À confirmer chez le vendeur'})
    return results


@app.middleware('http')
async def security_headers(request:Request, call_next):
    res=await call_next(request)
    res.headers['X-Content-Type-Options']='nosniff'
    res.headers['X-Frame-Options']='DENY'
    res.headers['Cache-Control']='no-store'
    res.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    res.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    return res


@app.get('/')
def home():return FileResponse(ROOT/'static'/'index.html')


@app.get('/health')
def health():return {'ok':True,'product':'FlightHunter AI'}


@app.get('/api/status')
def api_status():
    return {'product':'FlightHunter AI','ready':is_ready(),'api_mode':ENV if is_ready() else 'links_only',
            'private_search':bool(CODE)}


@app.post('/api/search')
def search(body:dict,request:Request):
    try:
        c=validate(body)
    except (ValueError,OverflowError,TypeError) as e:
        return JSONResponse({'error':str(e)},status_code=400)
    result={'criteria':c,'links':search_links(c),'offers':[],
            'checked_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'warning':'Confirme le prix, les passagers et les bagages avant le paiement.'}
    if not is_ready():
        result.update(status='not_configured',mode='links_only',message='Comparateurs disponibles ; aucun fournisseur de prix en direct connecté. Aucun faux tarif.')
        return result
    provided=request.headers.get('X-Access-Code','')
    if not secrets.compare_digest(provided,CODE):
        return JSONResponse({'error':'Code privé incorrect. Ouvre « Configurer l’accès » pour le saisir.'},status_code=401)
    addr=request.client.host if request.client else 'unknown'
    now=time.monotonic()
    with _RATE_LOCK:
        if now-_RATE.get(addr,-1e10)<20:
            return JSONResponse({'error':'Recherche trop rapprochée : réessaie dans quelques secondes.'},status_code=429)
        _RATE[addr]=now
        if len(_RATE)>1000:_RATE.clear()
    try:
        bearer=token()
    except (requests.RequestException,ValueError,KeyError):
        result.update(status='provider_error',message='Identification API Amadeus impossible. Vérifie les variables d’environnement.')
        return JSONResponse(result,status_code=502)
    airports=['PVG','SHA'] if c['destination']=='ALL' else [c['destination']]
    offers,errors=[],[]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures={executor.submit(query_airport,c,a,bearer):a for a in airports}
        for fut in as_completed(futures):
            name=futures[fut]
            try:offers.extend(normalize(fut.result(),name,c['stops'],c['adults']+c['children']))
            except (requests.RequestException,RuntimeError,ValueError,KeyError,TypeError) as e:
                errors.append(str(e)[:100])
    offers.sort(key=lambda x:x['price'])
    result.update(offers=offers[:30],count=len(offers),provider_errors=errors,
                  is_test_data=ENV!='production',
                  status='ok' if offers else ('provider_error' if errors else 'empty'),
                  message='Prix retournés par Amadeus (non garantis lors de la réservation).' if offers else
                  'Aucun prix pour ces critères sur les sources disponibles.')
    if ENV!='production':
        result['warning']='Mode TEST Amadeus : ces tarifs ne sont PAS des prix réels, ni réservables.'
    return result
